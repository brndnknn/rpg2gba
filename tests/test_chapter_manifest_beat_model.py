"""`chapter_manifest.beat_model` -- the concrete `checker.BeatModel`.

The adapter answers two questions for D2 ("every `beat:Bn` disposition must
name a beat that is actually registered"): is a beat id registered, and if
not, was it deferred and why. Its interesting behaviour is the family-prefix
match (a `beat_prefix="B4"` template registers `B4_battle`, `B4_retalk`,
..., all of which satisfy a plain `B4` disposition) and the degrade path --
no playtest module at all is unenforced, everything else raises.

Chapter modules are faked into `sys.modules` the way
`tests/test_chapter_manifest_route_model.py` does, so no real chapter module
(and no ROM) is needed, except for one test that pins down real `ch04`'s
known-deferred state.
"""
from __future__ import annotations

import sys
import types

import pytest

from rpg2gba.chapter_manifest.beat_model import ChapterBeatModel, build_beat_model
from rpg2gba.playtest.chapter import ChapterBuilder

PKG = "rpg2gba.playtest.chapters"


def _run(emu: object) -> None:  # pragma: no cover - never executed
    raise AssertionError("beat body must not run in this test")


def _install_chapter(
    name: str, beat_names: list[str], *, deferred: tuple = (),
) -> None:
    """Fake a chapter module with the given registered beats and, optionally,
    a `DEFERRED_BEATS` tuple of raw entries (passed through verbatim so a
    test can deliberately install a malformed one)."""
    builder = ChapterBuilder(name, f"{name} test chapter")
    for beat_name in beat_names:
        builder.beat(beat_name, f"{beat_name} description",
                     map_constant="MAP_G1", at=(1, 1))(_run)

    module = types.ModuleType(f"{PKG}.{name}")
    module.CHAPTER = builder.build()  # type: ignore[attr-defined]
    if deferred:
        module.DEFERRED_BEATS = deferred  # type: ignore[attr-defined]
    sys.modules[f"{PKG}.{name}"] = module


def _cleanup_chapter(name: str) -> None:
    sys.modules.pop(f"{PKG}.{name}", None)


def test_plain_name_beat_is_registered_with_no_deferral_reason() -> None:
    _install_chapter("beatplace1", ["B4"])
    try:
        model = build_beat_model("beatplace1")
        assert isinstance(model, ChapterBeatModel)
        assert model.is_registered("B4") is True
        assert model.deferral_reason("B4") is None
    finally:
        _cleanup_chapter("beatplace1")


def test_prefixed_template_family_satisfies_the_bare_id() -> None:
    _install_chapter("beatplace2", ["B4_battle", "B4_retalk"])
    try:
        model = build_beat_model("beatplace2")
        assert model is not None
        assert model.is_registered("B4") is True
    finally:
        _cleanup_chapter("beatplace2")


def test_b4_is_not_satisfied_by_a_registered_b14() -> None:
    _install_chapter("beatplace3", ["B14"])
    try:
        model = build_beat_model("beatplace3")
        assert model is not None
        assert model.is_registered("B4") is False
    finally:
        _cleanup_chapter("beatplace3")


def test_deferred_beat_is_not_registered_and_reports_its_reason() -> None:
    _install_chapter(
        "beatplace4", ["B1"],
        deferred=(("B8", "needs a harness primitive that doesn't exist", _run),),
    )
    try:
        model = build_beat_model("beatplace4")
        assert model is not None
        assert model.is_registered("B8") is False
        assert model.deferral_reason("B8") == (
            "needs a harness primitive that doesn't exist")
    finally:
        _cleanup_chapter("beatplace4")


def test_unknown_beat_id_is_neither_registered_nor_deferred() -> None:
    _install_chapter("beatplace5", ["B1"])
    try:
        model = build_beat_model("beatplace5")
        assert model is not None
        assert model.is_registered("B99") is False
        assert model.deferral_reason("B99") is None
    finally:
        _cleanup_chapter("beatplace5")


def test_returns_none_when_no_playtest_module_exists() -> None:
    assert build_beat_model("CH_NO_SUCH_CHAPTER") is None


def test_malformed_deferred_beats_entry_raises_rather_than_skipping() -> None:
    _install_chapter("beatplace6", ["B1"], deferred=(("B8", "reason only two"),))
    try:
        with pytest.raises(TypeError):
            build_beat_model("beatplace6")
    finally:
        _cleanup_chapter("beatplace6")


def test_real_ch04_has_b8_and_b10_deferred_and_unregistered() -> None:
    """Pinned against real `ch04.py` state as of CLAUDE.md's D2 background:
    `CH04.dispositions.json` disposes `beat:B8` and `beat:B10`, while
    `ch04.py`'s `DEFERRED_BEATS` lists both -- this is the exact silent
    contradiction D2 exists to catch. If this test breaks because ch04 has
    since registered B8 or B10 for real, that's good news; update the
    assertion."""
    model = build_beat_model("CH04")
    assert model is not None
    assert model.is_registered("B8") is False
    assert model.deferral_reason("B8") is not None
    assert model.is_registered("B10") is False
    assert model.deferral_reason("B10") is not None
