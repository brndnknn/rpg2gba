# C6 Task 3 (seam) — measured data

**Dated 2026-09-21.** Measured data for the operator to design and implement `beat_gen/seam.py`
against — **not a solution, not a recommendation.** All numbers below came from throwaway
scripts under `/tmp/c6research/` (`seam1.py`..`seam6.py`), run once against real repo data
(`output/uranium-build/maps/`, `output/uranium-build/tilesets.json`,
`reference/manifests/CH0{1,3,4}.manifest.json`, `reference/map_name_overrides.json`,
`output/uranium-build/map_infos.json`). No dialogue or story content is quoted; map names,
row ids, and cell coordinates only.

---

## 0. Map identity (needed to check the task file / README naming claims)

From `output/uranium-build/map_infos.json` (`name` field; none of these five ids have an
entry in `reference/map_name_overrides.json`'s `overrides`, so the bare `map_infos` name is
authoritative):

| map id | `map_infos.json` name |
|---|---|
| 31 | Kevlar Town |
| 32 | Moki Town |
| 35 | Route 02 |
| 40 | Nowtoch City |
| 59 | Route 03 |

**The task file (`assignments/C6/03_seam.md` line 23) calls `map031/N/map035` "the Route 1 →
Route 2 seam". That is wrong: map031 is Kevlar Town, not a Route.** The README's phrasing
("the Kevlar x=31/x=32 case", `assignments/C6/README.md`... via A1) matches the data — map031
is Kevlar Town and map035 is Route 02. So this is a real seam: Kevlar Town → Route 02, not
Route 1 → Route 2.

---

## 1. The offset formula, worked example, and the four real seam rows

### 1a — Formula in plain terms (from `routing/connections.py` module docstring,
lines 1–61, and `tileset_converter/connections.py` lines 13–93)

`connections.json` rows store, per map, an **anchor point on that map's own edge**, in that
map's own local grid: `N -> (offset, 0)`, `S -> (offset, height)`, `W -> (0, offset)`,
`E -> (width, offset)`. The two anchors of one row name the *same point in world space*. So a
cell at distance `k` from one map's anchor along the shared axis corresponds to the cell at
distance `k` from the other map's anchor:

```
shared_axis_to = shared_axis_from - offset_from + offset_to
```

equivalently `shift = offset_from - offset_to`, `axis_to = axis_from - shift`
(`routing/connections.py:162,172-173,184-185`). This was cross-checked against
`engine/src/fieldmap.c` `FillNorthConnection`/`FillSouthConnection`/`FillWestConnection`/
`FillEastConnection` (`routing/connections.py:37-47`).

### 1b — The module's own worked example (`routing/connections.py:49-52`)

CH04 seam, `connections.json` row `[31, "N", 11, 35, "S", 0]`: shift = 11 − 0 = 11. Map031's
local column `x` (N edge, row 0) lines up with Map035's local column `x − 11` (S edge, row
`height − 1`) — e.g. Map031 `(11, 0)` ↔ Map035 `(0, 56)`.

### 1c — Applied to all four real seam rows (`load_chapter_rows`, `seam1.py`; each `SeamRef`
below is the row's field values verbatim)

| Chapter | row_id | SeamRef (map/dir/offset → other_map/other_dir/other_offset) | from dims (w×h) | to dims (w×h) | shift = offset − to_offset | mapping |
|---|---|---|---|---|---|---|
| CH01 | `map032/seam/E/map059` | 32/E/26 → 59/W/0 | 72×64 | 130×66 | 26 | `x_to(row) = y_from - 26`* |
| CH03 | `map031/seam/N/map035` | 31/N/11 → 35/S/0 | 50×50 | 42×57 | 11 | `x_to(col) = x_from - 11` |
| CH04a | `map035/seam/N/map040` | 35/N/0 → 40/S/15 | 42×57 | 79×74 | −15 | `x_to(col) = x_from + 15` |
| CH04b | `map035/seam/S/map031` | 35/S/0 → 31/N/11 | 42×57 | 50×50 | −11 | `x_to(col) = x_from + 11` |

