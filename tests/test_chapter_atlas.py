"""Tests for the chapter atlas: the binding's curation rules and the census.

The binding tests run against synthetic JSON so they pin the *rules*, not the
current contents of `reference/chapters.json`; a separate group validates the
real file so a bad hand-edit fails the suite.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.chapter_atlas.binding import (
    SCHEMA_VERSION,
    default_binding_path,
    load_binding,
)
from rpg2gba.chapter_atlas.census import (
    COND_TYPE_SCRIPT,
    MECHANIC_BY_HEAD,
    RUBY_KEYWORDS,
    census_for_maps,
)

OUT_DIR = Path("output/uranium-build")


def _untranspiled_map_id() -> int | None:
    """Lowest corpus map id that has never been through the transpiler (no
    `scripts/MapNNN.pory`). Derived rather than pinned: any map named here
    stops being untranspiled the moment its chapter reaches the frontier."""
    scripts = OUT_DIR / "scripts"
    for path in sorted((OUT_DIR / "maps").glob("Map*.json")):
        map_id = int(path.stem.removeprefix("Map"))
        if not (scripts / f"Map{map_id:03d}.pory").is_file():
            return map_id
    return None


UNTRANSPILED_MAP_ID = _untranspiled_map_id() if (OUT_DIR / "maps").is_dir() else None


def _write(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "chapters.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _minimal(**overrides) -> dict:
    chapter = {
        "id": "CH01", "act": "A1", "title": "Somewhere",
        "wiki_page": "Somewhere", "maps": [32], "outdoor": 32,
        "tier": "full", "status": "planned",
    }
    chapter.update(overrides.pop("chapter", {}))
    payload = {
        "schema": SCHEMA_VERSION,
        "acts": [{"id": "A1", "title": "Act one", "chapters": ["CH01"]}],
        "chapters": [chapter],
    }
    payload.update(overrides)
    return payload


# --------------------------------------------------------------------------- #
# binding curation rules
# --------------------------------------------------------------------------- #

def test_minimal_binding_loads(tmp_path: Path) -> None:
    binding = load_binding(_write(tmp_path, _minimal()))
    assert [c.id for c in binding.chapters] == ["CH01"]
    assert binding.chapter("CH01").maps == (32,)
    assert binding.map_ids == [32]


def test_wrong_schema_version_is_rejected(tmp_path: Path) -> None:
    payload = _minimal()
    payload["schema"] = SCHEMA_VERSION + 1
    with pytest.raises(ValueError, match="schema"):
        load_binding(_write(tmp_path, payload))


def test_duplicate_chapter_id_is_rejected(tmp_path: Path) -> None:
    payload = _minimal()
    payload["chapters"].append(dict(payload["chapters"][0]))
    payload["acts"][0]["chapters"] = ["CH01", "CH01"]
    with pytest.raises(ValueError, match="duplicate chapter id"):
        load_binding(_write(tmp_path, payload))


def test_chapter_naming_an_unknown_act_is_rejected(tmp_path: Path) -> None:
    payload = _minimal(chapter={"act": "A9"})
    with pytest.raises(ValueError, match="unknown act"):
        load_binding(_write(tmp_path, payload))


def test_act_listing_an_unknown_chapter_is_rejected(tmp_path: Path) -> None:
    payload = _minimal()
    payload["acts"][0]["chapters"] = ["CH01", "CH99"]
    with pytest.raises(ValueError, match="unknown chapter"):
        load_binding(_write(tmp_path, payload))


def test_chapter_not_listed_in_any_act_is_rejected(tmp_path: Path) -> None:
    payload = _minimal()
    payload["acts"][0]["chapters"] = []
    with pytest.raises(ValueError, match="listed in acts"):
        load_binding(_write(tmp_path, payload))


def test_outdoor_map_must_be_one_of_the_chapters_maps(tmp_path: Path) -> None:
    payload = _minimal(chapter={"outdoor": 999})
    with pytest.raises(ValueError, match="outdoor map"):
        load_binding(_write(tmp_path, payload))


def test_chapter_with_no_maps_is_rejected(tmp_path: Path) -> None:
    payload = _minimal(chapter={"maps": [], "outdoor": None})
    with pytest.raises(ValueError, match="no maps"):
        load_binding(_write(tmp_path, payload))


def test_unknown_tier_is_rejected(tmp_path: Path) -> None:
    payload = _minimal(chapter={"tier": "exhaustive"})
    with pytest.raises(ValueError, match="tier"):
        load_binding(_write(tmp_path, payload))


def test_unknown_status_is_rejected(tmp_path: Path) -> None:
    payload = _minimal(chapter={"status": "shipped"})
    with pytest.raises(ValueError, match="status"):
        load_binding(_write(tmp_path, payload))


def test_unknown_predecessor_is_rejected(tmp_path: Path) -> None:
    payload = _minimal(chapter={"predecessor": "CH77"})
    with pytest.raises(ValueError, match="unknown predecessor"):
        load_binding(_write(tmp_path, payload))


def test_revisits_over_the_same_maps_are_allowed(tmp_path: Path) -> None:
    payload = _minimal()
    payload["chapters"].append({
        "id": "CH02", "act": "A1", "title": "Somewhere (revisit)",
        "wiki_page": "Somewhere", "visit": 2, "maps": [32], "outdoor": 32,
        "predecessor": "CH01", "tier": "thin", "status": "planned",
    })
    payload["acts"][0]["chapters"] = ["CH01", "CH02"]
    binding = load_binding(_write(tmp_path, payload))
    assert binding.chapter("CH02").is_revisit
    assert not binding.chapter("CH01").is_revisit
    assert [c.id for c in binding.chapters_for_map(32)] == ["CH01", "CH02"]


def test_gapped_visit_numbering_is_rejected(tmp_path: Path) -> None:
    payload = _minimal()
    payload["chapters"].append({
        "id": "CH02", "act": "A1", "title": "Somewhere (revisit)",
        "wiki_page": "Somewhere", "visit": 3, "maps": [32], "outdoor": 32,
        "tier": "thin", "status": "planned",
    })
    payload["acts"][0]["chapters"] = ["CH01", "CH02"]
    with pytest.raises(ValueError, match="visit numbers"):
        load_binding(_write(tmp_path, payload))


def test_map_id_absent_from_map_infos_is_rejected(tmp_path: Path) -> None:
    infos = tmp_path / "map_infos.json"
    infos.write_text(json.dumps({"48": {"name": "elsewhere"}}), encoding="utf-8")
    with pytest.raises(ValueError, match="not in map_infos"):
        load_binding(_write(tmp_path, _minimal()), map_infos_path=infos)


# --------------------------------------------------------------------------- #
# the committed binding
# --------------------------------------------------------------------------- #

def test_the_real_binding_validates() -> None:
    infos = OUT_DIR / "map_infos.json"
    binding = load_binding(
        map_infos_path=infos if infos.exists() else None)
    assert len(binding.acts) == 10
    assert binding.chapters[0].id == "CH01"
    # CH01 is slice 1; its roster is the SoT that map_set.py mirrors.
    assert binding.chapter("CH01").maps == (32, 48, 49, 50, 64, 65, 89, 172)


def test_chapter_ids_are_contiguous_and_play_ordered() -> None:
    binding = load_binding()
    ids = [c.id for c in binding.chapters]
    assert ids == [f"CH{n:02d}" for n in range(1, len(ids) + 1)]


def test_every_act_lists_at_least_one_chapter() -> None:
    binding = load_binding()
    for act in binding.acts:
        assert act.chapters, f"{act.id} lists no chapters"


def test_predecessor_chain_is_unbroken_after_the_first_chapter() -> None:
    binding = load_binding()
    for previous, chapter in zip(binding.chapters, binding.chapters[1:]):
        assert chapter.predecessor == previous.id, (
            f"{chapter.id} follows {previous.id} but names "
            f"{chapter.predecessor!r} as predecessor")


def test_built_chapters_match_the_slice_map_set() -> None:
    # reference/chapters.json is meant to become the SoT that map_set derives
    # from; until that cutover lands, this test pins them together so the two
    # lists cannot drift silently. SLICE_MAP_IDS is the *cumulative* build set:
    # every chapter up to and including the frontier one (CH01 + CH02 since
    # 2026-08-05), not just the newest.
    from rpg2gba.tileset_converter.map_set import SLICE_MAP_IDS

    binding = load_binding()
    built = binding.chapter("CH01").maps + binding.chapter("CH02").maps
    assert sorted(built) == sorted(SLICE_MAP_IDS)


def test_bound_and_unbound_maps_account_for_the_whole_corpus() -> None:
    infos_path = OUT_DIR / "map_infos.json"
    if not infos_path.exists():
        pytest.skip("no converted corpus on disk")
    raw = json.loads(default_binding_path().read_text(encoding="utf-8"))
    unbound = {int(k) for k in raw.get("unbound_maps", {}) if k != "_comment"}
    known = {int(k) for k in json.loads(
        infos_path.read_text(encoding="utf-8"))}
    bound = set(load_binding().map_ids)
    assert not (bound & unbound), "a map is both bound and declared unbound"
    assert known - bound - unbound == set(), "some maps are unaccounted for"


# --------------------------------------------------------------------------- #
# census
# --------------------------------------------------------------------------- #

def test_ruby_keywords_never_shadow_a_mechanic_head() -> None:
    # A Ruby control word must not also be a mechanic key, or `_record_script`
    # would silently drop a real mechanic into the ruby_blocks bucket.
    assert not (RUBY_KEYWORDS & set(MECHANIC_BY_HEAD))


@pytest.mark.skipif(not (OUT_DIR / "maps").is_dir(),
                    reason="no converted corpus on disk")
def test_census_counts_trainer_battles_hidden_in_conditionals() -> None:
    # The regression this pins: every Uranium trainer battle is a code-111
    # type-12 conditional wrapping pbTrainerBattle(...), and there is no
    # code-301 in the corpus. Reading only 301/355 reported zero trainers.
    route1 = census_for_maps([33, 81], out_dir=OUT_DIR)
    assert route1.totals["trainer_battles"] == 9
    assert "trainer battle" in route1.mechanics

    moki = census_for_maps([32, 48, 49, 50, 64, 65, 89, 172], out_dir=OUT_DIR)
    # 01-moki.md section 4.1: exactly one trainer battle in the 8-map roster.
    assert moki.totals["trainer_battles"] == 1


@pytest.mark.skipif(not (OUT_DIR / "maps").is_dir(),
                    reason="no converted corpus on disk")
def test_census_normalises_the_kernel_prefix() -> None:
    moki = census_for_maps([32, 48, 49, 50, 64, 65, 89, 172], out_dir=OUT_DIR)
    assert not [h for h in moki.script_heads if h.startswith("Kernel.")]


@pytest.mark.skipif(UNTRANSPILED_MAP_ID is None,
                    reason="no converted corpus on disk, or every map transpiled")
def test_census_reports_unstaged_queue_as_none_not_zero() -> None:
    # A zero would read as "transpiles clean"; the truth is "never transpiled".
    # Pinned on a map id no build has ever transpiled — deliberately NOT a
    # frontier map: this used to name Route 01 (33), which stopped being a
    # never-transpiled map the day CH02 converted it (2026-08-05).
    unstaged = census_for_maps([UNTRANSPILED_MAP_ID], out_dir=OUT_DIR)
    assert unstaged.maps[0].unhandled is None

    moki = census_for_maps([50], out_dir=OUT_DIR)
    assert moki.maps[0].unhandled is not None


@pytest.mark.skipif(not (OUT_DIR / "maps").is_dir(),
                    reason="no converted corpus on disk")
def test_census_finds_seams_and_external_exits() -> None:
    moki = census_for_maps([32, 48, 49, 50, 64, 65, 89, 172], out_dir=OUT_DIR)
    # connections.json carries Moki Town E <-> Route 03 W.
    assert any(32 in (s[0], s[3]) for s in moki.seams)
    # Moki's cave triad warps to Route 01 (map 33), outside the chapter.
    assert 33 in moki.external_warp_destinations


def test_missing_map_json_fails_loud(tmp_path: Path) -> None:
    (tmp_path / "maps").mkdir()
    (tmp_path / "map_infos.json").write_text("{}", encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="no converted map"):
        census_for_maps([12345], out_dir=tmp_path)


def test_conditional_script_discriminator_is_the_documented_one() -> None:
    assert COND_TYPE_SCRIPT == 12
