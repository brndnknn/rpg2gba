"""Unit tests for `pbs_converter._binary`.

These tests are env-independent — no Uranium data required.
"""
from __future__ import annotations

import struct
from pathlib import Path

import pytest

from rpg2gba.pbs_converter._binary import (
    BinaryReadError,
    DatReader,
    parse_indexed,
)


def _write_bytes(tmp_path: Path, name: str, data: bytes) -> Path:
    p = tmp_path / name
    p.write_bytes(data)
    return p


def test_uint_reads_little_endian(tmp_path: Path) -> None:
    raw = bytes([0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07])
    r = DatReader(_write_bytes(tmp_path, "u.dat", raw))
    assert r.b() == 0x01
    assert r.w() == 0x0302
    assert r.dw() == 0x07060504
    assert r.eof


def test_signed_reads(tmp_path: Path) -> None:
    r = DatReader(_write_bytes(tmp_path, "s.dat", bytes([0xFF, 0xFE, 0xFF])))
    assert r.sb() == -1
    assert r.sw() == -2


def test_bytes_and_seek(tmp_path: Path) -> None:
    r = DatReader(_write_bytes(tmp_path, "b.dat", b"ABCDEFGH"))
    assert r.bytes(3) == b"ABC"
    r.seek(6)
    assert r.bytes(2) == b"GH"
    assert r.eof


def test_at_returns_independent_slice(tmp_path: Path) -> None:
    r = DatReader(_write_bytes(tmp_path, "a.dat", b"0123456789"))
    sub = r.at(2, 4)
    assert sub.bytes(4) == b"2345"
    # parent reader unaffected by the sub-read
    assert r.pos == 0


def test_eof_raises_with_path_and_offset(tmp_path: Path) -> None:
    r = DatReader(_write_bytes(tmp_path, "eof.dat", b"\x01"))
    r.b()
    with pytest.raises(BinaryReadError) as exc:
        r.b()
    assert "eof.dat" in str(exc.value)
    assert "offset 1" in str(exc.value)


def test_at_out_of_range_raises(tmp_path: Path) -> None:
    r = DatReader(_write_bytes(tmp_path, "oor.dat", b"\x00\x01\x02"))
    with pytest.raises(BinaryReadError):
        r.at(2, 10)


def test_decode_int_single_byte(tmp_path: Path) -> None:
    # encodeInt(strm, 5) writes a single byte 0x05 (high bit clear)
    r = DatReader(_write_bytes(tmp_path, "i.dat", bytes([0x05])))
    assert r._decode_int() == 5


def test_decode_int_multi_byte(tmp_path: Path) -> None:
    # encodeInt(strm, 200) → 200 > 127, so emit 0x80 | (200 & 0x7F) = 0xC8,
    # then emit 200 >> 7 = 1 → bytes(0xC8, 0x01) = 200
    r = DatReader(_write_bytes(tmp_path, "i2.dat", bytes([0xC8, 0x01])))
    assert r._decode_int() == 200


def test_string_decode_ascii(tmp_path: Path) -> None:
    body = b"hello"
    r = DatReader(_write_bytes(tmp_path, "s1.dat", bytes([len(body)]) + body))
    assert r.s() == "hello"


def test_string_decode_windows_1252(tmp_path: Path) -> None:
    # Windows-1252 0xE9 = 'é', 0x97 = em-dash. Both are valid Win-1252,
    # invalid UTF-8 in a strict decoder.
    body = bytes([0xE9, 0x97])
    r = DatReader(_write_bytes(tmp_path, "s2.dat", bytes([len(body)]) + body))
    s = r.s()
    assert s == "é—"


# ---------- parse_indexed ----------

def _build_indexed_file(entries: list[list[int]], entry_size_bytes: int) -> bytes:
    """Build an Essentials-style indexed file with uint16 entries.

    `entries[i]` is the list of uint16 values for species (i+1). Header is
    `len(entries) × 8` bytes of (uint32 offset, uint32 length-as-element-count).
    """
    header = bytearray()
    body = bytearray()
    header_size = len(entries) * 8
    for vals in entries:
        offset = header_size + len(body)
        header += struct.pack("<II", offset, len(vals))
        for v in vals:
            body += struct.pack("<H", v)
    return bytes(header) + bytes(body)


def test_parse_indexed_basic(tmp_path: Path) -> None:
    raw = _build_indexed_file([[100, 200], [300], []], entry_size_bytes=2)
    path = _write_bytes(tmp_path, "idx.dat", raw)

    def body_parser(blob: bytes, index: int, stored_length: int) -> list[int]:
        assert len(blob) == stored_length * 2
        return list(struct.unpack(f"<{stored_length}H", blob))

    out = parse_indexed(path, species_count=3, body_parser=body_parser, length_unit_bytes=2)
    assert out[0] is None  # 1-based indexing
    assert out[1] == [100, 200]
    assert out[2] == [300]
    assert out[3] is None  # empty entry