\* CH01 is an E/W seam: the shared axis is `y` (row), not `x` (column); `crossing_cells`
walks `y_from` in `range(from_graph.height)` and maps to `y_to = y_from - shift`
(`routing/connections.py:183-189`).

CH03 (`map031/N/map035`) and CH04b (`map035/S/map031`) are the two directed halves of the
**same physical connection** (Kevlar Town ↔ Route 02) — confirmed identical in
`connections.json` (§2 below) and already documented in
`assignments/C6/research/02_group.md` §6 ("a seam appears once per map it touches").

---

## 2. `SeamRef` ↔ `MapConnection`: field correspondence, and cross-check against `connections.json`

### 2a — Field mapping

| `SeamRef` field (`chapter_manifest/schema.py:335-340`) | `MapConnection` field (`routing/connections.py:100-104`) | Notes |
|---|---|---|
| `map_id` | `from_map` | direct |
| `direction` (str `"N"/"S"/"E"/"W"`) | `direction` (`Direction` enum) | needs the edge-letter table (§3) to convert |
| `offset` | `offset` | direct, same raw `connections.json` number |
| `other_map_id` | `to_map` | direct |
| `other_offset` | `to_offset` | direct |
| `other_direction` | *(no `MapConnection` field)* | implied — should equal `direction`'s `Direction.opposite` under the edge-letter mapping; `MapConnection` doesn't store it because `crossing_cells` never needs it |

Confirmed by the test file itself (`tests/test_beat_gen_seam.py:39-41`,
`test_connection_for_maps_every_field`): `SeamRef(map_id=31, direction="N", offset=11,
other_map_id=35, other_direction="S", other_offset=0)` must map to
`MapConnection(from_map=31, direction=Direction.NORTH, offset=11, to_map=35, to_offset=0)`.

