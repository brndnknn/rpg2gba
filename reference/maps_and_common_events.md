# Maps and Common Events — how they relate (and how rpg2gba converts the link)

> Hand-authored explainer (2026-06-14). Audience: humans + the build agent.
> Numbers are from the deserialized corpus (`output/uranium-build/`): 199 maps,
> 5,301 map events, 8,429 pages, **100 common events**. Advisory; the deserializer
> + `orchestrator.convert_common_events` are authoritative.

## TL;DR

A **map event** is local, positioned, and multi-page; it lives in one map. A
**common event** is a single global, map-independent script with no position,
no graphic, and no pages. Maps reach common events two ways: an event **calls**
one (RMXP code `117`, like a subroutine), or the engine **auto-runs** one while a
switch is on (trigger = autorun/parallel). rpg2gba emits each common event **once**
as a Poryscript `CommonEvent_<NNN>` block and rewrites every `117` call site to
`call CommonEvent_<NNN>`.

---

## 1. Two different containers

| | **Map event** | **Common event** |
|---|---|---|
| Lives in | `maps/Map{NNN}.json` → `events[]` | `common_events.json` (one flat list of 100) |
| Scope | one map | global, all maps |
| Identity | `(map_id, event_id)` — per-map | `id` 1–100 — global |
| Has a position (`x`,`y`)? | yes | no |
| Has a graphic / sprite? | yes (per page) | no |
| Has **pages**? | yes — multiple, condition-gated | **no** — a single `list` of commands |
| Has a self-switch? | yes (A–D, per event) | **no** (no event id to hang one on) |
| Trigger | per page: action/touch/autorun/parallel | per event: none / autorun / parallel |

Field shapes from the actual JSON:

```
map event:     { id, name, x, y, pages: [ { condition, graphic, trigger, ... , list:[cmd,...] }, ... ] }
common event:  { id, name, trigger, switch_id, list:[cmd,...] }     # flat — no pages
```

The key structural difference: **a common event is just a command `list`** — the
same shape as a single map-event *page*, minus everything spatial. That is exactly
why it can be shared: it carries no map-specific state of its own.

---

## 2. The two ways a map connects to a common event

### 2a. Explicit call — RMXP code `117` "Call Common Event" (the subroutine link)

A map event's command list contains `117 [N]`, which runs common event `N`'s
command list inline, then returns. In the corpus:

- **73 call sites** across the maps, referencing **6 distinct** common events:

| CE id | name | # calls | # maps | what it is |
|---|---|---|---|---|
| 4 | `GTS/WT` | 12 | 11 | online GTS / Wonder-Trade receptionist logic |
| 5 | `VT` | 12 | 11 | online battle (PVP) receptionist logic |
| 6 | `LOBBY` | 12 | 11 | online lobby receptionist logic |
| 87 | `Fennel Guide` | 17 | 11 | a revisit/guide helper reused across rooms |
| 12 | `Abyssal Venesi Reset` | 19 | 1 | a single map's repeated reset routine |
| 86 | `Fennel Follow` | 1 | 1 | one-off helper |

The first three are the textbook case: the **same three online-service
receptionists appear in ~11 different Pokémon Centers**. Rather than copy the
lobby logic into 11 maps × 3 events, each receptionist event is just
`117 [4]` / `117 [5]` / `117 [6]`. One definition, many call sites — DRY.

> **Caller-context semantics (important gotcha).** A called common event executes
> *inside the calling event's interpreter*. So a `get_character(0)` / "this event"
> reference, a self-switch, or a **move route targeting "this event" (target `0`)**
> inside the CE acts on **the event that called it**. CE 5 (`VT`) literally contains
> `209 [0, …]` (Set Move Route, target 0 = this event) — when receptionist A calls
> it the routine turns receptionist A; when receptionist B calls it, it turns B.
> One CE, correct behaviour for every caller. This is why the shared receptionists
> can include an NPC turn/animation in the common logic.

### 2b. Trigger-based — autorun / parallel (the switch link, *no* call site)

A common event can also have `trigger = 1` (autorun) or `trigger = 2` (parallel
process) plus a `switch_id`. The engine runs it **on its own**, continuously,
**whenever that switch is ON** — nothing "calls" it. In the corpus:

- **97** common events are `trigger = 0` ("None" → run only when called via `117`).
- **0** autorun.
- **3** parallel (`trigger = 2`), each gated by a switch:

