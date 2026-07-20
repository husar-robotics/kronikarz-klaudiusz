# Research log entry generation

This is the guidance for writing one day's entry in `shrek-dog`'s research log.
It runs after the newsletter step, on the same day's context bundle.

## Inputs

Two sources feed the entry.

The day's context bundle is already on disk from the newsletter step:
`transcript.md`, `repo-signal.md`, `links.md`, and `meta.json`. Read all four.

Before writing, fetch the project's memory of its own log. Read
`docs/research-log/<current-month>.md` from `shrek-dog` (path
`docs/research-log/`, file named `YYYY-MM.md`), and read the entries dated
in the 14 days before the one being written. If the month file does not
exist yet, or covers fewer than 14 days of history, treat the missing days
as no prior context. That is not an error.

`shrek-dog` is private and the environment has no `gh` CLI. Fetch it with a
shallow clone whose credential helper reads `HVSR_TOKEN` inside git's
own process — never put the token on a command line or in a URL:

```sh
git -c credential.helper= \
    -c 'credential.helper=!f() { echo username=x-access-token; echo "password=$HVSR_TOKEN"; }; f' \
    clone --depth 1 https://github.com/husar-robotics/shrek-dog.git /tmp/shrek-dog
```

Then read the log files from `/tmp/shrek-dog/docs/research-log/`. Clone
outside this repository's working tree, exactly as above.

## Report deltas, not state

An ongoing topic earns a new bullet only when something changed today: a
decision landed, a result arrived, or the direction moved. Restating a
topic's known state, with nothing new in it, is noise. Skip it.

## The five tags

Every bullet opens with one bold tag, followed by a colon. Every bullet
carries at least one link: a Discord jump URL, a PR or commit URL, or a
relative link to a details file.

**Decision** — a choice the project committed to, and the reasoning that
closed it.

```markdown
- **Decision:** Leg actuators switch to QDD (quasi-direct drive) after the
  torque-density comparison landed.
  ([discussion](https://discord.com/channels/...), [PR #42](https://github.com/husar-robotics/shrek-dog/pull/42))
```

**Result** — an outcome from a run, an experiment, a build, or a test.

```markdown
- **Result:** The MJX training run converged after the contact-parameter
  fix; the policy holds 1.8 m/s on flat terrain.
  ([details](details/2026-07-12-mjx-divergence.md))
```

**Direction** — a shift in what the project is aiming at next, before any
decision has closed it.

```markdown
- **Direction:** Gait planning is moving from a hand-tuned trot toward a
  learned central pattern generator, after last week's sim results looked
  more robust.
  ([discussion](https://discord.com/channels/...))
```

**Question** — an open question that needs resolving, with the current
state of the debate.

```markdown
- **Question:** The sim2real friction gap is unresolved; two calibration
  approaches are on the table.
  ([thread](https://discord.com/channels/...))
```

**Resource** — a paper, tool, or reference that changed how the project
thinks about a topic.

```markdown
- **Resource:** The team adopted the "Contact-Implicit MJX" paper as the
  reference for the new contact-parameter tuning approach.
  ([discussion](https://discord.com/channels/...), [paper](https://arxiv.org/abs/0000.00000))
```

## Budget: six bullets, at most

Write at most six bullets for the day. Fewer is better. One solid Decision
bullet beats six bullets that pad out a quiet day.

## Details files

Write a details file only when a topic produced enough substance that
compressing it to one bullet would lose information a future session
needs: an experiment write-up, a paper discussion, a design argument. Most
days need none.

Name each details file `details/<date>-<slug>.md`, using the day's date
and a short slug for the topic. Every details file must be linked from a
bullet in `entry.md`, and every details link in `entry.md` must point to a
file that exists in `details/`. `publish-log` checks both directions and
fails the bundle if either is missing.

## The no-entry rule

When nothing in the day clears the bar for a single bullet, produce
nothing. Do not create an output directory. Do not run `publish-log`. A
quiet log day is a normal outcome, not a failure to fix.

## Output

When at least one bullet qualifies, write the bundle to an output
directory: `entry.md` with the day's `## YYYY-MM-DD` section, plus
`details/` if any topic needed one.

Run `uv run klaudiusz publish-log <dir> --date <date> --dry-run` first.
Fix whatever the validation reports. Then run the same command again
without `--dry-run` to open the PR.

## Audience

The entry's readers are future project members and LLM sessions, reading
months after the day it describes. They remember nothing about today.
Write each bullet so a reader with no memory of the day understands it on
its own, and follows the link only for depth, not for the basic fact.