**Direction/offset are expressed from *this row's own map's side*, not the other's** — same
convention as `connections.json` itself (`tileset_converter/connections.py:15-16`: "`edge_a`/
`edge_b` are single-letter compass directions ... for THAT map's own border the seam sits
on"). `SeamRef.direction`/`SeamRef.offset` describe `SeamRef.map_id`'s own edge; `MapConnection
.direction`/`.offset` describe `from_map`'s own edge identically — the two are the same
quantity under the same convention, no sign flip needed for `direction`/`offset` (only for
resolving `to_offset` off the *other* map, which is what `other_offset` already is).

### 2b — Cross-check: does a matching `MapConnection` already exist in `connections.json`
for every seam row, and do the numbers agree? (`load_connections()`, `connections_between()`,
`seam2.py`)

`load_connections()` returns 28 directed `MapConnection`s total (14 undirected rows ×2).

| Seam row | `connections_between` result | Agrees with `SeamRef`? |
|---|---|---|
| `map032/seam/E/map059` (32/E/26→59/W/0) | `MapConnection(from_map=32, direction=EAST, offset=26, to_map=59, to_offset=0)` | Yes, exactly |
| `map031/seam/N/map035` (31/N/11→35/S/0) | `MapConnection(from_map=31, direction=NORTH, offset=11, to_map=35, to_offset=0)` | Yes, exactly |
| `map035/seam/N/map040` (35/N/0→40/S/15) | `MapConnection(from_map=35, direction=NORTH, offset=0, to_map=40, to_offset=15)` | Yes, exactly |
| `map035/seam/S/map031` (35/S/0→31/N/11) | `MapConnection(from_map=35, direction=SOUTH, offset=0, to_map=31, to_offset=11)` | Yes, exactly |

Every one of the four seam rows' `SeamRef` numbers agree bit-for-bit with the corresponding
directed `MapConnection` already derivable from `connections.json` via the existing loader.

---

## 3. Edge-letter → `Direction` tables in `src/`, and what `Direction` provides

### 3a — Every N/S/E/W → direction table found in `src/rpg2gba` (`seam2.py` grep, verified by read)

| Name | File:line | Maps to | Purpose |
|---|---|---|---|
| `_EDGE_TO_DIRECTION` (private) | `routing/connections.py:79-84` | `"N"→Direction.NORTH`, `"S"→Direction.SOUTH`, `"E"→Direction.EAST`, `"W"→Direction.WEST` | the traversal-graph `Direction` enum — exactly what `seam.py`'s `connection_for` needs |
| `EDGE_TO_DIRECTION` (public) | `tileset_converter/connections.py:109` | `"N"→"up"`, `"S"→"down"`, `"W"→"left"`, `"E"→"right"` | pokeemerald C schema strings — a *different* target type, not reusable for `Direction` |
| `EDGE_OPPOSITE` (public) | `tileset_converter/connections.py:112` | `"N"↔"S"`, `"E"↔"W"` (string→string) | opposite-edge validation, not a `Direction` mapping |

No other N/S/E/W-keyed table exists in `src/rpg2gba` (confirmed by grepping for `"N":` /
`'N':` patterns repo-wide, `seam2.py`/manual grep). The task file's hint about "a private
edge-letter table" refers to `_EDGE_TO_DIRECTION` at `routing/connections.py:79`, the only one
whose values are the `Direction` enum this module needs.

### 3b — `Direction` (`traversal/direction.py`)

| Member | Value | File:line |
|---|---|---|
| `Direction.NORTH/SOUTH/EAST/WEST` | enum, string values `"north"`/etc. | `direction.py:14-18` |
| `.delta` property | `(dx, dy)` for one step, y grows downward | `direction.py:20-24`, table `direction.py:31-36` |
| `.opposite` property | the reverse `Direction` | `direction.py:26-28`, table `direction.py:38-43` |
| `CARDINALS` | tuple of all four, in N/S/E/W declared order | `direction.py:45-50` |

**`Direction` has no built-in press-name string** ("UP"/"DOWN"/"LEFT"/"RIGHT") — only `.delta`
(dx, dy) and `.opposite`. No existing `Direction → "UP"/"DOWN"/"LEFT"/"RIGHT"` table exists
anywhere in `src/rpg2gba`; the closest-named tables (`beat_floor/terrain.py:50`
`_STEP_DIR_BY_FACING`, `tileset_converter/npc_gfx.py:58,76,80` `_DIRECTION_TO_FACING` etc.)
key on RMXP's int facing codes (2/4/6/8), not on `traversal.direction.Direction`, so they are
not directly reusable as-is for `SeamCrossing.press`. *(Lead check: also
`playtest/assertions.py:304` maps the engine's `"DIR_NORTH"`-style strings to `"UP"` etc.
Again, the keys aren't the enum. A grep for dicts keyed by `Direction.` members finds only
`direction.py`'s own two tables. Note that Task 5's `route_kwargs` needs the same
side→press mapping, so whatever you write here, Task 5 can reuse.)*

---

## 4. `crossing_cells` raise-vs-empty behaviour, and what "walkable" means

### 4a — Raise vs. empty (`routing/connections.py`)

- **Raises `ValueError`** at lines 193–200, guarded by the `any_overlap` flag set at line 175
  (N/S branch) or 187 (E/W branch) *only* when at least one `x_from`/`y_from` maps to an
  in-bounds `x_to`/`y_to` on the other map (lines 173, 185: `if not (0 <= x_to < to_graph.width):
  continue`). If **no** step along the shared axis lands in-bounds on the other side, the two
  edges don't overlap at all under the formula and it raises — "these two maps do not actually
  share an edge" (line 199).
- **Returns an empty tuple, not a raise**, when the edges *do* overlap geometrically but every
  overlapping cell pair fails the walkability check (`from_graph.is_walkable(exit_cell) and
  to_graph.is_walkable(entry_cell)`, lines 178/190) — nothing is appended to `pairs`, the loop
  finishes, `any_overlap` is `True`, and line 203 (`return tuple(pairs)`) returns `()`. Two of
  `crossing_cells`'s two `ValueError` raises (lines 152-155, 156-160) are a third, unrelated
  case: the caller passed a `MapGraph` whose `map_id` doesn't match the connection's
  `from_map`/`to_map` — a caller bug, not a data property of the seam itself.

### 4b — "walkable" (`is_walkable`, `traversal/graph.py:157-172`)

`is_walkable(cell)`: `False` if out of bounds (`in_bounds`, line 147-149); `False` if the cell
is a ledge (`is_ledge`, never a resting cell); `True` unconditionally if the cell is a
staircase (force-passable, per Phase 5's `behavior_overrides`); otherwise `not
self.blocked.get(cell, True)` — i.e. plain collision, missing key defaults to blocked. Fields
used: `MapGraph.blocked` (raw collision dict), `MapGraph.ledge_directions`,
`MapGraph.stair_sides` — all populated by `build_map_graph` (`traversal/graph.py:313-369`)
from `collision.py`, `stairs.stair_cell_sides`, and `ledges.derive_ledge_direction`
respectively. Warps are not consulted by `is_walkable` at all (module docstring,
`graph.py:73-82`).

---

## 5. Per-seam crossing counts, landing-filter survivors, and every excluded pair

All four maps' graphs build without error via bare `build_map_graph(map_id)` (no missing-map
exceptions) — `seam2.py`:

| map id | width×height | tileset_id |
|---|---|---|
| 31 | 50×50 | 22 |
| 32 | 72×64 | 22 |
| 35 | 42×57 | 22 |
| 40 | 79×74 | 23 |
| 59 | 130×66 | 24 |

*(Lead note: "builds a graph" is not the same as "in this chapter's ROM". Map 40 is CH06's map:
its RMXP data is in `output/uranium-build`, so Task 3 can compute crossings into it, but CH04's
build doesn't stage it. That's the same situation as Task 9's boundary-warp blocker, and
`map035/seam/N/map040` is its seam twin. The seam doesn't hit this in part one, because CH04 is
part two's scope.)*

(No to_map failed to build for any of the four real seam rows — all five participating map ids
staged. This item is N/A for Task 4/9's "unstaged map" concern on the current corpus, but the
scenario the task file flags — a to_map graph that can't be built — was not exercised here
since it doesn't occur in CH01–CH04's actual seam rows.)

`crossing_cells` pair counts, and survivors after manually applying the landing-open filter
described in `03_seam.md` ("the cell one further step in the same direction must be walkable
too") — `seam3.py`:

| Seam | `crossing_cells` pairs (both ends walkable) | survive landing-open filter | excluded by landing filter |
|---|---|---|---|
| CH01 `map032/E→map059/W` | 31 | 31 | 0 |
| CH03 `map031/N→map035/S` | 29 | **28** | 1 |
| CH04a `map035/N→map040/S` | 37 | 36 | 1 |
| CH04b `map035/S→map031/N` | 29 | 29 | 0 |

**Every excluded pair, with reason** (all are "landing blocked", not "out of bounds" — the
landing cell in every excluded case is in-bounds on its map but collision-blocked):

| Seam | exit_cell | entry_cell | landing cell | reason |
|---|---|---|---|---|
| CH03 | `(31, 0)` | `(20, 56)` | `(20, 55)` | landing blocked |
| CH04a | `(16, 0)` | `(31, 73)` | `(31, 72)` | landing blocked |

No excluded pair in any of the four seams was "out of bounds" — `crossing_cells` already
excludes out-of-bounds `x_to`/`y_to` via its own bounds check before walkability is even
considered (§4a), so nothing out-of-bounds ever reaches the landing filter.

### 5a — The Kevlar (map031↔map035) x=31/x=32 case, confirmed tile-by-tile (`seam4.py`)

`shift = 11`. For `x_from` in `{30, 31, 32, 33}`, `x_to = x_from − 11`, `entry row = 56`,
`landing row = 55`:

| x_from (exit col, map031) | exit `(x,0)` walkable | x_to (entry col, map035) | entry `(x,56)` walkable | landing `(x,55)` walkable |
|---|---|---|---|---|
| 30 | True | 19 | **False** | False |
| 31 | True | 20 | True | **False** ← excluded here |
| 32 | True | 21 | True | True ← included |
| 33 | True | 22 | True | True |

This matches `test_real_kevlar_seam_x31_closed_x32_open` exactly: `x=31` is a
`crossing_cells`-legal pair (both `exit`/`entry` walkable) that the landing filter removes;
`x=32` survives. **Measured total: 28 crossings survive** (`seam4.py` printed the full sorted
list of 28 exit-`x` values: `11-17, 19-24, 32-36, 38, 41-49`), matching the test's pinned `28`.
`x=30` is excluded earlier, by `crossing_cells` itself (entry cell not walkable), not by the
landing filter — a distinct kind of exclusion from `x=31`'s.

---

## 6. Q2 data — is one step always enough?

For every seam, for every landing-filter survivor, the size of the walkable connected
component (`MapGraph.connected_components()`, undirected closure) containing the *landing*
cell, versus the largest component on that `to_map` — `seam5.py`:

| Seam | to_map | # components | largest component size | survivors landing in a smaller component |
|---|---|---|---|---|
| CH01 (→map059) | 59 | 83 | 1257 | 26 / 31 |
| CH03 (→map035) | 35 | 31 | 412 | 23 / 28 |
| CH04a (→map040) | 40 | 77 | 1777 | 4 / 36 |
| CH04b (→map031) | 31 | 69 | 565 | 23 / 29 |

*(Lead check, 2026-09-21: "smaller than the largest component" is not the same as "a pocket".
Measured distribution of landing-component sizes, as {component size: number of legal
crossings landing in it}:*

| Seam | landing component sizes |
|---|---|
| 32→59 | {4: 3, 51: 12, 887: 11, 1257: 5} |
| 31→35 | {2: 1, 60: 9, 69: 13, 412: 5} |
| 35→40 | {1172: 4, 1777: 32} |
| 35→31 | {3: 1, 39: 6, 48: 7, 297: 9, 565: 6} |

*So each seam has only 0–3 true dead ends (2–4 cells). The 39–69-cell regions are real areas
separated from the rest of the map. Whether they connect back through something `MapGraph`
doesn't model (warps, stairs across elevation) hasn't been checked. Script:
`/tmp/c6research/verify_seam_components.py`.)*

**Smallest observed pockets** (landing open, but the reachable region from the landing is
small): CH03 exit `(38, 0)` → entry `(27, 56)`, component size **2**; CH01 several exits with
component size **4** (e.g. exit `(71, 39)/(71, 40)/(71, 50)` → entries `(0,13)/(0,14)/(0,24)`).
Every survivor's landing component is listed in the script output; the table above gives
counts, not an exhaustive per-cell list (available in `/tmp/c6research/seam_CH0*.pkl` if
needed, not part of this doc per the scratch-script convention).

**Reverse check** — excluded pairs (landing blocked) whose *entry* cell still has another
walkable neighbor sideways (`MapGraph.neighbors`, `seam5.py`):

| Seam | excluded entry cell | sideways neighbor found |
|---|---|---|
| CH03 | `(20, 56)` | `(21, 56)`, kind `walk`, press `EAST` |
| CH04a | `(31, 73)` | `(32, 73)`, kind `walk`, press `EAST` |

Both excluded (landing-blocked) entry cells in the corpus have exactly one sideways walkable
neighbor — a player who somehow stood there could still step off sideways; the seam crossing
itself just doesn't continue straight through.

---

## 7. Sortedness

`SeamCrossing` (`beat_gen/seam.py:24-32`) is `@dataclass(frozen=True, order=True)` with fields
declared `exit_cell, entry_cell, press`. Python dataclass ordering compares fields as a tuple
in declaration order, so `sorted()` sorts first by `exit_cell` (itself a `(x, y)` tuple,
compared elementwise), then `entry_cell`, then `press` (string) — confirmed with a standalone
3-instance sort in `seam6.py` (ties on `exit_cell`/`entry_cell` fall through to `press`
string comparison, e.g. `"DOWN" < "UP"`).

Within one `seam_crossings()` call, `press` is constant for every result (one seam row has one
direction), so in practice the sort key reduces to `exit_cell` alone — the same key
`crossing_cells` already sorts its own `pairs` list by (`connections.py:202`,
`pairs.sort()` on `(exit_cell, entry_cell)` tuples). Since `exit_cell.x` is monotonically
related to `entry_cell` under the offset formula (both walk the same shared axis in lockstep,
possibly with direction reversed for E/W's `y` axis or for a negative shift), no case in the
four real seams produces two crossings with the same `exit_cell` — `press` never actually
becomes a tie-breaker on real data (unverified for a hypothetical row where the same map
appears on both sides of two different seams sharing an exit cell — no such case exists in
CH01–CH05's four seam rows).

---

## Decisions left to you

- **Whether to reuse `routing.connections._EDGE_TO_DIRECTION` (private) or write your own
  4-entry table.** It's the only existing "N/S/E/W string → `Direction` enum" table in
  `src/rpg2gba` (§3a); `tileset_converter.connections.EDGE_TO_DIRECTION` maps to a different
  target type (pokeemerald direction strings) and isn't a drop-in substitute. The task file
  says pick one and don't write both.
- **The press-name table (`Direction` → `"UP"/"DOWN"/"LEFT"/"RIGHT"`).** No existing table in
  `src/rpg2gba` maps `traversal.direction.Direction` to these four strings (§3b) — the nearest
  analogues key on RMXP int facing codes, a different domain. You'll write this table
  regardless of the edge-letter reuse decision.
- **What "one step is always enough" means for the route solver vs. the seam resolver
  (Task 3's Question 2).** §6 gives concrete small-pocket cases (component size as low as 2)
  and the reverse case (blocked-landing entries that still have a sideways walkable neighbor).
  Whether a `SeamCrossing` landing in a small pocket should be filtered here or left for the
  route solver to discover (and how it would discover it — a `crossing_cells`-shaped
  fixed-cost check per candidate, vs. a full BFS) is not decided by any test in
  `tests/test_beat_gen_seam.py`; none of the eight synthetic tests exercise a pocket smaller
  than the whole map.
- **Whether `connection_for`'s `MapConnection` construction should assert
  `SeamRef.other_direction` is the opposite of `SeamRef.direction`** (§2a) — `MapConnection`
  doesn't carry `other_direction` at all, so this would be a pure consistency check, not
  something the return value encodes either way. Not exercised by any test.
- **The out-of-bounds vs. blocked-landing distinction (§4a, §5).** All excluded pairs measured
  in the real corpus are "landing blocked," never "out of bounds" (`crossing_cells` already
  filters out-of-bounds before either graph's `is_walkable` runs). Whether your landing check
  needs its own explicit in-bounds guard (vs. relying on `is_walkable`'s own `in_bounds` check,
  `graph.py:166-167`, returning `False` for an out-of-bounds landing) is a real corpus-observed
  non-issue either way, but the two `MapGraph`s differ in size, so a landing one step past a
  to_map edge cell could go out of that map's bounds in a case not present in CH01–CH04.
