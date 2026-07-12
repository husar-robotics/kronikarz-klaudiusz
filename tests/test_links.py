from __future__ import annotations

import httpx
import respx

from klaudiusz.links import SharedLink, extract_urls, links_markdown, resolve, validate

ARXIV_ATOM_FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <link href="http://arxiv.org/api/query?id_list=2406.01234" rel="self" type="application/atom+xml"/>
  <title type="text">ArXiv Query: id_list=2406.01234</title>
  <id>http://arxiv.org/api/6qs7f8ihn2p3</id>
  <updated>2026-07-12T00:00:00-04:00</updated>
  <opensearch:totalResults xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">1</opensearch:totalResults>
  <opensearch:startIndex xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">0</opensearch:startIndex>
  <opensearch:itemsPerPage xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">1</opensearch:itemsPerPage>
  <entry>
    <id>http://arxiv.org/abs/2406.01234v2</id>
    <updated>2024-06-03T00:00:00Z</updated>
    <published>2024-06-01T00:00:00Z</published>
    <title>Attention Is What You Need:
  A Study of Transformer Distillation</title>
    <summary>  We study distillation of large transformer models into
    smaller student networks...
    </summary>
    <author>
      <name>Jane Doe</name>
    </author>
    <author>
      <name>John Smith</name>
    </author>
    <link href="http://arxiv.org/abs/2406.01234v2" rel="alternate" type="text/html"/>
    <link title="pdf" href="http://arxiv.org/pdf/2406.01234v2" rel="related" type="application/pdf"/>
    <category term="cs.LG" scheme="http://arxiv.org/schemas/atom"/>
  </entry>
</feed>
"""

ARXIV_ATOM_NO_ENTRY_FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title type="text">ArXiv Query: id_list=9999.99999</title>
  <opensearch:totalResults xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">0</opensearch:totalResults>
</feed>
"""

CSL_JSON_FIXTURE = {
    "type": "article-journal",
    "title": "Deep Residual Learning for Image Recognition",
    "author": [
        {"given": "Kaiming", "family": "He"},
        {"given": "Xiangyu", "family": "Zhang"},
    ],
    "DOI": "10.1109/cvpr.2016.90",
    "container-title": "2016 IEEE Conference on Computer Vision and Pattern Recognition (CVPR)",
}


def make_record(content="", attachment_urls=None, jump_url="https://discord.com/channels/1/2/3", **overrides):
    record = {
        "id": "1",
        "channel_id": "10",
        "channel_name": "general",
        "thread_name": None,
        "author": "alice",
        "author_is_bot": False,
        "timestamp": "2026-07-12T10:00:00+00:00",
        "content": content,
        "attachment_urls": attachment_urls or [],
        "jump_url": jump_url,
    }
    record.update(overrides)
    return record


# --- extract_urls: punctuation edge cases -----------------------------------


def test_extract_urls_strips_trailing_period():
    records = [make_record(content="check this out https://example.com/page. cool right?")]

    links = extract_urls(records)

    assert [link.url for link in links] == ["https://example.com/page"]


def test_extract_urls_strips_trailing_comma():
    records = [make_record(content="see https://example.com/page, it's great")]

    links = extract_urls(records)

    assert [link.url for link in links] == ["https://example.com/page"]


def test_extract_urls_strips_unbalanced_closing_paren_keeps_balanced_url_parens():
    records = [make_record(content="See (https://en.wikipedia.org/wiki/Erlang_(programming_language)) for background.")]

    links = extract_urls(records)

    assert [link.url for link in links] == ["https://en.wikipedia.org/wiki/Erlang_(programming_language)"]


def test_extract_urls_dedup_first_sharer_wins():
    records = [
        make_record(content="https://example.com/paper", jump_url="https://discord.com/channels/1/2/first"),
        make_record(content="https://example.com/paper", jump_url="https://discord.com/channels/1/2/second"),
    ]

    links = extract_urls(records)

    assert len(links) == 1
    assert links[0].shared_in_jump_url == "https://discord.com/channels/1/2/first"


def test_extract_urls_includes_attachment_urls():
    records = [
        make_record(
            content="no links here",
            attachment_urls=["https://cdn.discordapp.com/attachments/1/2/image.png"],
        )
    ]

    links = extract_urls(records)

    assert len(links) == 1
    assert links[0].url == "https://cdn.discordapp.com/attachments/1/2/image.png"
    assert links[0].kind == "other"


