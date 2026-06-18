"""Scan Poryscript dialogue against the GBA charmap; report unrepresentable chars.

Parses the single-character glyph entries from pokeemerald's charmap.txt, then
walks every double-quoted string literal in the given .pory files and flags any
character that has no charmap mapping (after stripping {PLACEHOLDERS} and
\\n/\\l/\\p escape sequences). This catches the "compile-clean-but-broken" class
where poryscript passes text through but arm-as later dies on "unknown character".
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

from rpg2gba.tileset_converter.assembly import load_charmap_chars

# Placeholders {PLAYER}, {STR_VAR_1}, {COLOR RED}, ... — preproc handles these.
_PLACEHOLDER_RE = re.compile(r"\{[^}]*\}")
# Poryscript/asm escapes that are valid inside a string.
_ESCAPE_RE = re.compile(r"\\[nlp]")
# Double-quoted string literal, escaped-quote aware: "(...)" with \" allowed inside.
_STRING_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')


def scan_file(path: Path, allowed: set[str]) -> list[tuple[int, str, str]]:
    """Return (lineno, badchars, line_text) for lines with unrepresentable chars."""
    findings: list[tuple[int, str, str]] = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = raw.lstrip()
        if stripped.startswith("#"):  # poryscript comment — never reaches asm
            continue
        for s in _STRING_RE.findall(raw):
            s = _PLACEHOLDER_RE.sub("", s)
            s = _ESCAPE_RE.sub("", s)
            s = s.replace('\\"', '"').replace("\\\\", "\\")  # unescape -> real chars
            bad = [c for c in s if c not in allowed]
            if bad:
                findings.append((lineno, "".join(bad), raw.strip()))
    return findings


def main() -> int:
    charmap = Path("/home/b/repos/pokeemerald-expansion/charmap.txt")
    allowed = load_charmap_chars(charmap)

    files = [Path(a) for a in sys.argv[1:]]
    if not files:
        print("usage: charmap_lint.py <file.pory> ...", file=sys.stderr)
        return 2

    total = Counter()
    any_bad = False
    for f in sorted(files):
        findings = scan_file(f, allowed)
        if not findings:
            continue
        any_bad = True
        print(f"\n=== {f} ===")
        for lineno, bad, text in findings:
            uni = " ".join(f"U+{ord(c):04X}({c!r})" for c in dict.fromkeys(bad))
            total.update(bad)
            print(f"  L{lineno}: [{uni}]  {text[:90]}")

    print("\n=== SUMMARY: unrepresentable char counts ===")
    if not total:
        print("  (none)")
    for c, n in total.most_common():
        print(f"  U+{ord(c):04X} {c!r}: {n}")
    return 1 if any_bad else 0


if __name__ == "__main__":
    sys.exit(main())
