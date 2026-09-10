"""`chapter_manifest.capability_model` -- the concrete `checker.CapabilityModel`.

`ChapterCapabilityModel` itself is tested directly against a synthetic
`CapabilityDerivation` and a hand-built predecessor chain, so the
"already granted by a predecessor" half doesn't need the real chapter chain.
`build_capability_model` is tested against the real repo state (real
`reference/chapters.json`, real `output/uranium-build/`), the same way
`test_chapter_manifest_boundary_model.py` pins real corpus state.
"""
from __future__ import annotations

from rpg2gba.capability_sites import CapabilityDerivation, CapabilitySite
from rpg2gba.chapter_manifest.capability_model import (
    ChapterCapabilityModel,
    build_capability_model,
)
from rpg2gba.chapter_manifest.checker import CapabilityGrant


def _derivation(grants: dict[str, list[CapabilitySite]]) -> CapabilityDerivation:
    token_sources = {token: (("switch", i),) for i, token in enumerate(grants)}
    return CapabilityDerivation(
        _grants={token: tuple(sites) for token, sites in grants.items()},
        token_sources=token_sources,
    )


def _site(token: str, row_id: str, map_id: int, chapter_id: str | None) -> CapabilitySite:
    return CapabilitySite(
        token=token, row_id=row_id, map_id=map_id, chapter_id=chapter_id, detail="test"
    )


# --- ChapterCapabilityModel: pure logic --------------------------------------


def test_grant_sites_translates_derivation_sites_to_capability_grants() -> None:
    derivation = _derivation({
        "rock_smash": [_site("rock_smash", "map001/ev001/p0", 1, "CH07")],
    })
    model = ChapterCapabilityModel("CH07", derivation, frozenset({"CH07"}))
    sites = model.grant_sites("rock_smash")
    assert sites == (CapabilityGrant(row_id="map001/ev001/p0", map_id=1, chapter_id="CH07"),)


def test_grant_sites_passes_through_undetermined_and_empty() -> None:
    derivation = _derivation({})
    model = ChapterCapabilityModel("CH01", derivation, frozenset({"CH01"}))
    assert model.grant_sites("never_heard_of") is None


def test_granted_within_excludes_sites_outside_the_chain() -> None:
    derivation = _derivation({
        "final_event": [_site("final_event", "map199/ev001/p0", 199, "CH57")],
    })
    # CH01's chain is {CH01} -- CH57 is not a predecessor.
    model = ChapterCapabilityModel("CH01", derivation, frozenset({"CH01"}))
    assert model.granted_within("final_event") == ()


def test_granted_within_includes_a_site_in_this_chapter_itself() -> None:
    derivation = _derivation({
        "got_pokemon": [_site("got_pokemon", "map050/ev019/p0", 50, "CH01")],
    })
    model = ChapterCapabilityModel("CH01", derivation, frozenset({"CH01"}))
    granted = model.granted_within("got_pokemon")
    assert granted == (CapabilityGrant(row_id="map050/ev019/p0", map_id=50, chapter_id="CH01"),)


def test_granted_within_includes_a_site_in_a_predecessor() -> None:
    derivation = _derivation({
        "got_pokemon": [_site("got_pokemon", "map050/ev019/p0", 50, "CH01")],
    })
    # CH02's chain includes CH01 as a predecessor.
    model = ChapterCapabilityModel("CH02", derivation, frozenset({"CH01", "CH02"}))
    assert len(model.granted_within("got_pokemon")) == 1


def test_granted_within_is_empty_when_grant_sites_is_undetermined() -> None:
    derivation = _derivation({})
    model = ChapterCapabilityModel("CH01", derivation, frozenset({"CH01"}))
    assert model.granted_within("never_heard_of") == ()


def test_granted_within_is_empty_when_grant_sites_is_confidently_empty() -> None:
    derivation = CapabilityDerivation(_grants={}, token_sources={"dead": (("switch", 1),)})
    model = ChapterCapabilityModel("CH01", derivation, frozenset({"CH01"}))
    assert model.grant_sites("dead") == ()
    assert model.granted_within("dead") == ()


# --- build_capability_model: real repo state ---------------------------------


def test_build_capability_model_returns_none_for_unknown_chapter() -> None:
    assert build_capability_model("CH_NO_SUCH_CHAPTER") is None


def test_build_capability_model_real_ch01_final_event_not_granted_within() -> None:
    """Pinned against the real corpus: `FINAL EVENT` (switch 125) is granted
    only from map199, owned by CH57 -- CH01 is nowhere in that chain, so
    `granted_within` must be empty. If this breaks because the chapter chain
    or the switch's grant site changed, that's real news; update the
    assertion."""
    model = build_capability_model("CH01")
    assert model is not None
    sites = model.grant_sites("final_event")
    assert sites is not None
    assert len(sites) == 1
    assert model.granted_within("final_event") == ()


def test_build_capability_model_real_ch01_got_pokemon_is_granted_within_itself() -> None:
    """`Got Pokemon` (switch 2) is granted from map050, one of CH01's own
    maps -- so a `blocked:got_pokemon` row authored on CH01 would be a false
    claim: the capability is granted same-chapter."""
    model = build_capability_model("CH01")
    assert model is not None
    granted = model.granted_within("got_pokemon")
    assert len(granted) == 1
    assert granted[0].chapter_id == "CH01"
