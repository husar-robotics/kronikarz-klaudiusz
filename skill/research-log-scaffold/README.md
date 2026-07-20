# Research log

This is a day-by-day research diary for the project. Klaudiusz, a bot that
reads the project Discord and this repo's activity, drafts each day's entry
and opens it as a pull request. A human reviews and merges every entry
before it lands here. Not every day gets an entry: a day with nothing worth
recording produces no PR.

## How to read it

Entries are grouped into monthly files: `2026-07.md` holds every entry from
July 2026, one `## YYYY-MM-DD` section per day that had something to log.

Each entry is a short list of tagged bullets. Every bullet opens with one
of five tags:

- **Decision** — a choice the project committed to, and why.
- **Result** — an outcome from a run, an experiment, a build, or a test.
- **Direction** — a shift in what the project is aiming at next.
- **Question** — an open question, and the current state of the debate.
- **Resource** — a paper, tool, or reference that changed the project's
  thinking on a topic.

Every bullet links to its source: a Discord message, a PR or commit, or a
file in `details/`.

The `details/` folder holds the small number of topics that needed more
than one bullet: an experiment write-up, a paper discussion, a design
argument. A details file is named `details/<date>-<slug>.md` and is always
linked from the entry that references it.

## Example entry

```markdown
## 2026-07-12
- **Decision:** Leg actuators switch to QDD (quasi-direct drive) after the
  torque-density comparison landed.
  ([discussion](https://discord.com/channels/...), [PR #42](https://github.com/machinekind/wojtek/pull/42))
- **Result:** The MJX training run converged after the contact-parameter
  fix; the policy holds 1.8 m/s on flat terrain.
  ([details](details/2026-07-12-mjx-divergence.md))
- **Question:** The sim2real friction gap is unresolved; two calibration
  approaches are on the table.
  ([thread](https://discord.com/channels/...))
```
