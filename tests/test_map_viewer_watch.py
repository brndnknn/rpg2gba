"""Tests for the map viewer server's hot-reload watcher (PROJECT_TODO.md #12).

Only the three pure/near-pure seam functions are exercised --
`_watched_files`, `_snapshot`, `_changed_paths` -- never `os.execv`, the real
background thread, or a bound socket.  Importing `map_viewer_server` also
transitively imports `map_viewer_common`, which a different agent may be
editing concurrently in this session; if that import ever breaks mid-session,
prefer fixing the concurrent edit over reaching around it here, since by the
time this suite runs in CI both edits are expected to be complete.
"""
from __future__ import annotations

import os
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from map_viewer_server import _changed_paths, _snapshot, _watched_files  # noqa: E402

# ---------------------------------------------------------------------------
# _changed_paths
# ---------------------------------------------------------------------------


def test_changed_paths_detects_stat_diff() -> None:
    old = {"/a.py": (100, 10)}
    new = {"/a.py": (200, 10)}
    assert _changed_paths(old, new) == ["/a.py"]


def test_changed_paths_detects_disappearance() -> None:
    old = {"/a.py": (100, 10)}
    new: dict[str, tuple[int, int]] = {}
    assert _changed_paths(old, new) == ["/a.py"]


def test_changed_paths_new_path_not_reported() -> None:
    # A path present in `new` but absent from `old` is the watch set growing
    # (a lazy import mid-session), not a change -- must not be reported, or
    # every lazy import would trigger a restart-loop.
    old: dict[str, tuple[int, int]] = {}
    new = {"/new.py": (100, 10)}
    assert _changed_paths(old, new) == []


def test_changed_paths_empty_to_empty_no_changes() -> None:
    assert _changed_paths({}, {}) == []


def test_changed_paths_unchanged_path_not_reported() -> None:
    old = {"/a.py": (100, 10)}
    new = {"/a.py": (100, 10)}
    assert _changed_paths(old, new) == []


# ---------------------------------------------------------------------------
# _snapshot
# ---------------------------------------------------------------------------


def test_snapshot_records_mtime_and_size(tmp_path: Path) -> None:
    f = tmp_path / "a.py"
    f.write_text("x = 1\n", encoding="utf-8")
    st = f.stat()

    snap = _snapshot([f])

    assert snap == {str(f): (st.st_mtime_ns, st.st_size)}


def test_snapshot_omits_missing_file(tmp_path: Path) -> None:
    # Pinned behavior: a path that can't be stat'd is simply excluded from
    # the result dict, not recorded under a sentinel value.
    missing = tmp_path / "does_not_exist.py"

    snap = _snapshot([missing])

    assert snap == {}


def test_snapshot_mixed_existing_and_missing(tmp_path: Path) -> None:
    present = tmp_path / "present.py"
    present.write_text("x = 1\n", encoding="utf-8")
    missing = tmp_path / "missing.py"

    snap = _snapshot([present, missing])

    assert list(snap.keys()) == [str(present)]


# ---------------------------------------------------------------------------
# _snapshot + _changed_paths, end to end via os.utime
# ---------------------------------------------------------------------------


def test_mtime_bump_detected_end_to_end(tmp_path: Path) -> None:
    f = tmp_path / "a.py"
    f.write_text("x = 1\n", encoding="utf-8")

    before = _snapshot([f])

    st = f.stat()
    # Bump mtime by a whole second (well past filesystem timestamp
    # resolution) without changing size, so only the mtime differs.
    os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))

    after = _snapshot([f])

    assert _changed_paths(before, after) == [str(f)]


def test_no_bump_no_change_end_to_end(tmp_path: Path) -> None:
    f = tmp_path / "a.py"
    f.write_text("x = 1\n", encoding="utf-8")

    before = _snapshot([f])
    after = _snapshot([f])

    assert _changed_paths(before, after) == []


# ---------------------------------------------------------------------------
# _watched_files
# ---------------------------------------------------------------------------


def test_watched_files_includes_only_files_under_root(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    inside_dir = root / "scripts"
    inside_dir.mkdir(parents=True)
    inside_file = inside_dir / "inside_mod.py"
    inside_file.write_text("x = 1\n", encoding="utf-8")

    outside_dir = tmp_path / "elsewhere"
    outside_dir.mkdir()
    outside_file = outside_dir / "outside_mod.py"
    outside_file.write_text("x = 1\n", encoding="utf-8")

    fake_inside = types.SimpleNamespace(__file__=str(inside_file))
    fake_outside = types.SimpleNamespace(__file__=str(outside_file))

    sys.modules["_fake_inside_mod_for_test"] = fake_inside
    sys.modules["_fake_outside_mod_for_test"] = fake_outside
    try:
        watched = _watched_files(root)
    finally:
        del sys.modules["_fake_inside_mod_for_test"]
        del sys.modules["_fake_outside_mod_for_test"]

    assert inside_file.resolve() in watched
    assert outside_file.resolve() not in watched


def test_watched_files_excludes_venv_and_pycache(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    venv_dir = root / ".venv" / "lib"
    venv_dir.mkdir(parents=True)
    venv_file = venv_dir / "site_mod.py"
    venv_file.write_text("x = 1\n", encoding="utf-8")

    pycache_dir = root / "scripts" / "__pycache__"
    pycache_dir.mkdir(parents=True)
    pycache_file = pycache_dir / "cached_mod.py"
    pycache_file.write_text("x = 1\n", encoding="utf-8")

    plain_dir = root / "scripts"
    plain_file = plain_dir / "plain_mod.py"
    plain_file.write_text("x = 1\n", encoding="utf-8")

    fake_venv = types.SimpleNamespace(__file__=str(venv_file))
    fake_pycache = types.SimpleNamespace(__file__=str(pycache_file))
    fake_plain = types.SimpleNamespace(__file__=str(plain_file))

    sys.modules["_fake_venv_mod_for_test"] = fake_venv
    sys.modules["_fake_pycache_mod_for_test"] = fake_pycache
    sys.modules["_fake_plain_mod_for_test"] = fake_plain
    try:
        watched = _watched_files(root)
    finally:
        del sys.modules["_fake_venv_mod_for_test"]
        del sys.modules["_fake_pycache_mod_for_test"]
        del sys.modules["_fake_plain_mod_for_test"]

    assert venv_file.resolve() not in watched
    assert pycache_file.resolve() not in watched
    assert plain_file.resolve() in watched


def test_watched_files_ignores_non_py_and_no_file_modules(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    data_file = root / "data.json"
    data_file.write_text("{}", encoding="utf-8")

    fake_non_py = types.SimpleNamespace(__file__=str(data_file))
    fake_no_file = types.SimpleNamespace()  # no __file__ attribute at all

    sys.modules["_fake_non_py_mod_for_test"] = fake_non_py
    sys.modules["_fake_no_file_mod_for_test"] = fake_no_file
    try:
        watched = _watched_files(root)
    finally:
        del sys.modules["_fake_non_py_mod_for_test"]
        del sys.modules["_fake_no_file_mod_for_test"]

    assert data_file.resolve() not in watched
