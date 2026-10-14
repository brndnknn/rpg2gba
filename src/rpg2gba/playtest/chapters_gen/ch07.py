"""GENERATED -- do not edit.

Chapter CH07. Regenerate with `python -m rpg2gba.beat_gen generate --chapter CH07`.
"""

from __future__ import annotations

from rpg2gba.playtest.archetypes.generic import generic_beat, obstacle_beat, seam_beat, transit_beat
from rpg2gba.playtest.archetypes.item_ball import item_ball_beats
from rpg2gba.playtest.archetypes.trainer import trainer_beats
from rpg2gba.playtest.chapter import ChapterBuilder

ch07 = ChapterBuilder('CH07', doc='beat_gen-generated module for CH07', predecessor='CH06', suite='gen')

transit_beat(
    ch07,
    chapter_id='CH07',
    beat_name='m035seamN14000_transit',
    group='m035seamN14000',
    hops=(('MAP_NOWTOCH_CITY', 11, 61, 'DOWN', 'MAP_ROUTE_02'),),
)

seam_beat(
    ch07,
    chapter_id='CH07',
    beat_name='m035seamN14000',
    group='m035seamN14000',
    rows=('map035/seam/N/map14000',),
    approach_prefer='UP@(17,0)',
)

generic_beat(
    ch07,
    chapter_id='CH07',
    beat_name='m035e023p0',
    group='m035e023p0',
    rows=('map035/ev023/p0', 'map035/ev023/p0/b0'),
    approach_prefer='south',
)

generic_beat(
    ch07,
    chapter_id='CH07',
    beat_name='m035e023p2',
    group='m035e023p2',
    rows=('map035/ev023/p2',),
    approach_prefer='south',
)

item_ball_beats(
    ch07,
    chapter_id='CH07',
    beat_prefix='m035e025_item_ball',
    group='m035e025_item_ball',
    approach_prefer='west',
    event_id=25,
    item='ITEM_SUPER_POTION',
    map_constant='MAP_ROUTE_02',
    map_id=35,
    negative_beat=True,
)

generic_beat(
    ch07,
    chapter_id='CH07',
    beat_name='m035e025_item_ball_arms',
    group='m035e025_item_ball',
    rows=('map035/ev025/p0/b0',),
    approach_prefer='west',
    skip_claimed=True,
)

trainer_beats(
    ch07,
    chapter_id='CH07',
    beat_prefix='m035e024_trainer',
    group='m035e024_trainer',
    approach_prefer='west',
    defeat_flag='TRAINER_FLAGS_START + TRAINER_CHUCK_279',
    double=False,
    event_id=24,
    map_constant='MAP_ROUTE_02',
    map_id=35,
    phone=False,
    retalk_pages=1,
    rider=False,
    trainer_const='TRAINER_CHUCK_279',
    trigger='event_touch',
)

generic_beat(
    ch07,
    chapter_id='CH07',
    beat_name='m035e024_trainer_arms',
    group='m035e024_trainer',
    rows=('map035/ev024/p0/b0',),
    approach_prefer='west',
    skip_claimed=True,
)

item_ball_beats(
    ch07,
    chapter_id='CH07',
    beat_prefix='m035e026_item_ball',
    group='m035e026_item_ball',
    approach_prefer='north',
    event_id=26,
    item='ITEM_TM78',
    map_constant='MAP_ROUTE_02',
    map_id=35,
    negative_beat=True,
)

generic_beat(
    ch07,
    chapter_id='CH07',
    beat_name='m035e026_item_ball_arms',
    group='m035e026_item_ball',
    rows=('map035/ev026/p0/b0',),
    approach_prefer='north',
    skip_claimed=True,
)

obstacle_beat(
    ch07,
    chapter_id='CH07',
    beat_name='m035obstacle_rock_smash',
    group='m035obstacle_rock_smash',
    rows=('map035/ev015/p0', 'map035/ev016/p0', 'map035/ev018/p0'),
    approach_prefer='east',
    capability='rock_smash',
)

generic_beat(
    ch07,
    chapter_id='CH07',
    beat_name='m035e019p0',
    group='m035e019p0',
    rows=('map035/ev019/p0', 'map035/ev019/p0/b2', 'map035/ev019/p0/b3', 'map035/ev019/p0/b4'),
    approach_prefer='south',
)

generic_beat(
    ch07,
    chapter_id='CH07',
    beat_name='m035e019p0_face_north_south_east',
    group='m035e019p0_face_north_south_east',
    rows=('map035/ev019/p0/b1',),
    approach_prefer='south',
)

generic_beat(
    ch07,
    chapter_id='CH07',
    beat_name='m035e019p1',
    group='m035e019p1',
    rows=('map035/ev019/p1',),
    approach_prefer='south',
)

