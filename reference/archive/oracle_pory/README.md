# Frozen-Opus oracle archive (`.pory`)

Snapshot (2026-07-02) of `output/uranium-build/scripts/` — the Poryscript output of
the retired Opus-4.8 conversion runs — archived per grill decision **D6**
(`reference/grill_spine_2026-07-02.md`) so that `pipeline --clean` /
`prep_bulk_run.py --yes` can no longer destroy the transpiler's differential oracle.

**Role:** one-time harvest target for the deterministic transpiler. At each
transpiler milestone, diff its output against these files (normalized text, not
bytes) and disposition every divergence cluster as *transpiler bug* (fix) or *Opus
error* (note, discard). These are **not golden files** — permanent regression
goldens are minted from reviewed transpiler output, never from Opus text. After the
harvest completes, this directory is inert history.

## Provenance (verified 2026-07-02 from run state, checkpoints, and token log)

| Files | Origin |
|---|---|
| `Map001`–`Map007`, `CommonEvents` | Opus bulk run, 2026-06-06→09 (87 spawns). Jun 12 mtimes are a **zero-spawn memo replay** (`scripts/regen_outputs.py`, label-uniquing fix `dc8e436`) — content is Opus-sourced. This is the oracle proper (D6). |
| `Map008`–`Map014`, `Map017` | Same bulk run, continuation 2026-06-13 (35 spawns) until the usage limit hit at Map017 (`run_state.json` `limit_reached`, mtime matches Map017 to the second). `Map008`/`Map010` checkpointed **`.partial`** — their lane events were held for hand conversion, so those two are incomplete conversions. Extra harvest material beyond the D6 set. |
| `Map032`, `Map048`, `Map049` | Pathfinder-slice run (`scripts/run_slice.py`, same orchestrator + memo), 2026-06-15→16. `Map048` is cleanly attributable (script and checkpoint mtimes match to the millisecond). **Caveat:** `Map032`/`Map049` were rewritten on disk ~Jun 17 08:36 (31 s apart) with zero token spend that day and no known pipeline writer — coinciding with the S8 build-gate debugging session. Content shows no hand-edit signature (pre-normalization `\"` escapes and bare `healparty` still present), so the likely explanation is an ad hoc re-save of Opus content, but that write is off the documented paper trail. |

Notes for harvest time:

- Text here is **pre-normalization**: raw `\"` escapes and invented symbols
  (`healparty`) are present by design — `normalize_pory` fixes were applied
  downstream at staging, never written back. Apply the same normalization to both
  sides before diffing.
- `output/uranium-build/staging/scripts/` did not exist at snapshot time; the only
  on-disk copy of these conversions was the gitignored canonical `scripts/` dir.
