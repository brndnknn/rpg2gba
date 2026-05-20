"""Stream reader for Essentials' custom binary `.dat` format.

Essentials writes `.dat` files via `fputb`/`fputw`/`fputdw` helpers (1/2/4-byte
unsigned little-endian) and `encodeString` (length-prefixed UTF-8/Win-1252).
The schema for each file lives in `reference/scripts_dump/175__Compiler.rb`.

Fails loud per CLAUDE.md §4.5 — any read past EOF or schema-violating value
raises `BinaryReadError` with the file path and byte offset.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable


class BinaryReadError(Exception):
    """Raised on EOF, malformed input, or schema violation."""


@dataclass
class IndexedEntry:
    """One entry from an indexed `.dat` (offset+length header → body slice)."""

    index: int           # 1-based species/move/item ID matching Compiler.rb's `for i in 1..mx`
    offset: int          # absolute byte offset into the file where this entry's body starts
    stored_length: int   # raw value from the length field — interpretation depends on file
    body: bytes          # the byte slice for this entry's payload


class DatReader:
    """Cursor over a byte buffer matching Essentials' `fputb`/`fputw`/`fputdw`.

    Two ways to construct:
      DatReader(path)               — read whole file into memory
      DatReader.from_bytes(buf, src) — wrap an existing buffer (used by `at()`)
    """

    __slots__ = ("_buf", "_pos", "_src")

    def __init__(self, path: Path | str) -> None:
        path = Path(path)
        self._buf = path.read_bytes()
        self._pos = 0
        self._src = str(path)

    @classmethod
    def from_bytes(cls, buf: bytes, src: str = "<bytes>") -> "DatReader":
        obj = cls.__new__(cls)
        obj._buf = buf
        obj._pos = 0
        obj._src = src
        return obj

    @property
    def size(self) -> int:
        return len(self._buf)

    @property
    def pos(self) -> int:
        return self._pos

    @property
    def remaining(self) -> int:
        return len(self._buf) - self._pos

    @property
    def eof(self) -> bool:
        return self._pos >= len(self._buf)

    def seek(self, offset: int) -> None:
        if offset < 0 or offset > len(self._buf):
            raise BinaryReadError(
                f"{self._src}: seek out of range — offset={offset}, size={len(self._buf)}"
            )
        self._pos = offset

    def at(self, offset: int, length: int | None = None) -> "DatReader":
        """Return a new reader over a slice of the underlying buffer."""
        end = len(self._buf) if length is None else offset + length
        if offset < 0 or end > len(self._buf):
            raise BinaryReadError(
                f"{self._src}: slice out of range — offset={offset}, length={length}, "
                f"size={len(self._buf)}"
            )
        return DatReader.from_bytes(self._buf[offset:end], src=f"{self._src}@{offset}")

    def _need(self, n: int) -> None:
        if self._pos + n > len(self._buf):
            raise BinaryReadError(
                f"{self._src}: read of {n} bytes at offset {self._pos} would pass EOF "
                f"(size={len(self._buf)})"
            )

    def b(self) -> int:
        self._need(1)
        v = self._buf[self._pos]
        self._pos += 1
        return v

    def sb(self) -> int:
        """Signed int8."""
        v = self.b()
        return v - 256 if v >= 128 else v

    def w(self) -> int:
        self._need(2)
        v = int.from_bytes(self._buf[self._pos:self._pos + 2], "little", signed=False)
        self._pos += 2
        return v

    def sw(self) -> int:
        """Signed int16 LE."""
        self._need(2)
        v = int.from_bytes(self._buf[self._pos:self._pos + 2], "little", signed=True)
        self._pos += 2
        return v

    def dw(self) -> int:
        self._need(4)
        v = int.from_bytes(self._buf[self._pos:self._pos + 4], "little", signed=False)
        self._pos += 4
        return v

    def bytes(self, n: int) -> bytes:
        self._need(n)
        v = self._buf[self._pos:self._pos + n]
        self._pos += n
        return v

    def s(self) -> str:
        """Length-prefixed string per Compiler.rb `encodeString`/`decodeString`.

        `decodeString` reads a variable-length integer (via `decodeInt`/`encodeInt`)
        then that many bytes. Bytes are decoded as Windows-1252 (Uranium's encoding)
        with fallback to UTF-8 if the codepoints are all ASCII.
        """
        length = self._decode_int()
        raw = self.bytes(length)
        try:
            return raw.decode("windows-1252")
        except UnicodeDecodeError as exc:
            raise BinaryReadError(
                f"{self._src}: string decode failed at offset {self._pos - length}: {exc}"
            )

    def _decode_int(self) -> int:
        """Variable-length integer per Compiler.rb `decodeInt`.

        Reads a sequence of bytes where each byte's high bit indicates 'more bytes
        follow'. The low 7 bits are accumulated into the result, little-endian.
        """
        result = 0
        shift = 0
        while True:
            byte = self.b()
            if byte & 0x80:
                result |= (byte & 0x7F) << shift
                shift += 7
            else:
                result |= byte << shift
                return result


def parse_indexed(
    path: Path | str,
    species_count: int,
    body_parser: Callable[[bytes, int, int], object],
    *,
    length_unit_bytes: int | None = None,
) -> list[object]:
    """Parse Essentials' recurring "indexed file" layout.

    Layout: `species_count × 8` bytes of `(uint32 offset, uint32 stored_length)` header,
    then per-species body blobs. `body_parser(body_bytes, index, stored_length)` is
    called once per non-empty entry. Returns a list keyed by 1-based index
    (index 0 is always `None`).

    The stored `length` field's semantics differ per file — see plan §"Cross-cutting
    components" table. `length_unit_bytes`, if given, is used to validate that
    `stored_length × length_unit_bytes` matches the byte distance to the next entry.
    """
    reader = DatReader(path)
    headers: list[tuple[int, int]] = []
    for _ in range(species_count):
        offset = reader.dw()
        length = reader.dw()
        headers.append((offset, length))

    results: list[object | None] = [None] * (species_count + 1)
    for i, (offset, stored_length) in enumerate(headers, start=1):
        if stored_length == 0:
            continue
        body_byte_length = (
            stored_length * length_unit_bytes if length_unit_bytes is not None else None
        )
        if body_byte_length:
            body = reader.at(offset, body_byte_length).bytes(body_byte_length)
        else:
            body = reader.at(offset).bytes(reader.size - offset)
        results[i] = body_parser(body, i, stored_length)
    return results
