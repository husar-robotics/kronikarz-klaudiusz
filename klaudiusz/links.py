"""URL extraction from Discord messages, arXiv/DOI metadata resolution, and link validation."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, replace

import httpx

ARXIV_API = "http://export.arxiv.org/api/query"
DOI_HEADERS = {"Accept": "application/vnd.citationstyles.csl+json"}
ATOM_NS = "{http://www.w3.org/2005/Atom}"
REQUEST_TIMEOUT = 10.0

_URL_RE = re.compile(r"https?://\S+")
_ARXIV_ID_RE = re.compile(
    r"arxiv\.org/(?:abs|pdf)/(?P<id>\d{4}\.\d{4,5})(?:v\d+)?(?:\.pdf)?", re.IGNORECASE
)
_DOI_RE = re.compile(r"doi\.org/(?P<doi>10\.\d{4,9}/\S+)", re.IGNORECASE)

# Characters that are never the last character of a shared URL, only sentence
# or markup punctuation that happened to sit next to it.
_ALWAYS_STRIP_TRAILING = ".,;:!?\"'`>"
_BALANCED_CLOSERS = {")": "(", "]": "[", "}": "{"}


@dataclass(frozen=True)
class SharedLink:
    url: str
    title: str | None
    authors: tuple[str, ...]
    kind: str  # "arxiv" | "doi" | "other"
    shared_in_jump_url: str


def _clean_url(raw: str) -> str:
    """Strip whitespace-adjacent punctuation that isn't part of the URL itself.

    Trailing `.`/`,`/quotes/etc. are never part of a URL. A trailing closing
    bracket is stripped only when unbalanced within the token, so a URL
    legitimately wrapped in parentheses keeps its own parens.
    """
    url = raw
    changed = True
    while changed and url:
        changed = False
        last = url[-1]
        if last in _ALWAYS_STRIP_TRAILING:
            url = url[:-1]
            changed = True
            continue
        opener = _BALANCED_CLOSERS.get(last)
        if opener is not None and url.count(opener) < url.count(last):
            url = url[:-1]
            changed = True
    return url


def _arxiv_id(url: str) -> str | None:
    match = _ARXIV_ID_RE.search(url)
    return match.group("id") if match else None


def _doi(url: str) -> str | None:
    match = _DOI_RE.search(url)
    if not match:
        return None
    doi = match.group("doi").rstrip("/")
    if doi.lower().endswith(".pdf"):
        doi = doi[: -len(".pdf")]
    return doi


def _classify(url: str) -> str:
    if _arxiv_id(url) is not None:
        return "arxiv"
    if _doi(url) is not None:
        return "doi"
    return "other"


def extract_urls(records: list[dict]) -> list[SharedLink]:
    """Every http(s) URL in message content and attachments, deduplicated.

    The first record to share a URL wins; its jump URL is kept. `records`
    must already be in the order sharing precedence should follow
    (chronological, as produced by ingest).
    """
    seen: dict[str, SharedLink] = {}
    for record in records:
        jump_url = record["jump_url"]
        raw_urls = list(_URL_RE.findall(record.get("content") or ""))
        raw_urls.extend(record.get("attachment_urls") or [])
        for raw in raw_urls:
            url = _clean_url(raw)
            if not url or url in seen:
                continue
            seen[url] = SharedLink(
                url=url,
                title=None,
                authors=(),
                kind=_classify(url),
                shared_in_jump_url=jump_url,
            )
    return list(seen.values())


def _csl_author_name(author: dict) -> str | None:
    if author.get("literal"):
        return str(author["literal"])
    parts = [p for p in (author.get("given"), author.get("family")) if p]
    return " ".join(parts) if parts else None


def _resolve_arxiv(link: SharedLink, http: httpx.Client) -> SharedLink:
    arxiv_id = _arxiv_id(link.url)
    if arxiv_id is None:
        return link
    try:
        resp = http.get(ARXIV_API, params={"id_list": arxiv_id}, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
    except (httpx.HTTPError, ET.ParseError):
        return link

    entry = root.find(f"{ATOM_NS}entry")
    if entry is None:
        return link
    title_el = entry.find(f"{ATOM_NS}title")
    title = " ".join(title_el.text.split()) if title_el is not None and title_el.text else None
    if title is None:
        return link
    authors = tuple(
        " ".join(name_el.text.split())
        for author_el in entry.findall(f"{ATOM_NS}author")
        for name_el in (author_el.find(f"{ATOM_NS}name"),)
        if name_el is not None and name_el.text
    )
    return replace(link, title=title, authors=authors)


def _resolve_doi(link: SharedLink, http: httpx.Client) -> SharedLink:
    doi = _doi(link.url)
    if doi is None:
        return link
    try:
        resp = http.get(
            f"https://doi.org/{doi}",
            headers=DOI_HEADERS,
            follow_redirects=True,
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError):
        return link

    title = data.get("title")
    if not title:
        return link
    authors = tuple(
        name for author in data.get("author", []) if (name := _csl_author_name(author)) is not None
    )
    return replace(link, title=title, authors=authors)


def _resolve_one(link: SharedLink, http: httpx.Client) -> SharedLink:
    if link.kind == "arxiv":
        return _resolve_arxiv(link, http)
    if link.kind == "doi":
        return _resolve_doi(link, http)
    return link


def resolve(links: list[SharedLink], client: httpx.Client | None = None) -> list[SharedLink]:
    """Fetch title/authors for arXiv and DOI links.

    Network errors and unparseable responses degrade a link to its bare URL
    (kind stays, title stays None) rather than raising; resolution must never
    crash the pipeline. Pass `client` to inject a mock or a shared client.
    """
    owns_client = client is None
    http = client or httpx.Client()
    try:
        return [_resolve_one(link, http) for link in links]
    finally:
        if owns_client:
            http.close()


def _validate_one(url: str, http: httpx.Client) -> bool:
    try:
        resp = http.head(url, follow_redirects=True, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 405:
            resp = http.get(url, follow_redirects=True, timeout=REQUEST_TIMEOUT)
        return 200 <= resp.status_code < 400
    except Exception:
        # Arbitrary member-shared and web-search domains: any failure mode
        # (timeout, DNS, TLS, malformed URL) means "not usable", never a crash.
        return False


def validate(urls: list[str], client: httpx.Client | None = None) -> dict[str, bool]:
    """HEAD each URL (GET fallback on 405); any failure or non-2xx/3xx is False. Never raises."""
    owns_client = client is None
    http = client or httpx.Client()
    try:
        return {url: _validate_one(url, http) for url in urls}
    finally:
        if owns_client:
            http.close()


def links_markdown(shared_links: list[SharedLink]) -> str:
    """Render the `links.md` section of the context bundle."""
    if not shared_links:
        return "No links shared.\n"
    lines = []
    for link in shared_links:
        label = link.title or link.url
        bullet = f"- [{label}]({link.url})"
        if link.authors:
            bullet += f" — {', '.join(link.authors)}"
        if link.kind != "other":
            bullet += f" `{link.kind}`"
        bullet += f" ([shared here]({link.shared_in_jump_url}))"
        lines.append(bullet)
    return "\n".join(lines) + "\n"
