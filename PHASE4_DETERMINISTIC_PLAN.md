# Phase 4 — Deterministic Pre-Filter Plan

**Purpose:** Reduce Opus spawns before the bulk `phase4 --run` by routing
events with fully-mechanical structure through a deterministic handler instead
of the LLM. The LLM adds nothing for these events — the output is a direct
structural translation of data that is already fully present in the event JSON.

**Build agent:** implement the classifiers in the order given below, testing
between each one. Do not start the next classifier until the current one has
passing tests and a verified count on the real corpus.

**Session decisions (2026-06-04):** stop before any budget-gated run — build +
test all six classifiers, run only the no-budget acceptance checks (§10 steps
1–3), do the budget-free part of the Map002 comparison, present match counts,
and **stop before the Opus Map002 re-run (§10 step 4 full) and the bulk run.**
Work proceeds on a feature branch with **one commit per classifier** once its
tests pass.

---

## 0. Progress Tracker

Status legend: `[ ]` todo · `[~]` in progress · `[x]` done

### Shared scaffolding (§3, §2)
- [x] text-block extraction helper — landed as `_dialogue_body` (walks the page,
  collapses 101+401 runs into `msgbox`, interleaves 117/123) rather than the
  plan's standalone `_extract_text_blocks`
- [x] `format_pory_string` helper
- [x] `_try_deterministic` dispatch wired into `_convert_event`

### Classifiers (build in order; test + corpus-count each before the next)
- [x] Classifier 1 — Pure Dialogue (§4) · target ~620 · **actual: 372** (all
  compile clean; see §12 for why 372 not ~620 and the deferred `\sign` bucket)
- [x] Classifier 2 — Call Common Event (§5) · target 52 · **actual: 50** (all
  compile clean; `_dialogue_body(allow_call=True)` already existed — Classifier 2
  is a `saw_call`-guarded twin of Classifier 1; no unprescribed-content bucket)
- [x] Classifier 3 — Self-Switch Dialogue (§6) · target 67 · **actual: 58** (all
  compile clean; `_dialogue_body(allow_self_switch=True)` already existed —
  `saw_switch`-guarded twin; flag names agree with `_mint_event_switches` by
  construction; no unprescribed-content bucket)
- [ ] Classifier 4 — Simple Warp (§7) · target 317 · actual: ___
- [ ] Classifier 5 — Item Ball (§8) · target 45 · actual: ___
- [ ] Classifier 6 — Trainer Battle (§9) · target ~250 · actual: ___

### Acceptance — no-budget only this session (§10)
- [ ] `scripts/count_deterministic_actual.py` full-corpus count (§10.1)
- [ ] `phase4 --clean` dry counts still 8/5/34/199 (§10.2)
- [ ] full pytest incl. phase4 marker green (§10.3)
- [ ] budget-free part of Map002 comparison (§10.4)
- [ ] present final match counts to user (§10.5)
- [ ] DEFERRED (budget-gated, NOT this session): calibrate_map002.sh Opus re-run (§10.4 full) + bulk `phase4 --run`

---

## 1. Background

### Why this is safe

The orchestrator's job is to produce correct Poryscript. For events whose
entire content can be translated with a lookup table and a few fixed macros,
the LLM path is strictly more expensive and more likely to introduce variance.
A deterministic handler is:

- **Cheaper** — no API call
- **Faster** — no subprocess spawn
- **More consistent** — same input always produces same output
- **Fail-safe** — if the compile-gate rejects the output, the event falls
  through to the existing LLM path unchanged

### Research findings (2026-06-04)

Measured against the 3,581 command-bearing map events in the Phase 3 corpus.
Findings from two passes: initial pattern survey, then a deeper survey of the
remaining ~2,473 events to find additional patterns.

| Pattern | Events | % of total |
|---|---|---|
| Pure dialogue (expanded STRIP list) | ~620 | ~17.3% |
| Simple warp (doormat) | 317 | 8.9% |
| Call Common Event only | 52 | 1.5% |
| Self-switch dialogue | 67 | 1.9% |
| Item ball | 45 | 1.3% |
| Trainer battle | 299 | 8.3% |
| Memo hits (already built) | 65 | 1.8% |
| **Deterministic ceiling** | **~1,465** | **~41%** |

