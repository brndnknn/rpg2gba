"""Phase 3 map-deserializer tests (PHASE3_PLAN test strategy).

`.rxdata` is Marshal output and cannot be re-emitted, so there is no
parse→emit→re-parse round-trip. Fidelity is guarded by conservation (counts vs
the inventory oracle), schema conformance, command-code coverage, byte-exact
golden maps, and idempotence. All require the real Uranium tree, so they take
`uranium_data` (skips when `RPG2GBA_URANIUM_SRC` is unset) and are marked
`phase3`.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.map_deserializer import command_catalog, driver, validate

pytestmark = pytest.mark.phase3

GOLDEN_DIR = Path(__file__).parent / "fixtures" / "maps_golden"
GOLDEN_MAPS = ["Map001.json", "Map002.json", "Map021.json", "Map071.json"]


@pytest.fixture(scope="module")
def deserialized(uranium_data: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Deserialize the whole corpus once into a temp dir, shared by the module."""
    uranium_src = uranium_data.parent  # uranium_data is $SRC/Data
    out_dir = tmp_path_factory.mktemp("phase3_out")
    n_maps = driver.run(uranium_src, out_dir, clean=True)
    assert n_maps == validate.ORACLE["maps"]
    return out_dir


def test_conservation(deserialized: Path) -> None:
    """Total maps/events/pages match the Phase 0 inventory oracle exactly."""
    totals = validate.validate_output(deserialized, oracle=True)
    assert totals == validate.ORACLE


def test_schema_and_raw_commands(deserialized: Path) -> None:
    """Containers carry the contract keys and commands are preserved RAW (E1)."""
    m = json.loads((deserialized / "maps" / "Map001.json").read_text(encoding="utf-8"))
    assert {"map_id", "tileset_id", "width", "height", "tiles", "events"} <= m.keys()
    assert m["map_id"] == 1
    t = m["tiles"]
    assert t["xsize"] * t["ysize"] * t["zsize"] == len(t["data"])

    ev = m["events"][0]
    assert {"id", "name", "x", "y", "pages"} <= ev.keys()
    cmd = ev["pages"][0]["list"][0]
    assert {"code", "indent", "parameters"} <= cmd.keys()


def test_continuations_not_merged(deserialized: Path) -> None:
    """401/655 continuations survive as their own commands — no merging (E1)."""
    seen_codes: set[int] = set()
    for path in (deserialized / "maps").glob("Map*.json"):
        m = json.loads(path.read_text(encoding="utf-8"))
        for ev in m["events"]:
            for page in ev["pages"]:
                seen_codes.update(c["code"] for c in page["list"])
    # 401 = Show Text continuation, 655 = Script continuation. If Phase 3 had
    # folded continuations into their parent, these would be absent.
    assert 401 in seen_codes
    assert 655 in seen_codes


def test_command_coverage(deserialized: Path, tmp_path: Path) -> None:
    """Every command code in use is cataloged (E7 guard) and the doc is emitted."""
    ref = tmp_path / "reference"
    ref.mkdir()
    command_catalog.build(deserialized, ref)  # raises on any uncataloged code
    assert (ref / "rgss_event_commands.md").is_file()
    switches = json.loads((ref / "uranium_switches.json").read_text(encoding="utf-8"))
    variables = json.loads((ref / "uranium_variables.json").read_text(encoding="utf-8"))
    # Known named seeds from System.rxdata (sanity that the dump is populated).
    assert any(v == "Got Pokemon" for v in switches.values())
    assert len(variables) > 0


@pytest.mark.parametrize("name", GOLDEN_MAPS)
def test_golden_maps(deserialized: Path, name: str) -> None:
    """Selected maps deserialize byte-for-byte to their committed fixtures."""
    produced = (deserialized / "maps" / name).read_bytes()
    golden = (GOLDEN_DIR / name).read_bytes()
    assert produced == golden, f"{name} drifted from its golden fixture"


def test_idempotence(deserialized: Path, uranium_data: Path, tmp_path: Path) -> None:
    """A second clean run produces byte-identical map JSON."""
    second = tmp_path / "second"
    driver.run(uranium_data.parent, second, clean=True)
    for path in (deserialized / "maps").glob("Map*.json"):
        other = second / "maps" / path.name
        assert other.read_bytes() == path.read_bytes(), f"{path.name} not idempotent"
