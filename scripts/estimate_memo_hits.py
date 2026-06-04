"""Estimate dedup-C memo hit rate before the bulk run.

Replicates orchestrator._memo_key exactly: sha256 of event payload minus
map_id and id. Reports unique keys vs total command-bearing events to show
how many Opus spawns the memo will save.
"""
import hashlib
import json
from collections import Counter
from pathlib import Path

MAP_DIR = Path("output/uranium-build/maps")
CE_PATH = Path("output/uranium-build/common_events.json")


def _event_has_commands(event: dict) -> bool:
    for page in event.get("pages", []):
        for cmd in page.get("list", []):
            if cmd.get("code", 0) != 0:
                return True
    return False


def _memo_key(payload: dict) -> str:
    content = {k: v for k, v in payload.items() if k not in ("map_id", "id")}
    blob = json.dumps(content, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def main() -> None:
    keys: list[str] = []

    for path in sorted(MAP_DIR.glob("Map*.json")):
        m = json.loads(path.read_text(encoding="utf-8"))
        for event in m["events"]:
            if not _event_has_commands(event):
                continue
            payload = {"map_id": m["map_id"], **event}
            keys.append(_memo_key(payload))

    total = len(keys)
    unique = len(set(keys))
    saved = total - unique

    counts = Counter(keys)
    top = counts.most_common(10)

    print(f"Command-bearing map events: {total}")
    print(f"Unique memo keys:           {unique}")
    print(f"Memo hits (saves):          {saved}  ({saved/total*100:.1f}%)")
    print(f"Estimated Opus spawns:      {unique}")
    print()
    print("Top 10 most-duplicated event keys (occurrences → saves):")
    for key, count in top:
        # Find one example to show what the event is
        for path in sorted(MAP_DIR.glob("Map*.json")):
            m = json.loads(path.read_text(encoding="utf-8"))
            for event in m["events"]:
                if not _event_has_commands(event):
                    continue
                payload = {"map_id": m["map_id"], **event}
                if _memo_key(payload) == key:
                    print(f"  {count}x — map{m['map_id']} ev{event['id']} ({event.get('name', '')})")
                    break
            else:
                continue
            break


if __name__ == "__main__":
    main()