def test_extract_urls_no_urls_returns_empty_list():
    records = [make_record(content="nothing to see here")]

    assert extract_urls(records) == []


# --- arXiv / DOI recognition -------------------------------------------------


def test_extract_urls_recognizes_arxiv_abs_url():
    records = [make_record(content="https://arxiv.org/abs/2406.01234")]

    links = extract_urls(records)

    assert links[0].kind == "arxiv"


def test_extract_urls_recognizes_arxiv_pdf_url_with_version_and_extension():
    records = [make_record(content="https://arxiv.org/pdf/2406.01234v2.pdf")]

    links = extract_urls(records)

    assert links[0].kind == "arxiv"


def test_extract_urls_recognizes_doi_url():
    records = [make_record(content="https://doi.org/10.1109/cvpr.2016.90")]

    links = extract_urls(records)

    assert links[0].kind == "doi"


def test_extract_urls_other_kind_for_unrelated_url():
    records = [make_record(content="https://example.com/blog/post")]

    links = extract_urls(records)

    assert links[0].kind == "other"


# --- resolve: arXiv -----------------------------------------------------------


@respx.mock
def test_resolve_arxiv_fetches_title_and_authors():
    respx.get("https://export.arxiv.org/api/query", params={"id_list": "2406.01234"}).mock(
        return_value=httpx.Response(200, text=ARXIV_ATOM_FIXTURE)
    )
    link = SharedLink(
        url="https://arxiv.org/abs/2406.01234",
        title=None,
        authors=(),
        kind="arxiv",
        shared_in_jump_url="https://discord.com/channels/1/2/3",
    )

    resolved = resolve([link])

    assert resolved[0].title == "Attention Is What You Need: A Study of Transformer Distillation"
    assert resolved[0].authors == ("Jane Doe", "John Smith")
    assert resolved[0].kind == "arxiv"
    assert resolved[0].url == link.url


@respx.mock
def test_resolve_arxiv_degrades_on_server_error():
    respx.get("https://export.arxiv.org/api/query").mock(return_value=httpx.Response(500))
    link = SharedLink(
        url="https://arxiv.org/abs/2406.01234",
        title=None,
        authors=(),
        kind="arxiv",
        shared_in_jump_url="https://discord.com/channels/1/2/3",
    )

    resolved = resolve([link])

    assert resolved[0] == link


@respx.mock
def test_resolve_arxiv_degrades_on_garbage_xml():
    respx.get("https://export.arxiv.org/api/query").mock(return_value=httpx.Response(200, text="not xml <<<"))
    link = SharedLink(
        url="https://arxiv.org/abs/2406.01234",
        title=None,
        authors=(),
        kind="arxiv",
        shared_in_jump_url="https://discord.com/channels/1/2/3",
    )

    resolved = resolve([link])

    assert resolved[0] == link


@respx.mock
def test_resolve_arxiv_degrades_when_no_entry_in_feed():
    respx.get("https://export.arxiv.org/api/query").mock(return_value=httpx.Response(200, text=ARXIV_ATOM_NO_ENTRY_FIXTURE))
    link = SharedLink(
        url="https://arxiv.org/abs/9999.99999",
        title=None,
        authors=(),
        kind="arxiv",
        shared_in_jump_url="https://discord.com/channels/1/2/3",
    )

    resolved = resolve([link])

    assert resolved[0] == link


# --- resolve: DOI ---------------------------------------------------------


@respx.mock
def test_resolve_doi_fetches_title_and_authors_and_sends_csl_header():
    route = respx.get("https://doi.org/10.1109/cvpr.2016.90").mock(return_value=httpx.Response(200, json=CSL_JSON_FIXTURE))
    link = SharedLink(
        url="https://doi.org/10.1109/cvpr.2016.90",
        title=None,
        authors=(),
        kind="doi",
        shared_in_jump_url="https://discord.com/channels/1/2/3",
    )

    resolved = resolve([link])

    assert resolved[0].title == "Deep Residual Learning for Image Recognition"
    assert resolved[0].authors == ("Kaiming He", "Xiangyu Zhang")
    assert route.calls.last.request.headers["accept"] == "application/vnd.citationstyles.csl+json"


@respx.mock
def test_resolve_doi_degrades_on_server_error():
    respx.get("https://doi.org/10.1109/cvpr.2016.90").mock(return_value=httpx.Response(500))
    link = SharedLink(
        url="https://doi.org/10.1109/cvpr.2016.90",
        title=None,
        authors=(),
        kind="doi",
        shared_in_jump_url="https://discord.com/channels/1/2/3",
    )

    resolved = resolve([link])

    assert resolved[0] == link


