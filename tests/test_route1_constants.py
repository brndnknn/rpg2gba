"""Symbol lint for `rpg2gba.playtest.chapters.route1`.

Every `FLAG_*`/`VAR_*`/`MAP_*`/`TRAINER_*`/`SPECIES_* name-or-expression the
route1 chapter module resolves at runtime is collected in its module-level
`ALL_CONSTANTS` tuple. This test probes all of them through the real
preprocessor (`offsets.probe_constants`), so a bad symbol -- an invented
`FLAG_*`, a trainer id that doesn't exist, a stale expression -- is caught by
a fast compile instead of by a long emulator run.

Needs the built engine (specifically the generated `uranium_flags.h`) and the
devkitARM toolchain; skipped when either is absent, mirroring
`tests/test_playtest.py`'s `needs_probe`.

The `rpg2gba.playtest.chapters.route1` import is deliberately deferred to
inside each test body, not hoisted to module level. `route1` chains onto
`moki` as its predecessor (`ChapterBuilder(..., predecessor="moki")`), so
importing it caches `rpg2gba.playtest.chapters.moki` in `sys.modules` as a
side effect. `tests/test_chapter_predecessor.py` installs *fake* modules
under that same `rpg2gba.playtest.chapters.*` namespace and its cleanup
fixture only removes keys that were *not already present* at test setup --
so if `chapters.moki` were cached during collection (a bare top-level import
here would do exactly that, since pytest imports all test modules before
running any of them), a fake `moki` installed by that other test would leak
into every later test that resolves the real `moki` chapter. Importing here
lazily, inside the test function, means the cache population happens at this
test's run time -- after test_chapter_predecessor.py's and
test_moki_chapter.py's tests have already run to completion in normal
alphabetical file order -- so it can't feed that landmine.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from rpg2gba.playtest.offsets import probe_constants
from rpg2gba.playtest.symbols import DEVKITARM_BIN

ENGINE = Path(__file__).resolve().parents[1] / "engine"

needs_probe = pytest.mark.skipif(
    not (DEVKITARM_BIN / "arm-none-eabi-gcc").exists()
    or not (ENGINE / "include").exists()
    or not (ENGINE / "data" / "scripts" / "uranium_flags.h").exists(),
    reason="needs devkitARM toolchain and a built engine (uranium_flags.h)",
)


@needs_probe
def test_route1_constants_resolve() -> None:
    from rpg2gba.playtest.chapters.route1 import ALL_CONSTANTS

    values = probe_constants(ENGINE, ALL_CONSTANTS)
    assert set(values) == set(ALL_CONSTANTS)


def test_all_constants_nonempty() -> None:
    from rpg2gba.playtest.chapters.route1 import ALL_CONSTANTS

    # Sanity check independent of the engine build: the lint surface itself
    # should never silently shrink to nothing.
    assert len(ALL_CONSTANTS) >= 20
