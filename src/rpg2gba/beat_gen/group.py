"""Stage 2: owned rows -> planned beats (C6 Task 2).

Archetypes claim first (R11: "archetypes are layered on top"), then the
row-level shapes (obstacles, stairs, seams), then the generic template takes
every page row left. Branch-arm rows ride with the beat that owns their page.

STATUS: implemented (`assignments/C6/02_group.md`).
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence

from rpg2gba.beat_floor.assertion import RowFloor
from rpg2gba.beat_gen.plan import PlannedBeat, make_kwargs
from rpg2gba.chapter_manifest.archetypes import ArchetypeMatch
from rpg2gba.chapter_manifest.schema import ManifestRow, parse_row_id


def owning_page(row: ManifestRow) -> str:
    """The page row id a row belongs to: itself for a page row, the
    enclosing page for a branch arm at any nesting depth. Raises
    `ValueError` for seam/terrain rows, which have no page."""
    owner = parse_row_id(row.row_id).owning_page_row_id
    if owner is None:
        raise ValueError(f"{row.row_id}: kind {row.kind!r} has no owning page")
    return owner


def beat_name(template: str, rows: Sequence[ManifestRow], *, key: str = "") -> str:
    """The deterministic beat name for a beat claiming `rows` (see the
    naming table in the task file). A function of the rows (and `key`, for
    obstacle capability), never of position or a counter."""
    if template == "obstacle":
        map_id = rows[0].map_id
        return f"m{map_id:03d}obstacle_{key}"

    if template == "stair":
        map_id = rows[0].map_id
        assert all(r.terrain is not None for r in rows)
        x, y = min((r.terrain.x, r.terrain.y) for r in rows)  # type: ignore[union-attr]
        return f"m{map_id:03d}stair{x}x{y}"

    if template == "seam":
        seam = rows[0].seam
        assert seam is not None
        return f"m{seam.map_id:03d}seam{seam.direction}{seam.other_map_id:03d}"

    if template == "generic":
        pages = [r for r in rows if r.kind == "page"]
        if pages:
            p = pages[0]
            return f"m{p.map_id:03d}e{p.event_id:03d}p{p.page_idx}"
        # Arms only: the owning page itself isn't in `rows` (it's either
        # refused upstream or claimed elsewhere already). Derive the name
        # from the flat page-id the arms carry and suffix `_arms`.
        page_id = owning_page(rows[0])
        parsed = parse_row_id(page_id)
        return f"m{parsed.map_id:03d}e{parsed.event_id:03d}p{parsed.page_idx}_arms"

    # The five archetype templates: every row in `rows` shares one event.
    map_id = rows[0].map_id
    event_id = rows[0].event_id
    return f"m{map_id:03d}e{event_id:03d}_{template}"


def _connected_stair_components(cells: Sequence[ManifestRow]) -> list[list[ManifestRow]]:
    """Group terrain rows already filtered to one `(map_id, behavior)` key
    into staircases, under king-move (8-directional, diagonal-inclusive)
    adjacency (research doc §2c candidate C -- the only candidate that
    reproduces every hand-authored/hand-described staircase in the corpus,
    including CH02's diagonally-linked map033 run)."""
    coord = {r.row_id: (r.terrain.x, r.terrain.y) for r in cells}  # type: ignore[union-attr]
    by_id = {r.row_id: r for r in cells}
    ids = sorted(coord)
    visited: set[str] = set()
    components: list[list[ManifestRow]] = []
    for start in ids:
        if start in visited:
            continue
        stack = [start]
        comp_ids: list[str] = []
        while stack:
            cur = stack.pop()
            if cur in visited:
                continue
            visited.add(cur)
            comp_ids.append(cur)
            cx, cy = coord[cur]
            for other in ids:
                if other in visited:
                    continue
                ox, oy = coord[other]
                if max(abs(cx - ox), abs(cy - oy)) == 1:
                    stack.append(other)
        components.append([by_id[rid] for rid in comp_ids])
    return components


def deferred_retalks(match: ArchetypeMatch, rows_by_id: Mapping[str, ManifestRow]
                     ) -> tuple[str, ...]:
    """A trainer's retalk pages gated on a switch or variable -- state some
    OTHER beat writes -- in role order. They leave the trainer's group and
    take their own beat, ordered after their writer by the story model: in
    one indivisible group, a page needing a later write (the Nowtoch gym
    trainers' "trainers off" page, switch 58, set by the leader) forced the
    battle after that writer, a walk the ROM can't do (operator call
    2026-10-10). A self-switch-only retalk (the defeat's own write) stays."""
    if match.archetype != "trainer":
        return ()
    out = []
    for rid, role in match.roles.items():
        cond = rows_by_id[rid].condition if rid in rows_by_id else None
        if role == "retalk" and cond is not None and (
                cond.switch1_id is not None or cond.switch2_id is not None
                or cond.variable_id is not None):
            out.append(rid)
    return tuple(out)


def plan_beats(
    owned: Sequence[ManifestRow],
    matches: Sequence[ArchetypeMatch],
    floors: Mapping[str, RowFloor],
) -> tuple[PlannedBeat, ...]:
    """Every owned row claimed by exactly one planned beat.

    Returns beats ordered by their first row's manifest position (the
    route solver reorders them later, Task 4). Raises `ValueError` if any
    owned row would end up unclaimed or claimed twice."""
    owned_by_id = {r.row_id: r for r in owned}
    position = {r.row_id: i for i, r in enumerate(owned)}
    remaining: set[str] = set(owned_by_id)
    claimed: set[str] = set()
    # (sort_pos, arms_flag, PlannedBeat) -- arms_flag keeps an `_arms`
    # companion immediately after its principal even when both share a
    # sort_pos.
    staged: list[tuple[int, int, PlannedBeat]] = []

    def _claim(row_ids: Sequence[str]) -> None:
        dupes = claimed & set(row_ids)
        if dupes:
            raise ValueError(f"row(s) claimed twice: {sorted(dupes)}")
        claimed.update(row_ids)
        remaining.difference_update(row_ids)

    # --- 1. archetype matches, layered on top ------------------------------
    # Page-level archetypes can match more than one page of one event (a
    # multi-page NPC, a warp on two pages); those beats are named by page
    # so the names stay unique (C6 part two, CH01).
    per_event = Counter((m.archetype, m.map_id, m.event_id) for m in matches)
    for match in matches:
        deferred = deferred_retalks(match, owned_by_id)
        role_ids = [rid for rid in match.roles if rid not in deferred]
        if not all(rid in remaining for rid in role_ids):
            continue  # a half-owned match cannot register; falls to generic
        role_ids_sorted = sorted(role_ids, key=lambda rid: position[rid])
        main_rows = [owned_by_id[rid] for rid in role_ids_sorted]
        role_set = set(role_ids)
        arm_rows = [r for r in owned if r.row_id in remaining and r.kind == "branch"
                    and owning_page(r) in role_set]
        template = match.archetype
        if template == "warp" and main_rows[0].trigger == "action":
            # Ruling 11: a transfer on a talked-to page is an escort. It
            # fires once and never comes back, so its arms ride in the same
            # beat; `state_arms` drops the ones that firing doesn't take.
            template = "escort"
        main_name = beat_name(template, main_rows)
        if per_event[(match.archetype, match.map_id, match.event_id)] > 1:
            page = parse_row_id(role_ids_sorted[0]).page_idx
            main_name = f"m{match.map_id:03d}e{match.event_id:03d}p{page}_{template}"
        main_pos = position[role_ids_sorted[0]]
        if template == "escort":
            ids = role_ids_sorted + sorted((r.row_id for r in arm_rows),
                                           key=lambda rid: position[rid])
            _claim(ids)
            staged.append((main_pos, 0, PlannedBeat(
                name=main_name, template="escort", map_id=match.map_id,
                rows=tuple(ids), group=main_name)))
            continue
        _claim(role_ids_sorted)
        staged.append((main_pos, 0, PlannedBeat(
            name=main_name, template=match.archetype, map_id=match.map_id,
            rows=tuple(role_ids_sorted), group=main_name,
            kwargs=make_kwargs(deferred_retalks=deferred) if deferred else ())))

        if arm_rows:
            arm_ids = sorted((r.row_id for r in arm_rows), key=lambda rid: position[rid])
            _claim(arm_ids)
            arms_name = f"{main_name}_arms"
            staged.append((main_pos, 1, PlannedBeat(
                name=arms_name, template="generic", map_id=match.map_id,
                rows=tuple(arm_ids), group=main_name,
                kwargs=make_kwargs(skip_claimed=True))))

    # --- 2. obstacles: owned rows whose floor carries blocked_obstacle -----
    obstacle_groups: dict[tuple[int, str], list[str]] = {}
    for row in owned:
        if row.row_id not in remaining:
            continue
        floor = floors.get(row.row_id)
        if floor is None:
            continue
        caps = sorted({a.param("capability") for a in floor.assertions
                       if a.kind == "blocked_obstacle"})
        for cap in caps:
            obstacle_groups.setdefault((row.map_id, cap), []).append(row.row_id)
    for (map_id, cap), row_ids in obstacle_groups.items():
        row_ids_sorted = sorted(row_ids, key=lambda rid: position[rid])
        rows_objs = [owned_by_id[rid] for rid in row_ids_sorted]
        name = beat_name("obstacle", rows_objs, key=cap)
        pos = position[row_ids_sorted[0]]
        _claim(row_ids_sorted)
        staged.append((pos, 0, PlannedBeat(
            name=name, template="obstacle", map_id=map_id, rows=tuple(row_ids_sorted),
            group=name, kwargs=make_kwargs(capability=cap))))

    # --- 3. stairs: terrain rows grouped into staircases --------------------
    terrain_by_key: dict[tuple[int, str], list[ManifestRow]] = {}
    for row in owned:
        if row.row_id not in remaining or row.kind != "terrain":
            continue
        assert row.terrain is not None
        terrain_by_key.setdefault((row.map_id, row.terrain.behavior), []).append(row)
    for (map_id, _behavior), cells in terrain_by_key.items():
        for comp in _connected_stair_components(cells):
            row_ids_sorted = sorted((r.row_id for r in comp), key=lambda rid: position[rid])
            name = beat_name("stair", comp)
            pos = min(position[rid] for rid in row_ids_sorted)
            _claim(row_ids_sorted)
            staged.append((pos, 0, PlannedBeat(
                name=name, template="stair", map_id=map_id, rows=tuple(row_ids_sorted),
                group=name)))

    # --- 4. seams: one beat per seam row ------------------------------------
    for row in owned:
        if row.row_id not in remaining or row.kind != "seam":
            continue
        name = beat_name("seam", [row])
        pos = position[row.row_id]
        _claim([row.row_id])
        staged.append((pos, 0, PlannedBeat(
            name=name, template="seam", map_id=row.map_id, rows=(row.row_id,), group=name)))

    # --- 5a. everything else: each remaining page row + its owned arms -----
    for page in owned:
        if page.row_id not in remaining or page.kind != "page":
            continue
        arm_rows = sorted(
            (r for r in owned if r.row_id in remaining and r.kind == "branch"
             and owning_page(r) == page.row_id),
            key=lambda r: position[r.row_id])
        group_rows = [page, *arm_rows]
        row_ids_sorted = sorted((r.row_id for r in group_rows), key=lambda rid: position[rid])
        name = beat_name("generic", group_rows)
        pos = position[page.row_id]
        _claim(row_ids_sorted)
        staged.append((pos, 0, PlannedBeat(
            name=name, template="generic", map_id=page.map_id, rows=tuple(row_ids_sorted),
            group=name)))

    # --- 5b. arms whose page isn't planned at all: their own generic beat --
    orphan_groups: dict[str, list[ManifestRow]] = {}
    for row in owned:
        if row.row_id not in remaining or row.kind != "branch":
            continue
        orphan_groups.setdefault(owning_page(row), []).append(row)
    for _page_id, arm_rows in orphan_groups.items():
        row_ids_sorted = sorted((r.row_id for r in arm_rows), key=lambda rid: position[rid])
        name = beat_name("generic", arm_rows)
        pos = position[row_ids_sorted[0]]
        _claim(row_ids_sorted)
        staged.append((pos, 0, PlannedBeat(
            name=name, template="generic", map_id=arm_rows[0].map_id,
            rows=tuple(row_ids_sorted), group=name)))

    if remaining:
        raise ValueError(f"unclaimed owned rows: {sorted(remaining)}")

    staged.sort(key=lambda t: (t[0], t[1]))
    return tuple(beat for _, __, beat in staged)
