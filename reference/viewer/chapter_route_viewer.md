# Chapter route viewer — design

**Status:** BUILT 2026-10-01 (approved same day). Code: `scripts/chapter_route_data.py`,
`scripts/map_viewer/chapter.{html,js,css}`, routes in `scripts/map_viewer_server.py`,
`render_map_png` in `scripts/map_viewer_common.py`, sidecar `src/rpg2gba/beat_gen/beats_sidecar.py`.
Implementation deviations are recorded inline below as *(built: …)* notes.
**Page:** `/chapter/<CHnn>` on `scripts/map_viewer_server.py` (same server, same Tailscale port).
**Purpose:** follow a *generated* chapter's beats in order, and see how the route reaches and
leaves each one. Mobile-first: the operator uses it from a phone more than half the time.

## 1. Why a new page (what the events view gets wrong)

- Its declared beats come from the **hand** suites only (`load_chapter` default `suite="hand"`);
  `chapters_gen/` is never read.
- Its planned route reads `reference/routes/*.route.json`, which holds only CH05, and that copy
  is stale against the generator's `output/beats/CH05.route.json`.
- It works one map at a time. The whole route is drawn at once, so retraced tiles hide the
  order and the pass count.
- Label fonts are clamped to 8–12 px every frame (`viewer.js:401`, `viewer.js:569`), so zoom
  never makes them readable. The canvas also ignores `devicePixelRatio`, so it renders soft on a
  phone.

## 2. Interaction model (operator-settled 2026-10-01)

- **The whole route is always drawn**, dimmed grey, as background.
- **Step beat by beat** with Prev/Next. Badges number **route groups** (`7`); the beats inside
  a group are sub-steps (`7a`, `7b`, …). A trainer's transit/main/re-talk beats are one spot
  with no walking between them.
- On the selected group, **to** (incoming segment) and **from** (outgoing segment) are
  highlighted in two colours with direction arrows. Other passes stay visible in the grey
  background.
- **Shared tiles get parallel lines.** Where to and from cover the same tile, each is offset
  ±k from the centreline, with the normal taken from the tile pair in *canonical* (sorted)
  order. Opposite-direction and same-direction overlaps therefore both separate. (An offset
  "to its own right" collides when the two run in opposite directions.)
- **Map labels are numbers only**, drawn in world units so they grow with zoom. They have a
  minimum tap size and are rendered at `devicePixelRatio`.
- A **Card** button opens the beat card as a bottom sheet.
- **Path source:** the planned route by default; a toggle switches to the ROM-walked path when
  a run exists.
- **One stitched canvas per chapter.** Warp jumps are drawn as dashed connectors, and stepping
  pans the camera.

## 3. Data — `GET /api/chapter/<CHnn>`

One JSON payload joined server-side in a new `scripts/chapter_route_data.py` (pure functions,
unit-tested).

