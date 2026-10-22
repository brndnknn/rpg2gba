"""GENERATED -- do not edit.

Chapter CH04. Regenerate with `python -m rpg2gba.beat_gen generate --chapter CH04`.
"""

from __future__ import annotations

from rpg2gba.playtest.archetypes.flavour_npc import flavour_npc_beat
from rpg2gba.playtest.archetypes.generic import generic_beat, obstacle_beat, seam_beat, transit_beat
from rpg2gba.playtest.archetypes.item_ball import item_ball_beats
from rpg2gba.playtest.archetypes.trainer import trainer_beats
from rpg2gba.playtest.archetypes.warp import warp_beat
from rpg2gba.playtest.chapter import ChapterBuilder

ch04 = ChapterBuilder('CH04', doc='beat_gen-generated module for CH04', predecessor='CH03', suite='gen')

transit_beat(
    ch04,
    chapter_id='CH04',
    beat_name='m035seamS031_transit',
    group='m035seamS031',
    hops=(('MAP_KEVLAR_TOWN', 32, 0, 'UP', 'MAP_ROUTE_02'),),
)

seam_beat(
    ch04,
    chapter_id='CH04',
    beat_name='m035seamS031',
    group='m035seamS031',
    rows=('map035/seam/S/map031',),
    approach_prefer='DOWN@(21,56)',
)

trainer_beats(
    ch04,
    chapter_id='CH04',
    beat_prefix='m035e012_trainer',
    group='m035e012_trainer',
    approach_prefer='east',
    defeat_flag='TRAINER_FLAGS_START + TRAINER_TIMOTHY_247',
    double=False,
    event_id=12,
    map_constant='MAP_ROUTE_02',
    map_id=35,
    phone=False,
    retalk_pages=1,
    rider=False,
    trainer_const='TRAINER_TIMOTHY_247',
    trigger='event_touch',
)

generic_beat(
    ch04,
    chapter_id='CH04',
    beat_name='m035e012_trainer_arms',
    group='m035e012_trainer',
    rows=('map035/ev012/p0/b0',),
    approach_prefer='east',
    skip_claimed=True,
)

generic_beat(
    ch04,
    chapter_id='CH04',
    beat_name='m035e003p0',
    group='m035e003p0',
    rows=('map035/ev003/p0', 'map035/ev003/p0/b0'),
    approach_prefer='south',
)

obstacle_beat(
    ch04,
    chapter_id='CH04',
    beat_name='m035obstacle_rock_smash',
    group='m035obstacle_rock_smash',
    rows=('map035/ev014/p0', 'map035/ev017/p0'),
    approach_prefer='west',
    capability='rock_smash',
)

flavour_npc_beat(
    ch04,
    chapter_id='CH04',
    beat_name='m035e013_flavour_npc',
    group='m035e013_flavour_npc',
    approach_prefer='east',
    event_id=13,
    map_constant='MAP_ROUTE_02',
    map_id=35,
    variant='plain',
)

item_ball_beats(
    ch04,
    chapter_id='CH04',
    beat_prefix='m035e009_item_ball',
    group='m035e009_item_ball',
    approach_prefer='north',
    event_id=9,
    item='ITEM_POTION',
    map_constant='MAP_ROUTE_02',
    map_id=35,
    negative_beat=True,
)

generic_beat(
    ch04,
    chapter_id='CH04',
    beat_name='m035e009_item_ball_arms',
    group='m035e009_item_ball',
    rows=('map035/ev009/p0/b0',),
    approach_prefer='north',
    skip_claimed=True,
)

flavour_npc_beat(
    ch04,
    chapter_id='CH04',
    beat_name='m035e011_flavour_npc',
    group='m035e011_flavour_npc',
    approach_prefer='south',
    event_id=11,
    map_constant='MAP_ROUTE_02',
    map_id=35,
    variant='plain',
)

generic_beat(
    ch04,
    chapter_id='CH04',
    beat_name='m035e003p2',
    group='m035e003p2',
    rows=('map035/ev003/p2',),
    approach_prefer='south',
)

generic_beat(
    ch04,
    chapter_id='CH04',
    beat_name='m035e002p0',
    group='m035e002p0',
    rows=('map035/ev002/p0',),
    approach_prefer='south',
)

warp_beat(
    ch04,
    chapter_id='CH04',
    beat_name='m035e001_warp',
    group='m035e001_warp',
    boundary=True,
    dest_map_constant='MAP_PASSAGE_CAVE_1F',
    direction='UP',
    event_id=1,
    map_constant='MAP_ROUTE_02',
    map_id=35,
    mechanism='threshold',
)