seam_beat(
    ch07,
    chapter_id='CH07',
    beat_name='m035seamS031',
    group='m035seamS031',
    rows=('map035/seam/S/map031',),
    approach_prefer='DOWN@(20,56)',
)

NEVER_FIRES: dict[str, str] = {}

EMPTY_PAGES: dict[str, str] = {
    'map035/ev008/p0': 'every page of the event is empty; nothing to check on the ROM',
    'map035/ev020/p0': 'every page of the event is empty; nothing to check on the ROM',
    'map035/ev020/p1': 'every page of the event is empty; nothing to check on the ROM',
    'map035/ev021/p0': 'every page of the event is empty; nothing to check on the ROM',
    'map035/ev021/p1': 'every page of the event is empty; nothing to check on the ROM',
    'map035/ev022/p0': 'every page of the event is empty; nothing to check on the ROM',
    'map035/ev022/p1': 'every page of the event is empty; nothing to check on the ROM',
}

WALK_CHECKED: dict[str, str] = {}

ELSEWHERE: dict[str, str] = {
    'map035/ev001/p0': 'later: CH04',
    'map035/ev001/p1': 'later: CH04',
    'map035/ev001/p1/b0': 'later: CH04',
    'map035/ev001/p1/b1': 'later: CH04',
    'map035/ev002/p0': 'later: CH04',
    'map035/ev003/p0': 'later: CH04',
    'map035/ev003/p0/b0': 'later: CH04',
    'map035/ev003/p0/b1': 'later: CH04',
    'map035/ev003/p2': 'later: CH04',
    'map035/ev009/p0': 'later: CH04',
    'map035/ev009/p0/b0': 'later: CH04',
    'map035/ev009/p0/b1': 'later: CH04',
    'map035/ev009/p1': 'later: CH04',
    'map035/ev011/p0': 'later: CH04',
    'map035/ev012/p0': 'later: CH04',
    'map035/ev012/p0/b0': 'later: CH04',
    'map035/ev012/p0/b1': 'later: CH04',
    'map035/ev012/p1': 'later: CH04',
    'map035/ev013/p0': 'later: CH04',
    'map035/ev014/p0': 'later: CH04',
    'map035/ev017/p0': 'later: CH04',
    'map035/ev019/p0/b5': 'unselected_arm: not taken on the walk: else of `$game_player.y<=28` from cell (25, 27) (event at (25, 26)) (ruling 19)',
    'map035/ev023/p0/b1': 'unselected_arm: blocked by fork:whiteout; the walk takes the sibling arm (ruling 19)',
    'map035/ev024/p0/b1': 'unselected_arm: blocked by fork:whiteout; the walk takes the sibling arm (ruling 19)',
    'map035/ev025/p0/b1': 'unselected_arm: blocked by harness:full_bag; the walk takes the sibling arm (ruling 19)',
    'map035/ev026/p0/b1': 'unselected_arm: blocked by harness:full_bag; the walk takes the sibling arm (ruling 19)',
}

REFUSED: dict[str, str] = {
    'map035/ev003/p1': 'story-state: undetermined -- story model could not determine this row',
    'map035/ev003/p1/b0': 'story-state: unmodelled_outcome:phone_battle_count(trainer)',
    'map035/ev003/p1/b1': 'story-state: unmodelled_outcome:phone_battle_count(trainer)',
    'map035/ev003/p1/b2': 'story-state: unmodelled_outcome:phone_battle_count(trainer)',
    'map035/ev003/p1/b3': 'story-state: unmodelled_outcome:phone_battle_count(trainer)',
    'map035/ev003/p2/b0': 'story-state: unmodelled_outcome:phone_battle_count(trainer)',
    'map035/ev003/p2/b1': 'story-state: unmodelled_outcome:phone_battle_count(trainer)',
    'map035/ev019/p0/b0': "cell: no_facing_side -- group 'm035e019p0_face_west' runs only from ['west']; the event offers ['south']",
    'map035/ev023/p1': 'story-state: undetermined -- story model could not determine this row',
    'map035/ev023/p1/b0': 'story-state: unmodelled_outcome:phone_battle_count(trainer)',
    'map035/ev023/p1/b1': 'story-state: unmodelled_outcome:phone_battle_count(trainer)',
    'map035/ev023/p1/b2': 'story-state: unmodelled_outcome:phone_battle_count(trainer)',
    'map035/ev023/p1/b3': 'story-state: unmodelled_outcome:phone_battle_count(trainer)',
    'map035/ev023/p2/b0': 'story-state: unmodelled_outcome:phone_battle_count(trainer)',
    'map035/ev023/p2/b1': 'story-state: unmodelled_outcome:phone_battle_count(trainer)',
}

CHAPTER = ch07.build()