The ~620 pure-dialogue figure replaces the initial 452 count — 168 additional
events failed the original filter only because of STRIP-classified script calls
(pbSetPokemonCenter, pbRemoveDependency2, set_fog2, etc.) that carry no game
state. Widening the STRIP whitelist in the detector absorbs them for free.

Realistic Opus spawn reduction: **3,581 → ~2,150** after all six classifiers.

---

## 2. Architecture

### Where the pre-filter lives

Add a `_try_deterministic(map_id, event)` method to `Orchestrator`. It is
called at the **top** of `_convert_event`, before the memo check and before
any LLM spawn:

```python
def _convert_event(self, map_id: int, event: dict) -> str | None:
    payload = {"map_id": map_id, **event}
    ctx = self._event_ctx(map_id, event)

    # NEW: try deterministic handler first
    det = self._try_deterministic(map_id, event)
    if det is not None:
        compiled = self.compile_fn(det)
        if compiled.ok:
            if not self._mint_event_switches(map_id, event, ctx):
                return None
            self._store_memo(_memo_key(payload), map_id, event,
                             ConversionResult(script=det))
            logger.info("ev%s deterministic:\n%s", event.get("id"), det)
            return det
        # compile failed — fall through to LLM (fail-safe)
        logger.debug("ev%s deterministic output failed compile; falling through", event.get("id"))

    # memo check, then LLM (existing path, unchanged)
    key = _memo_key(payload)
    ...
```

`_try_deterministic` returns a Poryscript string on match or `None` to
fall through. It must never raise — any unexpected structure should return
`None`.

### What the deterministic handler does NOT do

- It does **not** call the registry's `propose_flag` / `propose_var`. It only
  calls `_mint_event_switches` (for self-switches), which the orchestrator
  already does post-accept.
- It does **not** write to `unhandled.jsonl`. If a pattern is only partially
  translatable (e.g. a warp whose map constant is a placeholder) that is fine
  — the warp placeholder is emitted exactly as Opus would emit it, and the
  `unhandled.jsonl` entry for the Phase-5 warp resolution is **not** written
  (we're intentionally not queuing it, since the placeholder is the known
  right output). If you want to queue it, do so explicitly inside the handler.
- It stores the result in the memo so cross-map identical events get reused
  automatically.

---

## 3. Text extraction helper

All patterns need to concatenate multi-line RMXP dialogue (codes 101 + 401
continuations) into a single Poryscript string. Write this helper once and
reuse it across all handlers:

```python
def _extract_text_blocks(page: dict) -> list[str]:
    """Return each complete Show Text block as one string.

    Code 101 starts a block; codes 401 are continuations. Each block becomes
    one msgbox call. Text parameters are in parameters[0]."""
    blocks: list[str] = []
    current: list[str] = []
    for cmd in page.get("list", []):
        code = cmd.get("code", 0)
        params = cmd.get("parameters", [])
        if code == 101:
            if current:
                blocks.append("".join(current))
            current = [params[0] if params else ""]
        elif code == 401:
            current.append(params[0] if params else "")
        # other codes: flush current block if open, ignore
        elif current:
            blocks.append("".join(current))
            current = []
    if current:
        blocks.append("".join(current))
    return blocks
```

Poryscript string quoting: wrap each block in `format_pory_string(text)`,
which escapes backslashes and double-quotes and wraps in double-quotes. Write
this helper too — you'll use it everywhere.

---

## 4. Classifier 1 — Pure Dialogue

**Count: ~620 events (~17.3%)**

### Detection

An event qualifies if **every page** passes this check:

- Every command code is in the safe set `{0, 5, 6, 7, 101, 401}`, OR
- The command is code 355/655 **and** its first parameter matches one of the
  STRIP patterns below (no output for any of them)

No code 111 (branch), 123 (self-switch set), 201 (warp), or any non-STRIP
script call. All pages must qualify; one non-qualifying page fails the whole
event.

