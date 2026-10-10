"""`beat_gen.__main__.claim_generic_archetypes`: a match handed to the generic
template (`_generic_reads_it_better`) is still claimed as its archetype, so the
manifest's conformance rule doesn't read the row as unclaimed (CH06's TVs,
map046/ev006+ev008; Theo, map14000/ev079)."""
from __future__ import annotations

from rpg2gba.beat_gen.__main__ import claim_generic_archetypes
from rpg2gba.beat_gen.plan import PlannedBeat

TV = "map046/ev006/p0"


def _beat(template: str, rows: tuple[str, ...]) -> PlannedBeat:
    return PlannedBeat(name="b", template=template, map_id=46, rows=rows, group="b")


def test_generic_beat_claims_the_handed_over_archetype():
    (beat,) = claim_generic_archetypes(
        [_beat("generic", (TV, f"{TV}/b0", f"{TV}/b1"))], {TV: "flavour_npc"})
    assert dict(beat.kwargs)["archetype"] == ((TV, "flavour_npc"),)


def test_beats_without_claimed_rows_are_untouched():
    plain = _beat("generic", ("map046/ev032/p0",))
    assert claim_generic_archetypes([plain], {TV: "flavour_npc"}) == (plain,)


def test_non_generic_templates_are_untouched():
    warp = _beat("warp", (TV,))
    assert claim_generic_archetypes([warp], {TV: "flavour_npc"}) == (warp,)
