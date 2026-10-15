"""`chapter_manifest.capability_model` -- the concrete `checker.CapabilityModel`.

`ChapterCapabilityModel` itself is tested directly against a synthetic
`CapabilityDerivation` and a hand-built predecessor chain, so the
"already granted by a predecessor" half doesn't need the real chapter chain.
`build_capability_model` is tested against the real repo state (real
`reference/chapters.json`, real `output/uranium-build/`), the same way
`test_chapter_manifest_boundary_model.py` pins real corpus state.
"""
from __future__ import annotations

from rpg2gba.capability_sites import (
    BadgeWriteSite,
    CapabilityDerivation,
    CapabilitySite,
    ItemGrantSite,
)
from rpg2gba.chapter_manifest.capability_model import (
    ChapterCapabilityModel,
    build_capability_model,
    taught_in_chain,
)
from rpg2gba.chapter_manifest.checker import CapabilityGrant


def _derivation(grants: dict[str, list[CapabilitySite]]) -> CapabilityDerivation:
    token_sources = {token: (("switch", i),) for i, token in enumerate(grants)}
    return CapabilityDerivation(
        _grants={token: tuple(sites) for token, sites in grants.items()},
        token_sources=token_sources,
    )


def _badge_write(
    badge_index: int, row_id: str, map_id: int, chapter_id: str | None
) -> BadgeWriteSite:
    return BadgeWriteSite(
        row_id=row_id,
        map_id=map_id,
        event_id=1,
        page_idx=0,
        badge_index=badge_index,
        chapter_id=chapter_id,
    )


def _site(token: str, row_id: str, map_id: int, chapter_id: str | None) -> CapabilitySite:
    return CapabilitySite(
        token=token, row_id=row_id, map_id=map_id, chapter_id=chapter_id, detail="test"
    )


# --- ChapterCapabilityModel: pure logic --------------------------------------


def test_grant_sites_translates_derivation_sites_to_capability_grants() -> None:
    # `rock_smash` is a field-capability token now, handled via the
    # badge-count path -- use a plain (non-field) token here so this test
    # stays about the generic switch/variable translation, not the badge
    # model (covered separately below).
    derivation = _derivation({
        "some_flag": [_site("some_flag", "map001/ev001/p0", 1, "CH07")],
    })
    model = ChapterCapabilityModel("CH07", derivation, frozenset({"CH07"}))
    sites = model.grant_sites("some_flag")
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


# --- field-capability badge-count model ---------------------------------------


def test_field_token_below_threshold_returns_sites_and_not_granted() -> None:
    """Chain with zero badges: rock_smash needs >= 1, so the badge write is
    returned as an (unconfirmed) grant site, but `granted_within` must stay
    empty -- the chain has not met even the necessary badge conjunct."""
    derivation = CapabilityDerivation(
        badge_writes=(_badge_write(0, "map042/ev003/p0", 42, "CH02"),),
    )
    model = ChapterCapabilityModel("CH01", derivation, frozenset({"CH01"}))
    sites = model.grant_sites("rock_smash")
    assert sites is not None
    assert len(sites) == 1
    assert model.granted_within("rock_smash") == ()


def test_field_token_at_or_above_threshold_is_undetermined_not_granted() -> None:
    """Chain with >= the required distinct badge count: the badge conjunct
    is met, but the move/item conjunct is unmodelled, so this must be
    undetermined (`None`), never a confirmed grant -- reporting sites here
    would let checker.py raise a false `blocked_already_granted`."""
    derivation = CapabilityDerivation(
        badge_writes=(_badge_write(0, "map042/ev003/p0", 42, "CH01"),),
    )
    model = ChapterCapabilityModel("CH01", derivation, frozenset({"CH01"}))
    assert model.grant_sites("rock_smash") is None
    assert model.granted_within("rock_smash") == ()


def test_field_token_duplicate_badge_index_counts_once() -> None:
    """Badge 7 is written true at two real-corpus sites; the distinct-count
    used against the requirement must not double-count it."""
    derivation = CapabilityDerivation(
        badge_writes=(
            _badge_write(0, "map042/ev003/p0", 42, "CH01"),
            _badge_write(7, "map175/ev032/p0", 175, "CH01"),
            _badge_write(7, "map175/ev033/p0", 175, "CH01"),
        ),
    )
    # rock_smash needs >= 1 distinct badge -- one of the two sites already
    # suffices, so a THIRD write of the same index must not push the count
    # to 2 and wrongly satisfy something needing >= 2.
    model = ChapterCapabilityModel("CH01", derivation, frozenset({"CH01"}))
    assert model.grant_sites("rock_smash") is None  # 1 distinct >= 1 required

    # strength needs >= 4 distinct badges -- 2 distinct badges (0 and 7)
    # must not satisfy it even though there are 3 writes total.
    assert model.grant_sites("strength") is not None


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