**STRIP script-call patterns** (all produce no output — extend this list if
additional STRIP calls are verified in `reference/uranium_script_calls.md`):

```python
_DIALOGUE_STRIP_RE = re.compile(
    r"^\s*("
    r"pbCallBub"
    r"|set_fog2"
    r"|XInput\.vibrate"
    r"|pbSEPlay"
    r"|pbPlayCry"
    r"|\$scene\.spriteset\.addUserSprite"
    r"|\$game_map\.need_refresh\s*="
    r"|pbRemoveDependency2"
    r"|Kernel\.pbRemoveDependency2"
    r"|pbAddDependency2"
    r"|Kernel\.pbAddDependency2"
    r"|Kernel\.pbSetPokemonCenter"
    r")\b"
)

_PURE_DIALOGUE_SAFE = {0, 5, 6, 7, 101, 401}

def _page_is_pure_dialogue(page: dict) -> bool:
    for cmd in page.get("list", []):
        code = cmd.get("code", 0)
        if code in _PURE_DIALOGUE_SAFE:
            continue
        if code in (355, 655):
            p = cmd.get("parameters", [""])[0]
            if isinstance(p, str) and _DIALOGUE_STRIP_RE.match(p):
                continue
        return False
    return True
```

### Output

Each page becomes one script block. A page with no text produces a block
with just `end`. Include `lock`/`faceplayer`/`release` only if the source
page contains those codes (5/6/7 respectively).

```
script Map{m:03d}_{name}_Page1 {
    lock
    faceplayer
    msgbox("...")
    msgbox("...")
    release
    end
}

script Map{m:03d}_{name}_Page2 {
    lock
    faceplayer
    msgbox("...")
    release
    end
}
```

Block label format: `Map{map_id:03d}_{event_name}_Page{n}` — identical to
what the LLM produces so memo reuse and label rewrites work correctly.

### Edge cases

- Pages with **no text** (only lock/release/pbCallBub/end): emit a minimal
  `script { end }` block — do not skip the page.
- Multi-page events: emit all pages. The page-switching dispatch is Phase-5
  work; the handler's job is just the per-page content.
- `\n`, `\l`, `\p` line-break codes inside text strings: pass through
  verbatim — Poryscript handles them.

### Tests

1. Single-page event with one 101+401+401 text block → correct msgbox
2. Multi-page event → correct number of script blocks, each labeled correctly
3. Event with `pbCallBub` mixed in → stripped, text preserved
4. Event with `Kernel.pbSetPokemonCenter` → stripped, text preserved
5. Event with `pbRemoveDependency2` → stripped, text preserved
6. Event with `set_fog2` → stripped, text preserved
7. Event with code 111 → returns None
8. Event with code 355 that is NOT in the STRIP list → returns None
9. Output from a real corpus event compiles through poryscript (phase4 marker test)
10. Run detector against full corpus and confirm count is ~620 (report actual)

---

## 5. Classifier 2 — Call Common Event

**Count: 52 events (1.5%)**

### What these are

Events that delegate entirely to a common event via code 117 (Call Common
Event), with only dialogue and STRIP script calls alongside. The common event
does the real work; the map event is just a wrapper that calls it. The call
target is already deterministic — we know it's `CommonEvent_NNN`.

### Detection

An event qualifies if **every page** passes this check:

- Every command code is in `{0, 5, 6, 7, 101, 401, 117}`, OR
- The command is code 355/655 matching `_DIALOGUE_STRIP_RE` (same STRIP list
  as Classifier 1 — reuse it)

No code 111 (branch), 123 (self-switch set), 201 (warp), or non-STRIP script
calls. Multiple 117 calls per page are fine — emit one `call` per occurrence.

### Output

```
script Map{m:03d}_{name}_Page1 {
    lock
    faceplayer
    msgbox("...")          ← if any dialogue precedes the call
    call CommonEvent_005
    release
    end
}
```

Extract the common event ID from code-117 parameters: `parameters[0]` is the
integer common event ID. Format as `CommonEvent_{id:03d}`.

Include `lock`/`faceplayer`/`release` only if codes 5/6/7 are present. Text
blocks (101/401) before or after the call are emitted as `msgbox` in order.

