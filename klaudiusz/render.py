"""Chunk a newsletter markdown file into Discord messages and embeds.

Discord's hard limits (from the API, not configurable): message content
<=2,000 chars; embed description <=4,096 chars; per message <=10 embeds and
<=6,000 chars total across all of a message's embeds (titles + descriptions).
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass

REQUIRED_SECTIONS = ("TL;DR", "Discussions", "Papers & links", "Learning corner")

LEAD_LIMIT = 2000
EMBED_DESCRIPTION_LIMIT = 4096
MAX_EMBEDS_PER_MESSAGE = 10
MAX_EMBED_CHARS_PER_MESSAGE = 6000

_HEADING_RE = re.compile(r"^##[ \t]+(.+?)[ \t]*$", re.MULTILINE)
_BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")


@dataclass
class RenderedNewsletter:
    """A newsletter split for posting: one lead message plus embed batches.

    `lead` is plain message content (<=2,000 chars). `embed_batches` is a
    list of messages' worth of embeds; each inner list already satisfies all
    three Discord limits and can be posted as one message's `embeds`.
    """

    lead: str
    embed_batches: list[list[dict]]


def chunk_newsletter(markdown: str, header: str | None = None) -> RenderedNewsletter:
    """Split a four-section newsletter markdown document for Discord posting.

    `header` is prepended to the lead message (before the TL;DR content) and
    counts toward its length limit.

    Fails loudly (`SystemExit`) when the required `##` sections are missing,
    out of order, or when a single paragraph/bullet cannot fit an embed even
    on its own.
    """
    sections = _parse_sections(markdown)

    tldr = f"{header}\n\n{sections['TL;DR']}" if header else sections["TL;DR"]
    lead_chunks = split_at_boundaries(tldr, LEAD_LIMIT)
    lead = lead_chunks[0] if lead_chunks else ""
    overflow = "\n\n".join(lead_chunks[1:])

    embeds: list[dict] = []
    if overflow:
        embeds.extend(_section_embeds("TL;DR (cont.)", overflow))
    for title in REQUIRED_SECTIONS[1:]:
        embeds.extend(_section_embeds(title, sections[title]))

    return RenderedNewsletter(lead=lead, embed_batches=_batch_embeds(embeds))


def split_at_boundaries(text: str, limit: int) -> list[str]:
    """Split text into chunks of at most `limit` chars.

    Cuts happen only between paragraphs (blank-line-separated blocks) or
    between bullet list items, never inside a line, so a markdown link never
    gets split. A single paragraph or bullet longer than `limit` is a hard
    error naming the offending line: by contract bullets are short, so this
    signals a content problem rather than something to silently truncate.
    """
    atoms = _split_units(text)
    chunks: list[str] = []
    current = ""
    for sep, unit in atoms:
        if len(unit) > limit:
            sys.exit(
                f"[FAIL] a single paragraph/bullet is {len(unit)} chars, over the "
                f"{limit}-char limit, and cannot be split further: {unit!r}"
            )
        if not current:
            current = unit
            continue
        candidate = current + sep + unit
        if len(candidate) <= limit:
            current = candidate
        else:
            chunks.append(current)
            current = unit
    if current:
        chunks.append(current)
    return chunks


def _parse_sections(markdown: str) -> dict[str, str]:
    """Split markdown into its `##` sections, keyed by heading text.

    Requires exactly REQUIRED_SECTIONS, in that order; anything else fails
    loudly listing what was found instead of guessing.
    """
    matches = list(_HEADING_RE.finditer(markdown))
    found = [m.group(1).strip() for m in matches]
    if tuple(found) != REQUIRED_SECTIONS:
        sys.exit(
            "[FAIL] newsletter must have exactly these ## sections, in order: "
            f"{', '.join(REQUIRED_SECTIONS)}; found: {', '.join(found) or '(none)'}"
        )

    sections: dict[str, str] = {}
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
        sections[found[i]] = markdown[start:end].strip()
    return sections


def _split_units(text: str) -> list[tuple[str, str]]:
    """Break text into (separator_before, unit_text) atoms.

    A unit is one bullet list item or one whole paragraph — the only points
    at which `split_at_boundaries` may cut. A block of contiguous non-blank
    lines that are all bullets splits one atom per line (bullet boundary);
    any other block stays a single atom (paragraph boundary only applies
    around it, not inside it).
    """
    stripped = text.strip()
    if not stripped:
        return []

    blocks = re.split(r"\n[ \t]*\n", stripped)
    atoms: list[tuple[str, str]] = []
    for block_index, block in enumerate(blocks):
        sep_before_block = "" if block_index == 0 else "\n\n"
        lines = block.split("\n")
        non_blank = [line for line in lines if line.strip()]
        if non_blank and all(_BULLET_RE.match(line) for line in non_blank):
            for line_index, line in enumerate(lines):
                sep = sep_before_block if line_index == 0 else "\n"
                atoms.append((sep, line))
        else:
            atoms.append((sep_before_block, block))
    return atoms


def _section_embeds(title: str, body: str) -> list[dict]:
    """Render one newsletter section as one or more embeds.

    A section that needs more than one embed continues with the same title
    plus a counter, e.g. "Discussions (2)".
    """
    chunks = split_at_boundaries(body, EMBED_DESCRIPTION_LIMIT)
    return [
        {"title": title if i == 0 else f"{title} ({i + 1})", "description": chunk}
        for i, chunk in enumerate(chunks)
    ]


def _embed_chars(embed: dict) -> int:
    return len(embed.get("title", "")) + len(embed.get("description", ""))


def _batch_embeds(embeds: list[dict]) -> list[list[dict]]:
    """Greedily pack embeds into messages within the 10-embed/6,000-char limits."""
    batches: list[list[dict]] = []
    current: list[dict] = []
    current_chars = 0
    for embed in embeds:
        chars = _embed_chars(embed)
        over_count = len(current) >= MAX_EMBEDS_PER_MESSAGE
        over_chars = current_chars + chars > MAX_EMBED_CHARS_PER_MESSAGE
        if current and (over_count or over_chars):
            batches.append(current)
            current, current_chars = [], 0
        current.append(embed)
        current_chars += chars
    if current:
        batches.append(current)
    return batches
