<!--
T11 note. Task T9 owns the pipeline instructions above this section: context
pull, newsletter generation, post-newsletter, ending in a marker line
`<!-- research-log step: added at Phase 4 -->`. T9 had not merged into this
branch when this file was written. This file currently holds only the
research-log step below. When T9 merges, fold its content in above this
section, at the marker line, and delete this note.
-->

## Research log

After the newsletter step posts, or exits cleanly on a quiet day, continue
with the research log for the same date.

1. Fetch the current month's log file and the previous 14 days of entries
   from `docs/research-log/` in `shrek-dog`.
2. Follow `prompts/research-log.md` to decide what qualifies and write the
   day's entry.
3. Run `klaudiusz publish-log` as described in `prompts/research-log.md`.

A quiet log day, where nothing in the day clears the bar for an entry, is a
normal outcome. Producing no bundle and opening no PR is correct on that
day, not an error to retry or report.
