#!/usr/bin/env python3
"""Extract a RPG Maker XP RGSSAD v1 archive (e.g. Uranium.rgssad).

Format reference: https://www.cyberunderground.net/?p=144 and Essentials docs.
Archive layout (after the 8-byte "RGSSAD\\0\\1" header):

    repeat until EOF:
        u32 name_len    (XOR with key, then advance key)
        u8  name[name_len]   (each byte XOR low-byte of key, advance per byte)
        u32 file_size   (XOR with key, then advance key)
        u8  data[file_size]  (XOR per 4-byte group with file_key,
                              file_key starts as global key and advances per group;
                              global key is unchanged by file data)

Key advancement: key = (key * 7 + 3) & 0xFFFFFFFF. Initial key: 0xDEADCAFE.

Usage:
    python scripts/extract_rgssad.py <archive.rgssad> <output_dir>
"""
import struct
import sys
from pathlib import Path

INITIAL_KEY = 0xDEADCAFE
HEADER = b"RGSSAD\x00\x01"


def advance(key: int) -> int:
    return (key * 7 + 3) & 0xFFFFFFFF


def extract(archive: Path, out_dir: Path) -> list[tuple[str, int]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    entries: list[tuple[str, int]] = []
    data = archive.read_bytes()
    if data[:8] != HEADER:
        raise ValueError(f"Not an RGSSAD v1 archive: header={data[:8]!r}")

    pos = 8
    key = INITIAL_KEY
    n = len(data)

    while pos < n:
        if pos + 4 > n:
            break
        name_len = struct.unpack_from("<I", data, pos)[0] ^ key
        key = advance(key)
        pos += 4

        if name_len == 0 or name_len > 4096 or pos + name_len > n:
            raise ValueError(f"Implausible name_len={name_len} at pos={pos}")
        name_bytes = bytearray(data[pos : pos + name_len])
        for i in range(name_len):
            name_bytes[i] ^= key & 0xFF
            key = advance(key)
        pos += name_len
        # Try cp1252 first; RPG Maker XP on Windows commonly uses it.
        try:
            name = name_bytes.decode("cp1252")
        except UnicodeDecodeError:
            name = name_bytes.decode("utf-8", errors="replace")

        if pos + 4 > n:
            raise ValueError(f"Truncated archive before file_size for {name!r}")
        file_size = struct.unpack_from("<I", data, pos)[0] ^ key
        key = advance(key)
        pos += 4

        if pos + file_size > n:
            raise ValueError(
                f"Truncated archive: {name!r} claims {file_size} bytes, only "
                f"{n - pos} remain"
            )

        file_key = key
        file_data = bytearray(data[pos : pos + file_size])
        for i in range(0, file_size, 4):
            kb = file_key
            for j in range(4):
                if i + j >= file_size:
                    break
                file_data[i + j] ^= kb & 0xFF
                kb >>= 8
            file_key = advance(file_key)
        pos += file_size

        # Normalize Windows separators to POSIX
        rel_path = name.replace("\\", "/")
        out_path = out_dir / rel_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(file_data)
        entries.append((rel_path, file_size))

    return entries


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    archive = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])
    if not archive.is_file():
        print(f"Error: {archive} not found", file=sys.stderr)
        return 1
    entries = extract(archive, out_dir)
    print(f"Extracted {len(entries)} files to {out_dir}")
    total = sum(s for _, s in entries)
    print(f"Total uncompressed size: {total:,} bytes")
    # Spot-check the top-level directories present
    top = sorted({e[0].split("/", 1)[0] for e in entries})
    print(f"Top-level entries: {top}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