### Edge cases

- A page with **only** a call and no dialogue: emit `call CommonEvent_NNN` +
  `end`, no lock/release.
- Multiple `call` commands in one page: emit them in order.
- Code 117 with id 0 → fall through (invalid common event reference).

### Tests

1. Single call, no dialogue → `call CommonEvent_NNN` only
2. Dialogue before the call → `msgbox` then `call`
3. Multiple calls in one page → emitted in order
4. Code 117 id=0 → returns None
5. Event with code 111 → returns None
6. Output compiles through poryscript

---

## 6. Classifier 3 — Self-Switch Dialogue

**Count: 67 events (1.9%)**

### What these are

Events that are essentially pure dialogue but also set a self-switch (code
123) — the classic "say something once, never repeat" pattern without a branch
to check the condition first. The self-switch flip is the only non-dialogue
content. Page-switching dispatch (which page runs based on the self-switch
state) is Phase-5 work; the handler only emits what each page does.

### Detection

An event qualifies if **every page** passes this check:

- Every command code is in `{0, 5, 6, 7, 101, 401, 123}`, OR
- The command is code 355/655 matching `_DIALOGUE_STRIP_RE`

No code 111 (branch), 201 (warp), or non-STRIP script calls.

### Parsing the self-switch set

Code 123 parameters: `[letter, value]` where letter is `"A"`/`"B"`/`"C"`/`"D"`
and value is `0` (on) or `1` (off). Map to:
- value 0 (turn on) → `setflag(FLAG_MAP{m:03d}_EVENT{e:03d}_SS{letter})`
- value 1 (turn off) → `clearflag(FLAG_MAP{m:03d}_EVENT{e:03d}_SS{letter})`

The flag name matches what `flag_registry.self_switch_flag_name` produces —
critical for `_mint_event_switches` and memo reuse to work correctly.

### Output

```
script Map{m:03d}_{name}_Page1 {
    lock
    faceplayer
    msgbox("...")
    setflag(FLAG_MAP{m:03d}_EVENT{e:03d}_SSA)
    release
    end
}

script Map{m:03d}_{name}_Page2 {
    lock
    faceplayer
    msgbox("...")
    release
    end
}
```

Emit `setflag`/`clearflag` inline in the script in the position the code-123
command appears relative to any text blocks on the same page.

### Edge cases

- A page with **only** a self-switch set and no dialogue: emit just
  `setflag(...)`/`clearflag(...)` + `end`.
- Multiple self-switch sets on one page: emit each in order.
- Self-switch letter other than A (B/C/D): supported — the flag name uses the
  correct letter; `_mint_event_switches` already handles all letters.

### Tests

1. Single-page event with text + `123 ["A", 0]` → `msgbox` + `setflag`
2. Self-switch turn off (`123 ["A", 1]`) → `clearflag`
3. Self-switch letter B → `FLAG_..._SSB`
4. Page with only self-switch set, no text → `setflag` + `end`
5. Event with code 111 → returns None
6. Flag name matches `flag_registry.self_switch_flag_name(map_id, event_id, "A")`
7. Output compiles through poryscript

---

## 7. Classifier 4 — Simple Warp

**Count: 317 events (8.9%)**

### What these are

Single-page doormat events (player-touch trigger) that fade the screen and
warp to another map. All the meaningful content is in code 201 (Transfer
Player). Everything else is plumbing: fade (223/224), screen tone (223/224
overlap in RMXP), wait (106), lock/release (5/7), SE (355 audio STRIP).

### Detection

An event qualifies if it is **single-page** and every command code is in:

```python
_WARP_SAFE_CODES = {0, 5, 6, 7, 106, 201, 221, 222, 223, 224, 249, 250}
```

Plus codes 355/655 are allowed only if the call is audio-only (matches
`^\s*(pbSEPlay|pbPlayCry|XInput\.vibrate)\b`). Any other code fails the check.

Exactly **one** code-201 command must be present (the warp target). Zero or
two warps → fall through to LLM.

### Output

