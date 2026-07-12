from __future__ import annotations

import pytest

from klaudiusz.render import (
    EMBED_DESCRIPTION_LIMIT,
    LEAD_LIMIT,
    MAX_EMBED_CHARS_PER_MESSAGE,
    MAX_EMBEDS_PER_MESSAGE,
    RenderedNewsletter,
    chunk_newsletter,
    split_at_boundaries,
)


def _newsletter(tldr: str, discussions: str, papers: str, learning: str) -> str:
    return (
        f"## TL;DR\n{tldr}\n\n"
        f"## Discussions\n{discussions}\n\n"
        f"## Papers & links\n{papers}\n\n"
        f"## Learning corner\n{learning}\n"
    )


def _all_embeds(rendered: RenderedNewsletter) -> list[dict]:
    return [embed for batch in rendered.embed_batches for embed in batch]


def _assert_batch_within_discord_limits(batch: list[dict]) -> None:
    assert len(batch) <= MAX_EMBEDS_PER_MESSAGE
    for embed in batch:
        assert len(embed["description"]) <= EMBED_DESCRIPTION_LIMIT
    total_chars = sum(len(e.get("title", "")) + len(e["description"]) for e in batch)
    assert total_chars <= MAX_EMBED_CHARS_PER_MESSAGE


# --- realistic snapshot -----------------------------------------------------


def test_realistic_newsletter_snapshot():
    tldr = (
        "- Actuator torque comparison converged on QDD gearboxes for the legs.\n"
        "- MJX contact-parameter fix unblocked the sim; 1.8 m/s on flat terrain.\n"
        "- Sim2real friction gap remains open; two calibration proposals on the table."
    )
    discussions = (
        "**Leg actuator torque density** — the team compared QDD vs. planetary "
        "gearboxes and settled on QDD for backdrivability. "
        "([thread](https://discord.com/channels/1/2/3))\n\n"
        "**MJX contact tuning** — divergence traced to a stiff contact solver; "
        "fix merged. ([thread](https://discord.com/channels/1/2/4))"
    )
    papers = (
        "- [Legged Robots that Keep on Learning]"
        "(https://arxiv.org/abs/2002.10344) — cited on catastrophic "
        "forgetting during sim2real transfer.\n"
        "- [MuJoCo XLA docs](https://mujoco.readthedocs.io/en/stable/mjx.html) "
        "— reference for the contact solver options."
    )
    learning = (
        "**Quasi-Direct Drive (QDD) actuators** — a QDD actuator uses a low "
        "gear ratio so joint torque is dominated by motor output rather than "
        "gear multiplication, keeping backdrivability high. Learn more: "
        "[MIT Cheetah actuator paper](https://example.com/cheetah-actuator).\n\n"
        "**Sim2real friction gap** — simulators approximate contact friction "
        "with simplified models, so a policy tuned in sim can behave "
        "differently on the real floor. Learn more: "
        "[Sim-to-real survey](https://example.com/sim2real-survey)."
    )
    markdown = _newsletter(tldr, discussions, papers, learning)

    rendered = chunk_newsletter(markdown)

    assert rendered.lead == tldr
    assert len(rendered.embed_batches) == 1
    embeds = rendered.embed_batches[0]
    assert [e["title"] for e in embeds] == [
        "Discussions",
        "Papers & links",
        "Learning corner",
    ]
    assert embeds[0]["description"] == discussions
    assert embeds[1]["description"] == papers
    assert embeds[2]["description"] == learning
    _assert_batch_within_discord_limits(embeds)


# --- adversarial: a single long bullet under the limit ----------------------


def test_single_300_char_bullet_stays_whole():
    bullet = "- " + ("x" * 298)
    assert len(bullet) == 300

    chunks = split_at_boundaries(bullet, EMBED_DESCRIPTION_LIMIT)

    assert chunks == [bullet]


def test_300_char_bullet_survives_full_pipeline():
    bullet = "- " + ("x" * 298)
    markdown = _newsletter("- ok", bullet, "- ok", "- ok")

    rendered = chunk_newsletter(markdown)

    discussions = next(e for e in _all_embeds(rendered) if e["title"] == "Discussions")
    assert discussions["description"] == bullet


# --- adversarial: an oversized section splits with counters -----------------


def test_10000_char_section_splits_across_embeds_with_counters():
    bullets = [f"- item {i:04d} " + ("z" * 90) for i in range(100)]
    big_section = "\n".join(bullets)
    assert len(big_section) > 10_000
    markdown = _newsletter("- ok", big_section, "- ok", "- ok")

    rendered = chunk_newsletter(markdown)

    discussion_embeds = [
        e for e in _all_embeds(rendered) if e["title"].startswith("Discussions")
    ]
    assert len(discussion_embeds) > 1
    assert discussion_embeds[0]["title"] == "Discussions"
    assert [e["title"] for e in discussion_embeds[1:]] == [
        f"Discussions ({i + 2})" for i in range(len(discussion_embeds) - 1)
    ]
    for embed in discussion_embeds:
        assert len(embed["description"]) <= EMBED_DESCRIPTION_LIMIT
    # every bullet survives, in order, undamaged
    rejoined = "\n".join(e["description"] for e in discussion_embeds)
    assert rejoined.split("\n") == bullets


