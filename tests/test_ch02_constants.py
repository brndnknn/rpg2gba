"""Symbol lint for `rpg2gba.playtest.chapters.ch02`.

Every `FLAG_*`/`VAR_*`/`MAP_*`/`TRAINER_*`/`SPECIES_* name-or-expression the
route1 chapter module resolves at runtime is collected in its module-level
`ALL_CONSTANTS` tuple. This test probes all of them through the real
preprocessor (`offsets.probe_constants`), so a bad symbol -- an invented
`FLAG_*`, a trainer id that doesn't exist, a stale expression -- is caught by
a fast compile instead of by a long emulator run.

Needs the built engine (specifically the generated `uranium_flags.h`) and the
devkitARM toolchain; skipped when either is absent, mirroring
`tests/test_playtest.py`'s `needs_probe`.

The `rpg2gba.playtest.chapters.ch02` import is deliberately deferred to
inside each test body, not hoisted to module level. CH02 chains onto CH01 as
its predecessor (`ChapterBuilder(..., predecessor="CH01")`), so importing it
caches `rpg2gba.playtest.chapters.ch01` in `sys.modules` as a side effect.
`tests/test_chapter_predecessor.py` installs *fake* modules under that same
`rpg2gba.playtest.chapters.*` namespace. A bare top-level import here would
populate that cache during *collection* -- pytest imports every test module
before running any of them -- which puts the real `ch01` in `sys.modules`
before a single test has run, in every ordering. Importing lazily inside the
test body keeps cache population at this test's own run time.

**This does not depend on file order, and must not be rewritten to.** It used
to say the deferral was safe because this file sorted last; after the
2026-09-01 rename to chapter ids that is no longer even true
(`test_ch01_chapter.py` now sorts *before* `test_chapter_predecessor.py`,
since `ch0` < `cha`), and the claim was doing no work anyway. What actually
makes cross-test leakage impossible is `test_chapter_predecessor.py`'s
`_clean_sys_modules` fixture, which **restores** a key it overwrote to the
object that was there before, rather than only deleting keys it added. The
deferral here is defence in depth against collection-time caching, not a
dependency on which file runs first.
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
    from rpg2gba.playtest.chapters.ch02 import ALL_CONSTANTS

    values = probe_constants(ENGINE, ALL_CONSTANTS)
    assert set(values) == set(ALL_CONSTANTS)


def test_all_constants_nonempty() -> None:
    from rpg2gba.playtest.chapters.ch02 import ALL_CONSTANTS

    # Sanity check independent of the engine build: the lint surface itself
    # should never silently shrink to nothing.
    assert len(ALL_CONSTANTS) >= 20