```
script Map{m:03d}_{name}_Page1 {
    lockall
    fadescreen(FADE_TO_BLACK)
    warp(MAP_URANIUM_{target_map_id}, {x}, {y})
    releaseall
    end
}
```

The warp target: code-201 parameters are `[map_id, x, y, direction,
fade_type]` in RMXP. Emit `MAP_URANIUM_{map_id}` as the placeholder — exactly
what Opus produces, and a known Phase-5 resolution target. Do **not** queue
it in `unhandled.jsonl`; the placeholder is the intended output.

Omit `lockall`/`releaseall` if codes 5/7 are absent from the page. Most
doormat warps won't have them.

### Edge cases

- Multi-page warp events → fall through (Phase-5 concern; rare).
- Warp with conditional branch → fall through.
- Direction parameter in code 201: emit as-is in the warp if non-zero, or
  omit — pokeemerald `warp` macro takes `(map, x, y)` with no direction arg.

### Tests

1. Single-page warp-only event → correct `warp(MAP_URANIUM_N, x, y)`
2. Warp with fade codes mixed in → same output (plumbing stripped)
3. Warp with SE 355 → audio stripped, warp emitted
4. Multi-page event → returns None
5. Event with two 201 commands → returns None
6. Output compiles through poryscript

---

## 8. Classifier 5 — Item Ball

**Count: 45 events (1.3%)**

### What these are

Ground item-ball pickups: player touches the event, receives an item, the
event sets self-switch A so it never triggers again. Typically 2–3 pages:
page 1 is the pickup (no self-switch condition), page 2+ is the empty
"already collected" state (self-switch A condition → blank).

### Detection

An event qualifies if:

- At least one page contains a `pbItemBall` or `Kernel.pbItemBall` call
  (code 355/655, parameter matches `^\s*(Kernel\.)?pbItemBall\b`)
- All **other** codes across all pages are in
  `{0, 5, 6, 7, 101, 401, 123, 355, 655}` (text + lock/release + self-switch
  set + script calls)
- The only non-pbItemBall, non-pbCallBub script calls are audio STRIP

### Parsing the item call

`pbItemBall` signature: `pbItemBall(:ITEM_CONSTANT)` or
`pbItemBall(:ITEM_CONSTANT, qty)`.

Extract the item symbol from the parameter string with a regex:
```python
_ITEM_BALL_PARSE = re.compile(r"pbItemBall\(:(\w+)(?:,\s*(\d+))?\)")
```

Map symbol to `ITEM_*` constant: load
`output/uranium-build/intermediate/item_field_codes.json` (Phase 2 output,
maps internal symbol → `ITEM_*`). If the symbol is not in the map → fall
through to LLM.

### Output

```
script Map{m:03d}_{name}_Page1 {
    lock
    faceplayer
    finditem(ITEM_*, qty)
    setflag(FLAG_MAP{m:03d}_EVENT{e:03d}_SSA)
    release
    end
}

script Map{m:03d}_{name}_Page2 {
    end
}
```

