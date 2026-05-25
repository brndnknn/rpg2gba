"""Poryscript compile-gate (Phase 4 §4.2).

Every event's generated Poryscript must compile through the `poryscript` binary
before the orchestrator accepts it (decision F5). This module is a thin wrapper:
resolve the binary, shell out, return a structured result. The compiler's error
message is fed back into the retry prompt on the first failure.

The binary is **not** bundled in the fork or this repo. Obtain a pinned release
from huderlem/poryscript and either put it on `PATH` or point
`RPG2GBA_PORYSCRIPT` at it (PHASE4_PLAN P2).
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class CompileResult:
    ok: bool
    stdout: str
    stderr: str


class PoryscriptUnavailable(RuntimeError):
    """Raised when no poryscript binary can be found."""


def binary_path() -> Path:
    """Resolve the poryscript binary, or fail loud with an install hint."""
    env = os.environ.get("RPG2GBA_PORYSCRIPT")
    if env:
        p = Path(env)
        if p.is_file():
            return p
        raise PoryscriptUnavailable(f"RPG2GBA_PORYSCRIPT={env} is not a file")
    found = shutil.which("poryscript")
    if found:
        return Path(found)
    raise PoryscriptUnavailable(
        "poryscript not found. Download a pinned release from "
        "https://github.com/huderlem/poryscript/releases, then put it on PATH "
        "or set RPG2GBA_PORYSCRIPT to its path (PHASE4_PLAN P2)."
    )


def is_available() -> bool:
    """True if the binary can be resolved (for skip-markers in tests)."""
    try:
        binary_path()
        return True
    except PoryscriptUnavailable:
        return False


def compile_script(script: str) -> CompileResult:
    """Compile a Poryscript string; return success + captured compiler output.

    Does not raise on a *compile* error (that's an expected outcome the
    orchestrator handles via retry/queue) — only raises if the binary is missing.
    """
    binary = binary_path()
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "event.pory"
        out = Path(td) / "event.inc"
        src.write_text(script, encoding="utf-8")
        proc = subprocess.run(
            [str(binary), "-i", str(src), "-o", str(out)],
            capture_output=True,
            text=True,
        )
    ok = proc.returncode == 0
    if not ok:
        logger.debug("poryscript rejected script: %s", proc.stderr.strip())
    return CompileResult(ok=ok, stdout=proc.stdout, stderr=proc.stderr)