| CE id | name | switch | meaning |
|---|---|---|---|
| 10 | `RACING-Main` | 53 | racing minigame loop (runs while switch 53 on) |
| 11 | `RACING-Mini` | 53 | racing minigame loop |
| 51 | `Only Day people` | 51 | time-of-day gated background routine |

These are **not** reached by any `117`; they are background loops toggled by a
global switch. (The racing pair is already a §10 fidelity call: STUB now →
**Phase 8 ADAPT** — see Decisions Made.)

### How many actually matter

Of the 100 common events, **only 22 have real commands** — the other 78 are
empty placeholders. Of those 22, 6 are call targets (2a) and 3 are switch loops
(2b); the rest are defined-but-currently-unreferenced.

---

## 3. How rpg2gba converts the relationship (Phase 4)

The pipeline preserves the call structure rather than inlining it:

| Uranium | rpg2gba output |
|---|---|
| `common_events.json` CE `N` (has commands) | one `script CommonEvent_<NNN> { … }` block in `scripts/CommonEvents.pory`, emitted **once** by `orchestrator.convert_common_events` |
| `117 [N]` inside a map event | `call CommonEvent_<NNN>` inside that event's `.pory` script |
| CE `N` marked STRIP (`reference/strip_list.json`) | a **stub** `CommonEvent_<NNN>` block is still emitted — STRIP ≠ delete, so every `call` site stays valid (no dangling symbol at assembly) |
| CE `N` with `trigger` 1/2 (switch loop) | **not** a `call`; handled per-feature (e.g. racing → ADAPT), not via the call mechanism |

Two consequences worth remembering:

- **Ordering:** the common-event pass must run **before fork assembly**, so that
  every `call CommonEvent_<NNN>` in a map `.pory` resolves to a defined block.
- **One spend, many reuses:** because a CE is converted once, the 11 Pokémon-Center
  receptionists cost one conversion of CE 4/5/6 plus a cheap `call` per site — the
  same DRY win the original game got.

---

## 4. Worked example — end to end

**Uranium source.** Map 2 (a Pokémon Center) has event 9, "Receptionist PVP".
Its page-1 command list is simply a call:

```
Map002 event 9 "Receptionist PVP", page 1:
  117 [5]      # Call Common Event 5 ("VT")
  0            # (list terminator)
```

Common event 5, "VT" (`trigger 0`, an online-battle lobby routine):

```
CE005 "VT":
  111 [6, -1, 2]                # conditional branch
  101 ["Stuck are we?"]         # show text
  209 [0, {MoveRoute…}]         # set move route on target 0 = the CALLING event
  509 …                         # move-route body
  …
```

**rpg2gba output.** The map event becomes a script that calls the shared block:

```poryscript
script Map002_EV009_Receptionist_PVP_Page1 {
    lock
    faceplayer
    call CommonEvent_005
    release
    ...
}
```

…and CE 5 is emitted once in `CommonEvents.pory`. In this build it resolves to a
STRIP stub (the online services are tagged unavailable, so the routine is replaced
by an "unavailable" message instead of dropped — keeping the call valid):

```poryscript
script CommonEvent_005 {
    # STRIPPED: online (phase0: scripts 233/235/236) (strip_list.json)
    msgbox("The Tandor Network is currently unavailable.")
    end
}
```

So the relationship "map event 9 on Map 2 → shared online-lobby routine" survives
the conversion intact as `call CommonEvent_005`, and the same `call` appears in the
ten other Pokémon Centers' receptionist events — one definition, eleven callers.

---

## 5. Quick reference — gotchas

- **A CE is a page, not an event.** No pages, no graphic, no position, no
  self-switch of its own. If you need per-instance state, it lives on the *calling*
  map event, not the CE.
- **Caller context.** `this event` / target `0` move routes / self-switches inside
  a CE bind to whichever map event called it (see §2a).
- **Two link types, don't conflate.** `117` = explicit subroutine call; `trigger
  1/2 + switch` = engine-driven background loop. Only the first becomes a `call`.
- **STRIP keeps the wiring.** A stripped or unbuilt CE still emits a stub block so
  `call CommonEvent_<NNN>` never dangles at fork assembly.
- **Most CEs are empty.** 78/100 have no commands; 6 are real call targets, 3 are
  switch loops.
- **Reproduce the numbers:** walk `output/uranium-build/maps/*.json` for `code==117`
  (`parameters[0]` = CE id) and read `output/uranium-build/common_events.json` for
  triggers/switch gating.
```