`finditem` is the pokeemerald macro for ground-item pickup (shows the "found
X!" fanfare). Use qty from the call if present, else 1.

Self-switch A is set deterministically — it is also minted by
`_mint_event_switches` which runs after accept, so the registry handles it
correctly.

### Tests

1. Standard 2-page item ball → correct `finditem(ITEM_*, 1)`
2. Item ball with qty 2 → `finditem(ITEM_*, 2)`
3. Unknown item symbol → returns None (falls through to LLM)
4. Event with non-STRIP extra script call → returns None
5. Output compiles through poryscript

---

## 9. Classifier 6 — Trainer Battle

**Count: 299 events (8.3%), ~250 realistic clean matches**

This is the most complex classifier. Build it last and only after the first
three are working and tested.

### How Uranium trainer events work

The RMXP event structure for a standard route trainer:

**Page 1** (no condition — encounter state):
```
108  ["Battle: <pre-battle dialogue>"]          ← comment encoding
408  ["<continuation>"]
108  ["EndBattle: <already-beaten dialogue>"]   ← comment encoding
108  ["Type: FISHERMAN"]                        ← comment encoding
108  ["Name: Matt"]                             ← comment encoding
108  ["EndSpeech: <loss speech>"]               ← comment encoding (optional)
355  ["pbTrainerIntro(:FISHERMAN)"]
355  ["Kernel.pbNoticePlayer(get_character(0))"]
355  ["pbCallBub(2)"]                           ← optional
101  ["<pre-battle dialogue text>"]
401  ["<continuation>"]
111  [12, "pbTrainerBattle(PBTrainers::FISHERMAN,\"Matt\",_I(\"loss speech\"),...)"]
123  ["A", 0]                                   ← set self-switch A on win
412  []                                         ← end branch
355  ["pbTrainerEnd"]
```

**Page 2** (self-switch A = true — already beaten):
```
355  ["pbCallBub(2)"]
101  ["<already-beaten dialogue>"]
```

Key observations:
- Code 108/408 are **comment lines** that encode structured data — parse them
  for trainer type/name/speeches as they are more reliable than parsing the
  111 branch string.
- `pbTrainerBattle(...)` is the **condition** of a code-111 branch (type 12 =
  "script evaluation"), NOT a code-355 call. The return value is the
  win/loss boolean.
- The self-switch set (123) is inside the branch body (executed on win).
- `pbTrainerEnd` ends the encounter.

### Comment line parsing

Code-108 comments follow these prefixes (from `scripts_dump/`):
- `Battle: ` — pre-battle dialogue (may span multiple 108/408 lines)
- `EndBattle: ` — already-beaten dialogue
- `Type: ` — trainer class symbol (e.g. `FISHERMAN`)
- `Name: ` — trainer name string (e.g. `Matt`)
- `EndSpeech: ` — loss speech (what the trainer says when they lose)

Parse these directly. They are more reliable than extracting from the 111
branch string because the branch string may have escaping/interpolation.

### TRAINER_* constant lookup

The handler needs `TRAINER_FISHERMAN_MATT` from `(PBTrainers::FISHERMAN, "Matt")`.

Load `output/uranium-build/intermediate/trainers.json` (Phase 2 output).
The constant is keyed by `(class_internal_name, trainer_name, party_id)`.
Because a trainer can appear multiple times (rematches use `party_id > 0`),
the first encounter is `party_id = 0`.

If no match is found → fall through to LLM.

### Detection

An event qualifies if **all** of the following hold:

1. Has exactly **2 pages** (encounter + already-beaten)
2. Page 1 contains exactly **one** code-111 branch of type 12 whose
   parameter string matches `pbTrainerBattle\(` or `pbDoubleTrainerBattle\(`
3. Page 1 contains code 123 `["A", 0]` (self-switch A set on win)
4. Page 2 only has codes in `{0, 5, 6, 7, 101, 401, 355, 655}` with only
   STRIP script calls (pure dialogue page)
5. No extra code-111 branches anywhere beyond the trainer battle branch
   (guards against cutscene trainers with extra conditional logic)

Fall through to LLM for: gym leaders, story trainers, double-battle
partners, or any trainer with extra pre-battle cutscene codes (209 move
routes, 201 warps, 223 fades outside the battle branch).

### Output

```
script Map{m:03d}_{name}_Page1 {
    lock
    faceplayer
    msgbox("<pre-battle dialogue>")
    trainerbattle(TRAINER_*, "<pre-battle text label>", "<loss speech label>")
    setflag(FLAG_MAP{m:03d}_EVENT{e:03d}_SSA)
    release
    end
}

script Map{m:03d}_{name}_Page2 {
    lock
    faceplayer
    msgbox("<already-beaten dialogue>")
    release
    end
}
```

For double battles, use `trainerbattle_double(...)` — verify the exact
pokeemerald macro signature before emitting.

### Tests

1. Clean 2-page route trainer → correct `trainerbattle(TRAINER_*, ...)` + flag
2. Unknown trainer constant → returns None
3. Event with extra code-111 branches → returns None
4. Event with move route (209) → returns None
5. Double battle variant → correct `trainerbattle_double(...)` or None
6. Page 2 post-battle dialogue emitted correctly
7. Output compiles through poryscript
8. Run against the real corpus and print the match count + a few examples

---

## 10. Integration and acceptance

After all six classifiers are implemented:

1. Add a `--dry-run` count to `convert-map` or write a script
   `scripts/count_deterministic_actual.py` that runs `_try_deterministic`
   against the full corpus (no spawns) and reports how many events each
   classifier claimed.

2. Run `phase4 --clean` dry-counts: the 8/5/34/199 numbers must be unchanged
   (the pre-filter doesn't touch the registry seed).

3. Run the full pytest suite (including the `phase4` marker tests). The
   deterministic path must not break any existing test.

4. Re-run `calibrate_map002.sh` to confirm Map002 output is equivalent —
   Map002 has simple-warp events (EV002/EV008), pure-dialogue events, and
   call-common-event events (EV009/EV010/EV012) that should now all be handled
   deterministically. Verify the `.pory` file is functionally identical to the
   gate-approved run.

5. Present the final deterministic match counts to the user before starting
   the bulk `phase4 --run`.

---

## 11. What this does NOT cover

These patterns are explicitly out of scope for deterministic handling and
remain in the Opus path:

- Events with conditional branches (111) other than the trainer battle check
- Events with variable manipulation (122 / setvar / copyvar)
- Events with Uranium script calls that aren't STRIP-classified
- Move routes (209) — Phase-5 deferred per the gate decision
- Multi-page events where page-switching depends on global switches/variables
  (Phase-5 dispatch concern)
- Any event the classifier returns None for — the LLM path is unchanged and
  is the correct fallback

The goal is not to eliminate the LLM. It is to avoid spending Opus budget on
events where the output is fully determined by a direct structural read of the
input data.

---

## 12. Deferred deterministic candidates — validate against Opus at the end

Classifier 1's real numbers (measured 2026-06-04, `count_deterministic_actual.py`
+ the throwaway `_tmp_dropcause.py` per-event attribution):

| Stage | Events |
|---|---|
| pass the code filter | 458 (the plan's ~620 was optimistic; **458 is the real max**) |
| − non-trigger-0 (autorun) page | −7 → 451 |
| − dialogue control codes | −94 → **357** baseline |
| + `\PN` → `{PLAYER}` (prescribed by `system.md`) | +15 → **372 claimed** |

The 94 control-code drops attribute almost entirely to **two** codes:

- **`\PN` (16 events)** — player name. `system.md` prescribes `\PN` → `{PLAYER}`
  verbatim, so this is now handled deterministically (`_TEXT_SUBS`). 15 of the 16
  recovered (the 16th also carries `\.`).
- **`\sign[id]TEXT` (70 events)** — sign-window message, e.g.
  `\sign[sign1]Comet Cave, Rochfale City right ahead.`. **DEFERRED — do not claim
  yet.** It *looks* like `msgbox(TEXT, MSGBOX_SIGN)` (that compiles), but
  `system.md` says **nothing** about signs, so `MSGBOX_SIGN` is our inference, not
  a frozen-prompt spec — claiming it deterministically would be an unprescribed
  content decision on frozen territory. The remaining tail is `\.` (pause, 6) and
  one-off `\wt`/`\[`/`\N…`.

**The bucket to test at the end (after all six classifiers are built, before the
bulk run):** observe what frozen-Opus actually emits for a `\sign` event (one
spawn, budget-gated — fold into the Map002 re-run or a single sign-event check).
If Opus consistently produces `msgbox(…, MSGBOX_SIGN)`, that is evidence the idiom
is both deterministic and prompt-faithful, and `\sign` can be added to `_TEXT_SUBS`
the same way `\PN` was (~10 lines + tests + re-count) — **but only worth doing
pre-bulk-run**, since the pre-filter saves a spawn only if it claims the event
before Opus does. Suspicion (per the user): this "compiles-but-unprescribed"
pattern will recur in later classifiers (warp/item/trainer placeholders), so keep
a running list here as each classifier surfaces one, and validate them together at
the end against a small observed-Opus sample rather than guessing per-classifier.

**Running deferred-candidate list:**
- `\sign[..]` sign-window dialogue → likely `msgbox(…, MSGBOX_SIGN)` (70 events)
