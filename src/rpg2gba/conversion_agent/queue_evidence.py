"""Search-evidence schema for `hand`-bucketed unhandled-queue entries.

Design ref: `ROM_TEST_DEV.md` §E1 ("correction accepted, and the real point is
fixable mechanically"). The problem this closes: the most expensive recurring
bug class in this repo is claiming the engine can't do X without checking the
engine (CLAUDE.md §4.7) — `healparty` was invented while `HealPlayerParty`
existed as a defined special the whole time, and day/night encounters were
declared unsupported when they're native. Exhortation didn't fix it; §4.7
already said this and it happened anyway.

The mechanical fix: no unhandled-queue entry may carry ``bucket="hand"``
without a structured, non-empty search-evidence record —

- the greps actually run against the engine (``$RPG2GBA_POKEEMERALD``, also
  vendored at ``engine/``)
- what each of those greps returned
- which behavior decomposition was attempted and why it failed

A ``hand`` entry with incomplete evidence is a schema violation: it fails
loud (``QueueSchemaViolation``), the same as every other malformed artifact
in this pipeline, not a judgment call. The point of the design is that the
evidence box is visibly blank when nobody looked — free text ("I checked")
doesn't satisfy that, only a structured record with real content in every
sub-field does.

``bucket`` values mirror the disposition vocabulary already in use across
`reference/findings/slice1_queue_readthrough.md` and `MEMORY.md`: ``native``
(fork analog exists — emit it), ``idiom`` (build agent extends the
transpiler's idiom library, user reviews), ``hand`` (genuinely irreducible —
hand-converted, `hand_conversions/*.pory`), ``defer`` (out of current slice
scope, revisit later).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

Bucket = Literal["native", "idiom", "hand", "defer"]
VALID_BUCKETS: tuple[Bucket, ...] = ("native", "idiom", "hand", "defer")

# The triage ledger this schema governs, and the live gate's input:
# `hand_overrides.load_hand_overrides` refuses any `hand_conversions/*.pory`
# without a matching evidence-carrying `hand` entry here. Committed (it is a
# curation artifact and a review surface, not generated output).
LEDGER_PATH = (
    Path(__file__).resolve().parents[3]
    / "reference" / "findings" / "hand_bucket_queue.jsonl"
)


class QueueSchemaViolation(ValueError):
    """A queue entry violates the persisted-triage schema.

    Raised both when a `hand` entry is missing required evidence at the
    point the bucket is assigned, and when a jsonl load encounters one
    on disk (see `enforce_hand_evidence` / `load_queue_jsonl`).
    """


# ---------------------------------------------------------------------------
# Evidence dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GrepRecord:
    """One grep actually run against the engine, and a summary of what it returned.

    ``command`` is the literal command/pattern searched (e.g. a `grep -rn
    "healparty"` invocation or just the pattern if the tool wasn't literally
    `grep`). ``result_summary`` is what came back — including "no matches",
    which is itself evidence, not an empty field.
    """

    command: str
    result_summary: str

    def to_dict(self) -> dict:
        return {"command": self.command, "result_summary": self.result_summary}

    @staticmethod
    def from_dict(data: dict) -> "GrepRecord":
        return GrepRecord(
            command=str(data.get("command", "")),
            result_summary=str(data.get("result_summary", "")),
        )


@dataclass(frozen=True)
class SearchEvidence:
    """Structured proof that the engine was actually searched before hand-bucketing.

    All four content fields (``greps`` non-empty with populated sub-fields,
    plus the two decomposition strings) are required for a `hand` entry to
    pass validation — see `missing_evidence_fields`. ``legacy_unaudited``
    is the one escape hatch: it marks a pre-existing entry that predates this
    schema and could not be honestly backfilled with real evidence. It does
    NOT satisfy validation (missing fields are still reported), it only
    changes how a violation is handled at load/enforcement time — logged
    instead of raised (see `enforce_hand_evidence`).
    """

    greps: tuple[GrepRecord, ...] = ()
    decomposition_attempted: str = ""
    decomposition_failed_because: str = ""
    legacy_unaudited: bool = False

    def to_dict(self) -> dict:
        return {
            "greps": [g.to_dict() for g in self.greps],
            "decomposition_attempted": self.decomposition_attempted,
            "decomposition_failed_because": self.decomposition_failed_because,
            "legacy_unaudited": self.legacy_unaudited,
        }

    @staticmethod
    def from_dict(data: dict) -> "SearchEvidence":
        return SearchEvidence(
            greps=tuple(GrepRecord.from_dict(g) for g in data.get("greps", [])),
            decomposition_attempted=str(data.get("decomposition_attempted", "")),
            decomposition_failed_because=str(data.get("decomposition_failed_because", "")),
            legacy_unaudited=bool(data.get("legacy_unaudited", False)),
        )


# ---------------------------------------------------------------------------
# Queue entry
# ---------------------------------------------------------------------------


@dataclass
class QueueEntry:
    """One triaged unhandled-queue entry: the raw source record + its disposition.

    ``raw`` is the queue record as written by the transpiler
    (`transpile_driver.py` / `transpiler.py`'s `TranspileContext.queue()`
    shape: map_id/common_event_id, event_id, page, line, command_code,
    description, reason, ...) — carried through unchanged so this layer
    never has to duplicate or re-derive that schema.
    """

    raw: dict = field(default_factory=dict)
    bucket: Bucket = "defer"
    evidence: SearchEvidence | None = None

    def identity(self) -> str:
        """Human-readable locator for error messages: 'MapNNN/EVn p<page> code<c>'."""
        if "common_event_id" in self.raw and self.raw.get("common_event_id") is not None:
            loc = f"CE{self.raw.get('common_event_id')}"
        else:
            loc = f"Map{self.raw.get('map_id', '?')}"
        return (
            f"{loc}/EV{self.raw.get('event_id', '?')} "
            f"p{self.raw.get('page', '?')} code{self.raw.get('command_code', '?')}"
        )

    def to_dict(self) -> dict:
        d: dict = {"raw": self.raw, "bucket": self.bucket}
        if self.evidence is not None:
            d["evidence"] = self.evidence.to_dict()
        return d

    @staticmethod
    def from_dict(data: dict) -> "QueueEntry":
        bucket = data.get("bucket")
        if bucket not in VALID_BUCKETS:
            raise QueueSchemaViolation(
                f"queue entry has invalid bucket {bucket!r}; must be one of {VALID_BUCKETS}"
            )
        evidence_data = data.get("evidence")
        evidence = SearchEvidence.from_dict(evidence_data) if evidence_data is not None else None
        return QueueEntry(raw=data.get("raw", {}), bucket=bucket, evidence=evidence)


# ---------------------------------------------------------------------------
# Validation / enforcement
# ---------------------------------------------------------------------------


def missing_evidence_fields(evidence: SearchEvidence | None) -> list[str]:
    """Return the dotted names of required sub-fields that are empty or missing.

    An empty return means the record is complete. This never looks at
    ``legacy_unaudited`` — that flag changes how a caller *reacts* to a
    non-empty result, not whether the result is non-empty.
    """
    if evidence is None:
        return ["evidence"]

    missing: list[str] = []
    if not evidence.greps:
        missing.append("evidence.greps")
    else:
        for i, g in enumerate(evidence.greps):
            if not g.command.strip():
                missing.append(f"evidence.greps[{i}].command")
            if not g.result_summary.strip():
                missing.append(f"evidence.greps[{i}].result_summary")
    if not evidence.decomposition_attempted.strip():
        missing.append("evidence.decomposition_attempted")
    if not evidence.decomposition_failed_because.strip():
        missing.append("evidence.decomposition_failed_because")
    return missing


def validate_entry(entry: QueueEntry) -> list[str]:
    """Return missing-evidence field names for a `hand` entry; [] for any other bucket.

    Never raises — pure inspection. `enforce_hand_evidence` is the
    raise/log decision layer built on top of this.
    """
    if entry.bucket != "hand":
        return []
    return missing_evidence_fields(entry.evidence)


def enforce_hand_evidence(entry: QueueEntry) -> None:
    """Fail loud when a `hand` entry's evidence is incomplete.

    Raises `QueueSchemaViolation` naming the entry and every missing
    sub-field — unless the evidence is explicitly marked
    ``legacy_unaudited``, in which case the same information is logged as a
    warning instead of raised (a known, flagged debt, not a silent gap).
    Entries in any other bucket always pass silently.
    """
    missing = validate_entry(entry)
    if not missing:
        return

    msg = (
        f"queue entry {entry.identity()!r} is bucketed 'hand' but is missing "
        f"required evidence field(s): {', '.join(missing)}"
    )
    is_legacy = entry.evidence is not None and entry.evidence.legacy_unaudited
    if is_legacy:
        logger.warning("%s (marked legacy_unaudited — not fatal, but still a gap)", msg)
        return
    raise QueueSchemaViolation(msg)


# ---------------------------------------------------------------------------
# jsonl load / save
# ---------------------------------------------------------------------------


def load_queue_jsonl(path: Path) -> list[QueueEntry]:
    """Load a triage jsonl, validating every `hand` entry as it's parsed.

    Fails loud at the first non-legacy schema violation — the entire load
    aborts (CLAUDE.md §4.5): an existing jsonl with a bad entry must fail at
    read time, not silently. `legacy_unaudited` violations are logged and
    the load continues.
    """
    path = Path(path)
    entries: list[QueueEntry] = []
    for lineno, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            data = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise QueueSchemaViolation(f"{path}:{lineno}: malformed JSON — {exc}") from exc
        entry = QueueEntry.from_dict(data)
        try:
            enforce_hand_evidence(entry)
        except QueueSchemaViolation as exc:
            raise QueueSchemaViolation(f"{path}:{lineno}: {exc}") from exc
        entries.append(entry)
    return entries


def save_queue_jsonl(path: Path, entries: list[QueueEntry]) -> None:
    """Serialize entries to jsonl, one per line.

    Validates every `hand` entry before writing anything — a bad entry must
    not silently make it onto disk. `legacy_unaudited` entries are written
    (with their gap logged), consistent with `load_queue_jsonl`.
    """
    for entry in entries:
        enforce_hand_evidence(entry)

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry.to_dict(), ensure_ascii=False))
            f.write("\n")
