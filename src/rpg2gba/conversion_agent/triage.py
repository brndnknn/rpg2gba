"""Cluster-aware triage for the Phase 4 unhandled-event queue.

Implements the design from FABLES_DECISIONS.md Suggestion 3.

Groups unhandled.jsonl entries by joining each back to its source RMXP
command in the Phase-3 JSON, building a deterministic cluster key, then
auto-tagging each cluster with a disposition from the recorded rule table.

Read-only: never writes to any output artifact. Degrades gracefully on bad or
unjoinable entries — falls back to 'novel' with a logged warning rather than
raising.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import click

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Signature extraction
# ---------------------------------------------------------------------------

_SIG_HEAD_RE = re.compile(r"[A-Za-z_$][A-Za-z0-9_.$]*")


def _sig_head(text: str) -> str:
    """Return the callable path leading the first line of a script text.

    Stops at the first ``(``, whitespace, or ``=`` (none of which appear in
    the regex character class), so ``Kernel.pbReceiveItem(:POTION,1)``
    returns ``Kernel.pbReceiveItem`` and ``$lobbyreset=true`` returns
    ``$lobbyreset``.
    """
    first_line = text.split("\n", 1)[0].lstrip()
    m = _SIG_HEAD_RE.match(first_line)
    return m.group() if m else ""


def _bare_method(sig: str) -> str:
    """Return the segment after the last dot (bare method name)."""
    return sig.rsplit(".", 1)[-1]


# ---------------------------------------------------------------------------
# Reference-file loaders
# ---------------------------------------------------------------------------


def _load_unhandled_table(reference_dir: Path) -> tuple[list[str], list[str]]:
    """Parse uranium_script_calls.md and return (exact_sigs, prefix_stems).

    Only the ``## UNHANDLED — queue it (do not guess)`` section is
    processed; tokens from MAP/STRIP sections are intentionally excluded.

    Raises FileNotFoundError when the file is absent — that is a caller
    error (the reference tree must be present).
    """
    path = reference_dir / "uranium_script_calls.md"
    text = path.read_text(encoding="utf-8")

    marker = "## UNHANDLED — queue it (do not guess)"
    start = text.find(marker)
    if start == -1:
        logger.warning("uranium_script_calls.md: UNHANDLED section not found")
        return [], []

    section = text[start + len(marker) :]
    nxt = re.search(r"\n## ", section)
    if nxt:
        section = section[: nxt.start()]

    exact: list[str] = []
    prefixes: list[str] = []
    for row in re.finditer(r"^\|([^|]+)\|", section, re.MULTILINE):
        cell = row.group(1)
        # Skip header and separator rows.
        if re.match(r"\s*[-:]+\s*$", cell) or re.search(r"[Ss]ignature", cell):
            continue
        for tok in re.findall(r"`([^`]+)`", cell):
            if tok.endswith("*"):
                prefixes.append(tok[:-1])
            else:
                exact.append(tok)

    return exact, prefixes


def _load_strip_set(reference_dir: Path) -> set[int]:
    """Return the set of CE ids in strip_list.json; empty set when absent.

    Absent file is not an error — strip disposition is simply inactive for
    this run/project. A parse error is also non-fatal (logged + empty set).
    """
    path = reference_dir / "strip_list.json"
    if not path.exists():
        logger.info("strip_list.json not present — strip disposition inactive")
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        logger.warning("strip_list.json decode error: %s — treating as empty", exc)
        return set()
    ce_entries = data.get("common_events", []) if isinstance(data, dict) else []
    ids: set[int] = set()
    for entry in ce_entries:
        try:
            ids.add(int(entry["id"]))
        except (KeyError, TypeError, ValueError):
            pass
    return ids


def _load_sources(
    out_dir: Path,
) -> tuple[dict[int, dict], dict[int, dict]]:
    """Load Phase-3 map JSON and common_events.json into lookup dicts.

    Missing files produce a warning but do not abort — entries that require
    those sources will simply be unjoinable.

    Returns (maps_by_id, ces_by_id).
    """
    maps: dict[int, dict] = {}
    maps_dir = out_dir / "maps"
    if maps_dir.is_dir():
        for p in maps_dir.glob("Map*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                mid = data.get("map_id")
                if mid is not None:
                    maps[int(mid)] = data
            except (json.JSONDecodeError, ValueError) as exc:
                logger.warning("could not load %s: %s", p.name, exc)

    ces: dict[int, dict] = {}
    ce_path = out_dir / "common_events.json"
    if ce_path.is_file():
        try:
            for ce in json.loads(ce_path.read_text(encoding="utf-8")):
                cid = ce.get("id")
                if cid is not None:
                    ces[int(cid)] = ce
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("could not load common_events.json: %s", exc)

    return maps, ces


# ---------------------------------------------------------------------------
# Source join
# ---------------------------------------------------------------------------


def _join_command(
    entry: dict,
    maps: dict[int, dict],
    ces: dict[int, dict],
) -> tuple[dict | None, bool]:
    """Locate the source RMXP command for a queue entry.

    ``line`` is unreliable across the live corpus (1-based, 0-based, or
    wrong) and is used only as a secondary hint when multiple commands share
    the same code on a page.

    Returns ``(command_dict, True)`` on success or ``(None, False)`` on any
    miss; the caller degrades gracefully in both cases.
    """
    code = entry.get("command_code")
    page_num = int(entry.get("page", 1))
    line = entry.get("line")  # absent in some entries

    is_ce = "common_event_id" in entry

    if is_ce:
        ce_id = int(entry.get("common_event_id") or entry.get("event_id", 0))
        ce = ces.get(ce_id)
        if ce is None:
            logger.warning("CE %d not in common_events.json", ce_id)
            return None, False
        cmd_list: list[dict] = ce.get("list", [])
    else:
        map_id = entry.get("map_id")
        event_id = entry.get("event_id")
        if map_id is None or event_id is None:
            logger.warning("queue entry missing map_id/event_id: %s", entry)
            return None, False
        map_data = maps.get(int(map_id))
        if map_data is None:
            logger.warning("map %d not found in out_dir/maps", int(map_id))
            return None, False
        event = next(
            (e for e in map_data.get("events", []) if e.get("id") == event_id),
            None,
        )
        if event is None:
            logger.warning("event %d not in map %d", event_id, int(map_id))
            return None, False
        pages = event.get("pages", [])
        idx = page_num - 1
        if idx < 0 or idx >= len(pages):
            logger.warning(
                "page %d out of range for map %d event %d",
                page_num,
                int(map_id),
                event_id,
            )
            return None, False
        cmd_list = pages[idx].get("list", [])

    matches = [i for i, cmd in enumerate(cmd_list) if cmd.get("code") == code]
    if not matches:
        return None, False
    if len(matches) == 1:
        return cmd_list[matches[0]], True

    # Multiple matches: use line as a hint; prefer 1-based index, then 0-based.
    if line is not None:
        if (line - 1) in matches:
            return cmd_list[line - 1], True
        if line in matches:
            return cmd_list[line], True

    # Fall through to first match — cluster keys for same-code repeats are
    # often identical anyway, so this is benign.
    return cmd_list[matches[0]], True


# ---------------------------------------------------------------------------
# Cluster key
# ---------------------------------------------------------------------------


def _cluster_key(entry: dict, cmd: dict | None, joined: bool) -> str:
    """Build a deterministic string key that identifies the cluster."""
    code = entry.get("command_code", 0)
    if not joined or cmd is None:
        return f"{code}:unjoined"

    params: list = cmd.get("parameters", [])

    if code in (355, 655):
        text = str(params[0]) if params else ""
        return f"{code}:{_sig_head(text)}"

    if code == 111:
        cond_type = params[0] if params else 0
        key = f"{code}:cond{cond_type}"
        if cond_type == 12 and len(params) > 1:
            sig = _sig_head(str(params[1]))
            if sig:
                key = f"{key}:{sig}"
        return key

    if code == 201:
        mode = params[0] if params else 0
        return f"{code}:{'variable' if mode == 1 else 'fixed'}"

    return str(code)


# ---------------------------------------------------------------------------
# Disposition rules
# ---------------------------------------------------------------------------


def _matches_table(sig: str, exact: list[str], prefixes: list[str]) -> bool:
    """True when sig (or its bare method name or Kernel.-stripped form) matches."""
    if not sig:
        return False
    bare = _bare_method(sig)
    kernel_stripped = sig[len("Kernel.") :] if sig.startswith("Kernel.") else sig
    candidates = {sig, bare, kernel_stripped}
    for e in exact:
        if e in candidates:
            return True
    for stem in prefixes:
        if any(c.startswith(stem) for c in candidates):
            return True
    return False


def _disposition(
    entry: dict,
    cmd: dict | None,
    joined: bool,
    strip_set: set[int],
    exact: list[str],
    prefixes: list[str],
) -> str:
    """Return the auto-disposition for an entry; rules applied in priority order."""
    code = entry.get("command_code", 0)

    # Rule 1 — move-route codes; applies even when the join failed.
    if code in (209, 210, 509):
        return "phase5-move-route"

    # Rule 2 — warp.
    if code == 201:
        return "phase5-warp"

    # Rule 3 — strip-listed common event.
    if "common_event_id" in entry:
        ce_id = int(entry.get("common_event_id") or entry.get("event_id", 0))
        if ce_id in strip_set:
            return "superseded-by-strip"

    # Rule 4 — signature is in the UNHANDLED table (needs an engine feature).
    if code in (355, 655) and joined and cmd is not None:
        params: list = cmd.get("parameters", [])
        text = str(params[0]) if params else ""
        if _matches_table(_sig_head(text), exact, prefixes):
            return "needs-engine"

    # Rule 5 — custom-mode conditional (randomizer check).
    if code == 111 and joined and cmd is not None:
        params = cmd.get("parameters", [])
        if params and params[0] == 12 and len(params) > 1:
            if "$PokemonGlobal.randomizer" in str(params[1]):
                return "phase8-custom-mode"

    return "novel"


# ---------------------------------------------------------------------------
# Public dataclasses
# ---------------------------------------------------------------------------


@dataclass
class TriagedEntry:
    """One queue entry and its derived triage facts."""

    raw: dict
    cluster_key: str
    disposition: str
    joined: bool


@dataclass
class Cluster:
    """All entries that share a cluster key."""

    key: str
    disposition: str
    entries: list[TriagedEntry] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.entries)

    @property
    def example_description(self) -> str:
        """First non-empty description in the cluster, or empty string."""
        for e in self.entries:
            desc = e.raw.get("description", "")
            if desc:
                return desc
        return ""


@dataclass
class TriageReport:
    """Full triage result with human-readable summary helpers."""

    clusters: list[Cluster]  # novel first, then by count desc within each group
    total: int
    novel_total: int

    def summary_lines(self) -> list[str]:
        """Table of dispositions with cluster and entry counts."""
        if not self.clusters:
            return ["  (no entries)"]
        by_disp: dict[str, list[int]] = {}
        for c in self.clusters:
            rec = by_disp.setdefault(c.disposition, [0, 0])
            rec[0] += 1
            rec[1] += c.count
        lines = [f"  {'disposition':<28} {'clusters':>8} {'entries':>8}"]
        for disp, (nc, ne) in sorted(by_disp.items(), key=lambda kv: -kv[1][1]):
            lines.append(f"  {disp:<28} {nc:>8} {ne:>8}")
        lines.append(f"  {'TOTAL':<28} {'':>8} {self.total:>8}")
        return lines

    def novel_lines(self) -> list[str]:
        """Detail lines for novel clusters: key, count, per-entry refs + description."""
        lines = []
        for c in self.clusters:
            if c.disposition != "novel":
                continue
            lines.append(f"  [{c.count}] {c.key}")
            for e in c.entries:
                raw = e.raw
                if "common_event_id" in raw:
                    loc = f"CE{raw.get('common_event_id', '?')}/EV{raw.get('event_id', '?')}"
                else:
                    loc = f"Map{raw.get('map_id', '?')}/EV{raw.get('event_id', '?')}"
                desc = (raw.get("description") or "")[:120]
                lines.append(f"      {loc}: {desc}")
        return lines


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def triage_queue(
    unhandled_path: Path,
    out_dir: Path,
    reference_dir: Path,
) -> TriageReport:
    """Cluster and auto-disposition all entries in unhandled.jsonl.

    Implements the design from FABLES_DECISIONS.md Suggestion 3.

    Never modifies any output artifact; safe to call mid-run. Individual
    entries that cannot be processed (bad JSON excluded; any other error)
    degrade to 'novel' with a logged warning.

    Raises FileNotFoundError for a missing unhandled.jsonl or
    uranium_script_calls.md — both indicate a misconfigured call site.
    """
    unhandled_path = Path(unhandled_path)
    out_dir = Path(out_dir)
    reference_dir = Path(reference_dir)

    exact, prefixes = _load_unhandled_table(reference_dir)
    strip_set = _load_strip_set(reference_dir)
    maps, ces = _load_sources(out_dir)

    triaged: list[TriagedEntry] = []
    for lineno, raw_line in enumerate(
        unhandled_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            entry = json.loads(raw_line)
        except json.JSONDecodeError:
            logger.warning("malformed JSONL at line %d — skipping", lineno)
            continue
        try:
            cmd, joined = _join_command(entry, maps, ces)
            key = _cluster_key(entry, cmd, joined)
            disp = _disposition(entry, cmd, joined, strip_set, exact, prefixes)
        except Exception as exc:  # never crash on queue content
            code = entry.get("command_code", 0)
            logger.warning(
                "unexpected error at line %d (%s) — treating as novel", lineno, exc
            )
            key = f"{code}:error"
            disp = "novel"
            joined = False
        triaged.append(
            TriagedEntry(raw=entry, cluster_key=key, disposition=disp, joined=joined)
        )

    # Group by (key, disposition): the disposition is entry-level (e.g. strip-list
    # membership), so two entries can share a content key yet diverge — they must
    # not be folded under whichever disposition happened to arrive first.
    cluster_map: dict[tuple[str, str], Cluster] = {}
    for e in triaged:
        ck = (e.cluster_key, e.disposition)
        if ck not in cluster_map:
            cluster_map[ck] = Cluster(key=e.cluster_key, disposition=e.disposition)
        cluster_map[ck].entries.append(e)

    clusters = sorted(
        cluster_map.values(),
        key=lambda c: (0 if c.disposition == "novel" else 1, -c.count),
    )
    total = len(triaged)
    novel_total = sum(c.count for c in clusters if c.disposition == "novel")
    return TriageReport(clusters=clusters, total=total, novel_total=novel_total)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.command()
@click.option(
    "--out-dir",
    type=click.Path(path_type=Path),
    default="output/uranium-build",
    show_default=True,
    help="Directory containing maps/ and common_events.json.",
)
@click.option(
    "--reference-dir",
    type=click.Path(path_type=Path),
    default="reference",
    show_default=True,
    help="Directory containing uranium_script_calls.md and strip_list.json.",
)
@click.option(
    "--novel",
    "show_novel",
    is_flag=True,
    default=False,
    help="Print novel-cluster detail instead of the summary table.",
)
def _cli(out_dir: Path, reference_dir: Path, show_novel: bool) -> None:
    """Triage the unhandled event queue."""
    out_dir = Path(out_dir)
    unhandled = out_dir / "unhandled.jsonl"
    report = triage_queue(unhandled, out_dir, Path(reference_dir))
    for line in report.novel_lines() if show_novel else report.summary_lines():
        print(line)


if __name__ == "__main__":
    _cli()