# --- field-capability item half + taught (CH08 §9, 2026-10-15) ----------------


def _item_grant(item: str, row_id: str, map_id: int, chapter_id: str | None) -> ItemGrantSite:
    return ItemGrantSite(
        row_id=row_id, map_id=map_id, event_id=1, page_idx=0, item=item, chapter_id=chapter_id
    )


def _rock_smash_derivation(item_chapter: str | None = "CH06") -> CapabilityDerivation:
    return CapabilityDerivation(
        badge_writes=(_badge_write(0, "map042/ev003/p0", 42, "CH06"),),
        item_grants=(_item_grant("HM06", "map14000/ev079/p0", 14000, item_chapter),),
    )


def test_badge_met_but_item_not_in_chain_returns_item_sites_not_granted() -> None:
    """The badge is in the chain but HM06 is granted later: an honest "not
    yet" -- the item's grant site, never a confirmed grant."""
    model = ChapterCapabilityModel(
        "CH06", _rock_smash_derivation(item_chapter="CH09"), frozenset({"CH06"})
    )
    sites = model.grant_sites("rock_smash")
    assert sites is not None and [s.row_id for s in sites] == ["map14000/ev079/p0"]
    assert model.granted_within("rock_smash") == ()
    assert not model.obtainable("rock_smash")


def test_obtainable_but_not_taught_stays_undetermined() -> None:
    """CH07's situation: badge + HM06 in the chain, but no suite has taught
    the move yet -- undetermined (`None`), exactly as before the item half
    was modelled, so CH07's affirmed `blocked:rock_smash` rows stay valid."""
    model = ChapterCapabilityModel("CH07", _rock_smash_derivation(), frozenset({"CH06", "CH07"}))
    assert model.obtainable("rock_smash")
    assert not model.held("rock_smash")
    assert model.grant_sites("rock_smash") is None
    assert model.granted_within("rock_smash") == ()


def test_taught_in_chain_confirms_held() -> None:
    model = ChapterCapabilityModel(
        "CH08",
        _rock_smash_derivation(),
        frozenset({"CH06", "CH08"}),
        taught=frozenset({"rock_smash"}),
    )
    assert model.held("rock_smash")
    granted = {g.row_id for g in model.granted_within("rock_smash")}
    assert granted == {"map042/ev003/p0", "map14000/ev079/p0"}


def test_token_without_item_half_never_held_even_if_taught() -> None:
    """`strength` has no `FIELD_CAPABILITY_ITEMS` entry: badge-only, never
    confirmed held."""
    derivation = CapabilityDerivation(
        badge_writes=tuple(_badge_write(i, f"map{i:03d}/ev001/p0", i, "CH01") for i in range(4)),
    )
    model = ChapterCapabilityModel(
        "CH01", derivation, frozenset({"CH01"}), taught=frozenset({"strength"})
    )
    assert not model.held("strength")
    assert model.grant_sites("strength") is None
    assert model.granted_within("strength") == ()


def test_taught_in_chain_reads_module_text(tmp_path) -> None:
    (tmp_path / "ch08.py").write_text('beat("teach_rock_smash")\n', encoding="utf-8")
    (tmp_path / "ch07.py").write_text('beat("smash_rock")\n', encoding="utf-8")
    assert taught_in_chain(frozenset({"CH07"}), tmp_path) == frozenset()
    assert taught_in_chain(frozenset({"CH07", "CH08"}), tmp_path) == frozenset({"rock_smash"})


def test_real_ch07_rock_smash_obtainable_not_held() -> None:
    """Pinned against the real corpus: CH06 grants badge 1 and HM06, so
    CH07 can obtain Rock Smash, but no committed suite teaches it."""
    model = build_capability_model("CH07")
    assert model is not None
    assert model.obtainable("rock_smash")
    assert not model.held("rock_smash")
    assert model.grant_sites("rock_smash") is None