| Need | Source |
|---|---|
| Group order, group cell/map, approach side | `output/beats/CHnn.route.json` `nodes[]` (not `reference/routes/`) |
| To/from tiles for group *i* | `segments[i-1]` / `segments[i]` `legs[].tiles`, plus `exit_warp` for connectors and `crossed_foreign_triggers` |
| Beats in a group, sub-step order | `load_chapter(CHnn, suite="gen")`, own beats (skip names containing `:`), grouped by `Beat.group == node.group` in registration order. **Not** `node.beats`, which lists only the primary beat (12 CH02 beats are missing from it). |
| Card fields | `CHnn.beats.json` sidecar (§4, pending approval) |
| Walked path | `output/playtest/observed_beats/<chapter>.json` `beats[].path`. Walked-to for group *i* is the paths of group *i*'s beats; walked-from is group *i+1*'s, because a beat's path includes its approach. Off-plan cells and violations carry through. |
| Chapter maps | union of `reference/chapters.json` `maps` and every `map_id` in route nodes/legs (CH02's route enters Moki, a CH01 map) |
| Map names | `map_infos.json` + `reference/map_name_overrides.json` (as `beat_gen` does) |

Degrades like the existing viewer: a missing artifact yields empty data plus a `notes[]`
message, not a 500.

## 4. Pipeline changes (§10 "schema of intermediate JSON")

**Scope rule (operator, 2026-10-01): hand-authored suites are excluded from this page entirely.**
Every beat, card, route and walked path shown comes from the generated suite (`suite="gen"`).
No hand-suite data is read, merged or shown, not even as a fallback.

1. **Beat-card sidecar — APPROVED 2026-10-01.** `beat_gen` writes `output/beats/CHnn.beats.json` next to
   `route.json`. Per own beat it records: name, group, template, the template call kwargs
   (event id, map id, direction/start_side/end_side, approach_prefer, mechanism), map name, the
   event cell, the `pick`, the description, the rows, and the assertions (kind, row, `offline`).
   It also records the chapter's order-dependent writes and refusals. All of this exists today
   only in the in-memory `ChapterPlan` and in `review.md` markdown; parsing the markdown is the
   brittle alternative.
2. **Suite tag on observed beats** (follows from the scope rule). Hand and gen runs both write
   `observed_beats/CHnn.json` (`runner.py:1209`), last run wins, and nothing records which suite
   ran. The runner adds `"suite": "hand"|"gen"` to the payload, an additive field. This page
   reads walked data **only** when `suite == "gen"`. A file that is hand-tagged or untagged
   (every file on disk today) is ignored with a `notes[]` message ("no generated-suite run on
   record; re-run with `--suite gen`"). The events view's reader is untouched.
   *(built: generated runs are written to `output/playtest-gen/` by the standing invocation
   `--output output/playtest-gen`, so `_load_observed` reads that directory first. A file there
   counts as gen unless it is explicitly tagged `hand`, which covers records from before the tag
   existed. The shared `output/playtest/` still requires an explicit `"suite": "gen"`.)*
3. *(built)* **Plan names ≠ runtime names.** The sidecar is keyed by the plan's beat names, but
   one template call can register under another name at load time (plan `…_item_ball_arms` →
   module `…_item_ball_spent`, trainer `…_arms` → `…_retalk1`). `_match_card` falls back to the
   same-group card that shares a row, then to the one that shares a name stem. The plan carries
   no description, so the loaded `Beat.description` fills it in.

## 5. Rendering

- **Per-map PNG endpoint** `/api/mappng/<id>.png?layer=gba` is composited server-side from the
  existing metatile renders and memory-cached. The chapter page draws one image per map instead
  of hundreds of 16 px tiles per map, which matters on a phone at fit-zoom.
- **Layout** (`chapter_layout(map_ids)`): outdoor maps are joined into seam clusters through
  `map_graph.component_layout`. Warp-only maps (interiors) are shelf-packed beside their
  cluster, ordered by first route visit. Each warp used by the route gets a dashed connector
  from the `exit_warp` cell to `dest_cell`. The output is `{members:[{id,name,ox,oy,w,h}],w,h}`,
  the same shape `/component` uses.
  *(built, operator-asked 2026-10-01: **borrowed maps are cropped.** A map that is on the route
  but not in the chapter's own `chapters.json` `maps` is cut to the bbox of every cell the page
  draws on it: route tiles, group cells, walked tiles and connector ends, padded by `CROP_PAD = 4`
  and clamped to the map. CH02's Moki Town goes from 72×64 to 18×11. Each map entry carries
  `crop: [x0, y0]`, the map-local cell drawn at `(ox, oy)`. The client offsets coordinates by it
  and draws that sub-rect of `/api/mappng`. The chapter's own maps are never cropped.)*
- **Colours** (Okabe-Ito, colour-blind safe): to `#0072B2` blue, from `#E69F00` orange,
  background route grey at 35 %, the selected badge filled. Crossed foreign triggers use the
  events view's X marker.

## 6. Mobile layout

```
┌──────────────────────────────┐
│ CH02 ▾   [Plan|Walk]   ⤢ fit │  top bar
│                              │
│        stitched canvas        │  pinch-zoom / drag-pan / tap badge = select
│                              │
├──────────────────────────────┤
│  ◀    7b / 23  m033e030…   ▶ │  bottom bar, thumb reach, 44 px targets
│           [ Card ]           │
└──────────────────────────────┘
```

The card is a bottom sheet (drag or tap to dismiss). It shows the number, beat name, template,
map and cell, approach/pick, the description, rows, assertions tagged `offline`/`ROM`, any
order-dependent writes touching its rows, and the last-run status when walked data exists. On
desktop the same sheet docks as a right panel. Nothing is hover-only. The selected step is in
the URL (`/chapter/CH02#7b`), so a view can be shared and survives a reload.

## 7. Build steps

| # | Work | Files (sole owner) |
|---|---|---|
| 1 | beat-card sidecar + test | `beat_gen/` writer, `tests/` |
| 2 | `suite` on observed beats + test | `playtest/runner.py`, `tests/` |
| 3 | join + layout + tests | `scripts/chapter_route_data.py`, `tests/test_chapter_route_data.py` |
| 4 | map PNG endpoint + test | `scripts/map_viewer_common.py` |
| 5 | front end | `scripts/map_viewer/chapter.{html,js,css}` |
| 6 | routes + handlers, wiring | `scripts/map_viewer_server.py` (lead) |

*(built: the page opens framed on the selected group's paths with 6 cells of context, capped at
24 px/cell. The ⤢ fit button shows the whole chapter. Fitting the whole chapter on load crowds
the badges on a phone. The background route is drawn as a dark casing under a light core so it
reads on any terrain.)*

Steps 1–4 are independent. Step 5 needs 3's payload shape (fixed by §3 before it starts).
Verification: unit tests plus a phone pass by the operator over Tailscale on a generated
chapter (CH02 has a ROM-green gen run).