NEVER_FIRES: dict[str, str] = {}

EMPTY_PAGES: dict[str, str] = {
    'map035/ev008/p0': 'every page of the event is empty; nothing to check on the ROM',
    'map035/ev014/p1': "the obstacle's empty page, shown only once it is cleared: nothing to refuse there; the obstacle's own page carries the negative beat",
    'map035/ev015/p1': "the obstacle's empty page, shown only once it is cleared: nothing to refuse there; the obstacle's own page carries the negative beat",
    'map035/ev016/p1': "the obstacle's empty page, shown only once it is cleared: nothing to refuse there; the obstacle's own page carries the negative beat",
    'map035/ev017/p1': "the obstacle's empty page, shown only once it is cleared: nothing to refuse there; the obstacle's own page carries the negative beat",
    'map035/ev018/p1': "the obstacle's empty page, shown only once it is cleared: nothing to refuse there; the obstacle's own page carries the negative beat",
    'map035/ev020/p0': 'every page of the event is empty; nothing to check on the ROM',
    'map035/ev020/p1': 'every page of the event is empty; nothing to check on the ROM',
    'map035/ev021/p0': 'every page of the event is empty; nothing to check on the ROM',
    'map035/ev021/p1': 'every page of the event is empty; nothing to check on the ROM',
    'map035/ev022/p0': 'every page of the event is empty; nothing to check on the ROM',
    'map035/ev022/p1': 'every page of the event is empty; nothing to check on the ROM',
}

WALK_CHECKED: dict[str, str] = {}

ELSEWHERE: dict[str, str] = {
    'map035/ev001/p1': "later: CH05: its event crosses out of the chapter's map chain (to map(s) [36]); the rest of the event belongs to the chapter that builds the far side",
    'map035/ev001/p1/b0': "later: CH05: its event crosses out of the chapter's map chain (to map(s) [36]); the rest of the event belongs to the chapter that builds the far side",
    'map035/ev001/p1/b1': "later: CH05: its event crosses out of the chapter's map chain (to map(s) [36]); the rest of the event belongs to the chapter that builds the far side",
    'map035/ev003/p0/b1': 'unselected_arm: blocked by fork:whiteout; the walk takes the sibling arm (ruling 19)',
    'map035/ev003/p1': 'unreachable',
    'map035/ev009/p0/b1': 'unselected_arm: blocked by harness:full_bag; the walk takes the sibling arm (ruling 19)',
    'map035/ev012/p0/b1': 'unselected_arm: blocked by fork:whiteout; the walk takes the sibling arm (ruling 19)',
    'map035/ev015/p0': 'later: CH06',
    'map035/ev016/p0': 'later: CH06',
    'map035/ev018/p0': 'later',
    'map035/ev023/p1': 'unreachable',
    'map035/seam/N/map040': 'later: CH06',
}

REFUSED: dict[str, str] = {
    'map035/ev003/p1/b0': 'story-state: unmodelled_outcome:phone_battle_count(trainer)',
    'map035/ev003/p1/b1': 'story-state: unmodelled_outcome:phone_battle_count(trainer)',
    'map035/ev003/p1/b2': 'story-state: unmodelled_outcome:phone_battle_count(trainer)',
    'map035/ev003/p1/b3': 'story-state: unmodelled_outcome:phone_battle_count(trainer)',
    'map035/ev003/p2/b0': 'story-state: unmodelled_outcome:phone_battle_count(trainer)',
    'map035/ev003/p2/b1': 'story-state: unmodelled_outcome:phone_battle_count(trainer)',
    'map035/ev023/p1/b0': 'story-state: unmodelled_outcome:phone_battle_count(trainer)',
    'map035/ev023/p1/b1': 'story-state: unmodelled_outcome:phone_battle_count(trainer)',
    'map035/ev023/p1/b2': 'story-state: unmodelled_outcome:phone_battle_count(trainer)',
    'map035/ev023/p1/b3': 'story-state: unmodelled_outcome:phone_battle_count(trainer)',
    'map035/ev023/p2/b0': 'story-state: unmodelled_outcome:phone_battle_count(trainer)',
    'map035/ev023/p2/b1': 'story-state: unmodelled_outcome:phone_battle_count(trainer)',
}

CHAPTER = ch04.build()