@respx.mock
def test_resolve_doi_degrades_on_garbage_json():
    respx.get("https://doi.org/10.1109/cvpr.2016.90").mock(return_value=httpx.Response(200, text="not json"))
    link = SharedLink(
        url="https://doi.org/10.1109/cvpr.2016.90",
        title=None,
        authors=(),
        kind="doi",
        shared_in_jump_url="https://discord.com/channels/1/2/3",
    )

    resolved = resolve([link])

    assert resolved[0] == link


def test_resolve_other_kind_is_passthrough_with_no_http_call():
    link = SharedLink(
        url="https://example.com/blog/post",
        title=None,
        authors=(),
        kind="other",
        shared_in_jump_url="https://discord.com/channels/1/2/3",
    )

    with respx.mock:
        resolved = resolve([link])

    assert resolved == [link]


# --- validate -----------------------------------------------------------------


@respx.mock
def test_validate_200_is_true():
    respx.head("https://example.com/ok").mock(return_value=httpx.Response(200))

    result = validate(["https://example.com/ok"])

    assert result == {"https://example.com/ok": True}


@respx.mock
def test_validate_own_client_sends_descriptive_user_agent():
    # Wikipedia and similar hosts 403 the default python-httpx UA (verified
    # live 2026-07-12), which would read as a dead link.
    route = respx.head("https://example.com/ua").mock(return_value=httpx.Response(200))

    validate(["https://example.com/ua"])

    ua = route.calls[0].request.headers["User-Agent"]
    assert "kronikarz-klaudiusz" in ua
    assert "python-httpx" not in ua


@respx.mock
def test_validate_404_is_false():
    respx.head("https://example.com/missing").mock(return_value=httpx.Response(404))

    result = validate(["https://example.com/missing"])

    assert result == {"https://example.com/missing": False}


@respx.mock
def test_validate_405_falls_back_to_get():
    respx.head("https://example.com/head-not-allowed").mock(return_value=httpx.Response(405))
    respx.get("https://example.com/head-not-allowed").mock(return_value=httpx.Response(200))

    result = validate(["https://example.com/head-not-allowed"])

    assert result == {"https://example.com/head-not-allowed": True}


@respx.mock
def test_validate_timeout_is_false():
    respx.head("https://example.com/slow").mock(side_effect=httpx.TimeoutException("timed out"))

    result = validate(["https://example.com/slow"])

    assert result == {"https://example.com/slow": False}


@respx.mock
def test_validate_multiple_urls_independent_results():
    respx.head("https://example.com/ok").mock(return_value=httpx.Response(200))
    respx.head("https://example.com/missing").mock(return_value=httpx.Response(404))

    result = validate(["https://example.com/ok", "https://example.com/missing"])

    assert result == {"https://example.com/ok": True, "https://example.com/missing": False}


# --- links_markdown -------------------------------------------------------------


def test_links_markdown_empty():
    assert links_markdown([]) == "No links shared.\n"


def test_links_markdown_snapshot_mixed_fixture():
    shared_links = [
        SharedLink(
            url="https://arxiv.org/abs/2406.01234",
            title="Attention Is What You Need: A Study of Transformer Distillation",
            authors=("Jane Doe", "John Smith"),
            kind="arxiv",
            shared_in_jump_url="https://discord.com/channels/1/2/100",
        ),
        SharedLink(
            url="https://doi.org/10.1109/cvpr.2016.90",
            title=None,
            authors=(),
            kind="doi",
            shared_in_jump_url="https://discord.com/channels/1/2/101",
        ),
        SharedLink(
            url="https://example.com/blog/post",
            title=None,
            authors=(),
            kind="other",
            shared_in_jump_url="https://discord.com/channels/1/2/102",
        ),
    ]

    markdown = links_markdown(shared_links)

    assert markdown == (
        "- [Attention Is What You Need: A Study of Transformer Distillation]"
        "(https://arxiv.org/abs/2406.01234) — Jane Doe, John Smith `arxiv` "
        "([shared here](https://discord.com/channels/1/2/100))\n"
        "- [https://doi.org/10.1109/cvpr.2016.90](https://doi.org/10.1109/cvpr.2016.90) `doi` "
        "([shared here](https://discord.com/channels/1/2/101))\n"
        "- [https://example.com/blog/post](https://example.com/blog/post) "
        "([shared here](https://discord.com/channels/1/2/102))\n"
    )
