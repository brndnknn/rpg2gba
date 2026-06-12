"""One-off 1.5b check: corpus-wide duplicate script-label scan over emitted .pory."""
import re
from collections import Counter
from pathlib import Path

scripts_dir = Path("output/uranium-build/scripts")
label_re = re.compile(r"^\s*(?:script|text|movement|mapscripts)\s+(\w+)", re.M)

counts: Counter[str] = Counter()
per_file: dict[str, list[str]] = {}
for pory in sorted(scripts_dir.glob("*.pory")):
    labels = label_re.findall(pory.read_text(encoding="utf-8"))
    counts.update(labels)
    per_file[pory.name] = labels

dups = {name: n for name, n in counts.items() if n > 1}
print(f"files scanned: {len(per_file)}")
print(f"total labels:  {sum(counts.values())}")
print(f"duplicates:    {len(dups)}")
for name, n in sorted(dups.items()):
    where = [f for f, labels in per_file.items() if name in labels]
    print(f"  {n}x {name}  ({', '.join(where)})")