# --- adversarial: a markdown link sitting exactly at a split boundary -------


def test_link_exactly_at_boundary_is_never_split():
    bullet_one = "- " + ("a" * 46)
    bullet_two = "- see [click here](https://example.com/page) for details"
    text = bullet_one + "\n" + bullet_two
    # big enough for each bullet alone, too small for both together
    limit = max(len(bullet_one), len(bullet_two))

    chunks = split_at_boundaries(text, limit)

    assert chunks == [bullet_one, bullet_two]
    assert "[click here](https://example.com/page)" in chunks[1]


# --- adversarial: lead overflow --------------------------------------------


def test_lead_over_2000_chars_overflows_into_embed():
    bullets = [f"- bullet {i:03d} " + ("q" * 30) for i in range(60)]
    tldr = "\n".join(bullets)
    assert len(tldr) > LEAD_LIMIT
    markdown = _newsletter(tldr, "- ok", "- ok", "- ok")

    rendered = chunk_newsletter(markdown)

    assert len(rendered.lead) <= LEAD_LIMIT
    assert rendered.lead != tldr
    overflow_embeds = [
        e for e in _all_embeds(rendered) if e["title"].startswith("TL;DR (cont.)")
    ]
    assert overflow_embeds
    # nothing from the TL;DR body is lost: lead + overflow reconstruct every bullet
    recovered = "\n".join([rendered.lead] + [e["description"] for e in overflow_embeds])
    assert recovered.split("\n") == bullets


def test_lead_under_2000_chars_has_no_overflow_embed():
    markdown = _newsletter("- short and sweet", "- ok", "- ok", "- ok")

    rendered = chunk_newsletter(markdown)

    assert not [e for e in _all_embeds(rendered) if "TL;DR" in e["title"]]


# --- adversarial: missing / out-of-order sections ---------------------------


def test_missing_section_fails_loudly():
    markdown = "## TL;DR\n- ok\n\n## Discussions\n- ok\n\n## Learning corner\n- ok\n"

    with pytest.raises(SystemExit) as excinfo:
        chunk_newsletter(markdown)

    message = str(excinfo.value)
    assert "Papers & links" in message
    assert "Learning corner" in message  # what was found is listed


def test_out_of_order_sections_fails_loudly():
    markdown = (
        "## Discussions\n- ok\n\n"
        "## TL;DR\n- ok\n\n"
        "## Papers & links\n- ok\n\n"
        "## Learning corner\n- ok\n"
    )

    with pytest.raises(SystemExit) as excinfo:
        chunk_newsletter(markdown)

    assert "Discussions" in str(excinfo.value)


# --- adversarial: a single line over the embed limit ------------------------


def test_single_line_over_embed_limit_fails_loudly():
    huge_line = "- " + ("w" * (EMBED_DESCRIPTION_LIMIT + 10))

    with pytest.raises(SystemExit) as excinfo:
        split_at_boundaries(huge_line, EMBED_DESCRIPTION_LIMIT)

    message = str(excinfo.value)
    assert str(EMBED_DESCRIPTION_LIMIT) in message


def test_section_with_single_oversized_line_fails_loudly_end_to_end():
    huge_line = "- " + ("w" * (EMBED_DESCRIPTION_LIMIT + 10))
    markdown = _newsletter("- ok", "- ok", huge_line, "- ok")

    with pytest.raises(SystemExit):
        chunk_newsletter(markdown)


# --- property-style: every produced batch respects all three limits --------


@pytest.mark.parametrize(
    "section_sizes",
    [
        (1, 1, 1, 1),
        (5, 5, 5, 5),
        (200, 3, 3, 3),
        (3, 200, 3, 3),
        (3, 3, 3, 200),
        (40, 40, 40, 40),
    ],
)
def test_every_batch_respects_discord_limits(section_sizes):
    tldr_n, disc_n, papers_n, learning_n = section_sizes

    def bullets(n: int, label: str) -> str:
        return "\n".join(f"- {label} {i:04d} " + ("m" * 60) for i in range(n))

    markdown = _newsletter(
        bullets(tldr_n, "tldr"),
        bullets(disc_n, "disc"),
        bullets(papers_n, "papers"),
        bullets(learning_n, "learning"),
    )

    rendered = chunk_newsletter(markdown)

    assert len(rendered.lead) <= LEAD_LIMIT
    for batch in rendered.embed_batches:
        _assert_batch_within_discord_limits(batch)
