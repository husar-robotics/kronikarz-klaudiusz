# Newsletter generation guidance

This is the fixed instruction for writing the daily newsletter file from the context bundle
(`transcript.md`, `repo-signal.md`, `links.md`, `meta.json`). The daily routine reads it at the
newsletter step. See `prompts/routine-daily.md`.

The audience spans the whole server: robotics, ML, mechanical engineering, and electronics. Each
reader has strong expertise in their own field and little in the others.

## Output format

Write exactly four `##` sections, in this order: `TL;DR`, `Discussions`, `Papers & links`,
`Learning corner`. Use no other section and no other heading level for these four topics. The
`post-newsletter` command parses the file by these exact headings in this exact order and rejects
the file if they don't match.

## TL;DR

Write three to six bullets covering the whole day, Discord and repo activity both. Use plain
language. A reader skims this section to decide whether to read further. Keep the whole section
under 2,000 characters.

## Discussions

Write one short digest per topic that actually developed into a real exchange. Skip greetings,
logistics, and one-off remarks that nobody followed up on.

End each digest with the jump URLs of the thread or messages it draws from, taken from
`transcript.md`. A reader must be able to click through to the original messages.

## Papers & links

List every substantive link from `links.md`. Use the resolved title and authors exactly as given
in `links.md`. Never invent a title or author. Never correct one that looks wrong. If `links.md`
has no resolved title, use the bare URL.

Give each item one line on why it came up in the conversation, followed by the "shared here" jump
URL from `links.md`.

## Learning corner

This section is the educational core of the newsletter. Pick two to five concepts from the day
that a non-specialist reader would need to look up. Favor concepts that came up in a discussion
outside their own field, since that is where the gap is widest.

For each concept, write two to three plain-language sentences explaining it, then exactly one
pointer to learn more. Web search is allowed and encouraged for finding pointers. Prefer a
canonical source: official documentation, a textbook, or a well-known tutorial. Avoid a random blog
post when a canonical source exists.

Every pointer must be a real, working URL. `post-newsletter` sends a HEAD request to each one and
drops it if it fails, so do not write a URL from memory that you have not seen resolve.

## Language

Write in the language that dominates that day's transcript. On a mixed Polish/English day, write
Polish prose. Leave English technical terms as they are. Do not translate them.

## Citation rule

Every claim about what someone said or decided carries a jump URL to the message it came from.

## Length budget

Keep the whole newsletter under about 8,000 characters, so it fits in one lead message plus one
embed thread.
