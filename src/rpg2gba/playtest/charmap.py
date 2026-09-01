"""The one inversion of `engine/charmap.txt` for decoding ROM text.

`charmap.txt` is written for the *forward* direction the assembler needs
(character -> byte), and it is not injective: the same byte range is reused
by more than one glyph set, so a blind `dict` inversion is wrong.

Two distinct collisions matter here:

* **Section reuse.** A `@ Hiragana` section partway down the file maps
  different characters onto bytes the Latin table already used -- byte 0x01
  is both `'A`` and `'あ'`. `load_charmap` parses the whole file, so
  `char_to_byte` legitimately holds both. This build's ROM prints English
  (`ENG`, not `JPN`), so the Latin section -- which comes first in the file
  -- is what is actually on screen.
* **Duplicate glyphs inside the Latin table.** Byte `B4` is defined twice in
  immediate succession, as `'’'` (U+2019) and then as `'\''` (ASCII). One
  byte, two spellings, and the ROM cannot tell you which was meant.

Keeping the *first* character seen per byte resolves both: it selects the
Latin section, and it fixes a single deterministic spelling for a duplicated
glyph. The consequence for callers is worth stating plainly, because it is
counter-intuitive and it bit us once already (commit `2a4e4b61`): **decoded
ROM text spells an apostrophe U+2019, even though Uranium's source spells it
ASCII.** There is no U+2019 anywhere in the decoded Uranium corpus; the curly
quote is manufactured here, by this choice. Anything comparing source text to
screen text must normalize through `rom_decoded_char_table` rather than
assume the two agree.

This module exists so that inversion has exactly one implementation. It
deliberately imports nothing that pulls in `mgba`: `playtest.emulator` cannot
be imported at all without the emulator installed, and the offline text
resolver needs the same table.
"""

from __future__ import annotations

from pathlib import Path

from rpg2gba.text_validator.engine_metrics import load_charmap


def invert_charmap_english_first(char_to_byte: dict[str, int]) -> dict[int, str]:
    """byte -> the first character defined for it in `charmap.txt` file order.

    See the module docstring for why "first" is the correct rule and not an
    arbitrary tie-break.
    """
    byte_to_char: dict[int, str] = {}
    for char, byte in char_to_byte.items():
        if byte not in byte_to_char:
            byte_to_char[byte] = char
    return byte_to_char


def byte_to_char_table(engine_dir: Path) -> dict[int, str]:
    """The decode table for `engine_dir/charmap.txt`."""
    charmap_path = engine_dir / "charmap.txt"
    if not charmap_path.is_file():
        raise FileNotFoundError(
            f"no charmap at {charmap_path} -- RPG2GBA_POKEEMERALD should point "
            f"at the vendored engine/ tree (see .env-paths; never set it by hand)"
        )
    return invert_charmap_english_first(load_charmap(charmap_path).char_to_byte)
