"""GENERATED -- do not edit.

Chapter CH05. Regenerate with `python -m rpg2gba.beat_gen generate --chapter CH05`.
"""

from __future__ import annotations

from rpg2gba.playtest.archetypes.arrival_nudge import arrival_nudge_beat
from rpg2gba.playtest.archetypes.generic import generic_beat, stair_beat, transit_beat
from rpg2gba.playtest.archetypes.item_ball import item_ball_beats
from rpg2gba.playtest.archetypes.trainer import trainer_beats
from rpg2gba.playtest.archetypes.warp import warp_beat
from rpg2gba.playtest.chapter import ChapterBuilder

ch05 = ChapterBuilder('CH05', doc='beat_gen-generated module for CH05', predecessor='CH04', suite='gen')

warp_beat(
    ch05,
    chapter_id='CH05',
    beat_name='m035e001_warp',
    group='m035e001_warp',
    dest_map_constant='MAP_PASSAGE_CAVE_1F',
    direction='UP',
    end_side='dest',
    event_id=1,
    manifest_chapter_id='CH04',
    map_constant='MAP_ROUTE_02',
    map_id=35,
    mechanism='threshold',
    start_side='origin',
)

warp_beat(
    ch05,
    chapter_id='CH05',
    beat_name='m036e001_warp',
    group='m036e001_warp',
    dest_map_constant='MAP_ROUTE_02',
    direction='DOWN',
    end_side='dest',
    event_id=1,
    map_constant='MAP_PASSAGE_CAVE_1F',
    map_id=36,
    mechanism='threshold',
    start_side='origin',
)

arrival_nudge_beat(
    ch05,
    chapter_id='CH05',
    beat_name='m035e001_arrival_nudge',
    group='m035e001_arrival_nudge',
    event_id=1,
    from_event_id=1,
    from_map_constant='MAP_PASSAGE_CAVE_1F',
    manifest_chapter_id='CH04',
    map_constant='MAP_ROUTE_02',
    map_id=35,
)

generic_beat(
    ch05,
    chapter_id='CH05',
    beat_name='m035e001_arrival_nudge_arms',
    group='m035e001_arrival_nudge',
    rows=('map035/ev001/p1/b0',),
    manifest_chapter_id='CH04',
    skip_claimed=True,
)

transit_beat(
    ch05,
    chapter_id='CH05',
    beat_name='m036e003_item_ball_transit',
    group='m036e003_item_ball',
    hops=(('MAP_ROUTE_02', 20, 34, 'UP', 'MAP_PASSAGE_CAVE_1F'),),
)

item_ball_beats(
    ch05,
    chapter_id='CH05',
    beat_prefix='m036e003_item_ball',
    group='m036e003_item_ball',
    approach_prefer='east',
    event_id=3,
    item='ITEM_ESCAPE_ROPE',
    map_constant='MAP_PASSAGE_CAVE_1F',
    map_id=36,
    negative_beat=True,
)

generic_beat(
    ch05,
    chapter_id='CH05',
    beat_name='m036e003_item_ball_arms',
    group='m036e003_item_ball',
    rows=('map036/ev003/p0/b0',),
    approach_prefer='east',
    skip_claimed=True,
)

trainer_beats(
    ch05,
    chapter_id='CH05',
    beat_prefix='m036e004_trainer',
    group='m036e004_trainer',
    approach_prefer='east',
    defeat_flag='TRAINER_FLAGS_START + TRAINER_MANNY_5',
    double=False,
    event_id=4,
    map_constant='MAP_PASSAGE_CAVE_1F',
    map_id=36,
    phone=False,
    retalk_pages=1,
    rider=False,
    trainer_const='TRAINER_MANNY_5',
    trigger='event_touch',
)

generic_beat(
    ch05,
    chapter_id='CH05',
    beat_name='m036e004_trainer_arms',
    group='m036e004_trainer',
    rows=('map036/ev004/p0/b0',),
    approach_prefer='east',
    skip_claimed=True,
)

trainer_beats(
    ch05,
    chapter_id='CH05',
    beat_prefix='m036e006_trainer',
    group='m036e006_trainer',
    approach_prefer='east',
    defeat_flag='TRAINER_FLAGS_START + TRAINER_KEICHI_248',
    double=False,
    event_id=6,
    map_constant='MAP_PASSAGE_CAVE_1F',
    map_id=36,
    phone=False,
    retalk_pages=1,
    rider=False,
    trainer_const='TRAINER_KEICHI_248',
    trigger='event_touch',
)

generic_beat(
    ch05,
    chapter_id='CH05',
    beat_name='m036e006_trainer_arms',
    group='m036e006_trainer',
    rows=('map036/ev006/p0/b0',),
    approach_prefer='east',
    skip_claimed=True,
)

warp_beat(
    ch05,
    chapter_id='CH05',
    beat_name='m036e002_warp',
    group='m036e002_warp',
    dest_map_constant='MAP_PASSAGE_CAVE_2F',
    direction='UP',
    end_side='dest',
    event_id=2,
    map_constant='MAP_PASSAGE_CAVE_1F',
    map_id=36,
    mechanism='threshold',
    start_side='origin',
)

warp_beat(
    ch05,
    chapter_id='CH05',
    beat_name='m037e001_warp',
    group='m037e001_warp',
    dest_map_constant='MAP_PASSAGE_CAVE_1F',
    direction='DOWN',
    end_side='dest',
    event_id=1,
    map_constant='MAP_PASSAGE_CAVE_2F',
    map_id=37,
    mechanism='threshold',
    start_side='origin',
)

arrival_nudge_beat(
    ch05,
    chapter_id='CH05',
    beat_name='m036e002_arrival_nudge',
    group='m036e002_arrival_nudge',
    event_id=2,
    from_event_id=1,
    from_map_constant='MAP_PASSAGE_CAVE_2F',
    map_constant='MAP_PASSAGE_CAVE_1F',
    map_id=36,
)

generic_beat(
    ch05,
    chapter_id='CH05',
    beat_name='m036e002_arrival_nudge_arms',
    group='m036e002_arrival_nudge',
    rows=('map036/ev002/p1/b0',),
    skip_claimed=True,
)

item_ball_beats(
    ch05,
    chapter_id='CH05',
    beat_prefix='m036e005_item_ball',
    group='m036e005_item_ball',
    approach_prefer='west',
    event_id=5,
    item='ITEM_GREAT_BALL',
    map_constant='MAP_PASSAGE_CAVE_1F',
    map_id=36,
    negative_beat=True,
)

generic_beat(
    ch05,
    chapter_id='CH05',
    beat_name='m036e005_item_ball_arms',
    group='m036e005_item_ball',
    rows=('map036/ev005/p0/b0',),
    approach_prefer='west',
    skip_claimed=True,
)

transit_beat(
    ch05,
    chapter_id='CH05',
    beat_name='m037e004_trainer_transit',
    group='m037e004_trainer',
    hops=(('MAP_PASSAGE_CAVE_1F', 17, 5, 'UP', 'MAP_PASSAGE_CAVE_2F'),),
)

trainer_beats(
    ch05,
    chapter_id='CH05',
    beat_prefix='m037e004_trainer',
    group='m037e004_trainer',
    approach_prefer='south',
    defeat_flag='TRAINER_FLAGS_START + TRAINER_NUNES_128',
    double=False,
    event_id=4,
    map_constant='MAP_PASSAGE_CAVE_2F',
    map_id=37,
    phone=False,
    retalk_pages=1,
    rider=False,
    trainer_const='TRAINER_NUNES_128',
    trigger='event_touch',
)

generic_beat(
    ch05,
    chapter_id='CH05',
    beat_name='m037e004_trainer_arms',
    group='m037e004_trainer',
    rows=('map037/ev004/p0/b0',),
    approach_prefer='south',
    skip_claimed=True,
)

stair_beat(
    ch05,
    chapter_id='CH05',
    beat_name='m037stair20x9',
    group='m037stair20x9',
    rows=('map037/terrain/stairs/20,9', 'map037/terrain/stairs/20,10'),
    approach_prefer='east',
)

stair_beat(
    ch05,
    chapter_id='CH05',
    beat_name='m037stair11x9',
    group='m037stair11x9',
    rows=('map037/terrain/stairs/11,9', 'map037/terrain/stairs/11,10'),
    approach_prefer='west',
)

generic_beat(
    ch05,
    chapter_id='CH05',
    beat_name='m037e005p0',
    group='m037e005p0',
    rows=('map037/ev005/p0', 'map037/ev005/p0/b0'),
    approach_prefer='south',
)

generic_beat(
    ch05,
    chapter_id='CH05',
    beat_name='m037e005p1',
    group='m037e005p1',
    rows=('map037/ev005/p1',),
    approach_prefer='south',
)

warp_beat(
    ch05,
    chapter_id='CH05',
    beat_name='m037e002_warp',
    group='m037e002_warp',
    boundary=True,
    dest_map_constant='MAP_NOWTOCH_CITY',
    direction='UP',
    event_id=2,
    map_constant='MAP_PASSAGE_CAVE_2F',
    map_id=37,
    mechanism='threshold',
)

NEVER_FIRES: dict[str, str] = {}

EMPTY_PAGES: dict[str, str] = {}

WALK_CHECKED: dict[str, str] = {}

ELSEWHERE: dict[str, str] = {
    'map035/ev001/p1/b1': 'unselected_arm: not taken on the walk: else of `get_character(0).onEvent?` from cell (20, 33) (event at (20, 33)) (ruling 19)',
    'map036/ev002/p1/b1': 'unselected_arm: not taken on the walk: else of `get_character(0).onEvent?` from cell (17, 4) (event at (17, 4)) (ruling 19)',
    'map036/ev003/p0/b1': 'unselected_arm: blocked by harness:full_bag; the walk takes the sibling arm (ruling 19)',
    'map036/ev004/p0/b1': 'unselected_arm: blocked by fork:whiteout; the walk takes the sibling arm (ruling 19)',
    'map036/ev005/p0/b1': 'unselected_arm: blocked by harness:full_bag; the walk takes the sibling arm (ruling 19)',
    'map036/ev006/p0/b1': 'unselected_arm: blocked by fork:whiteout; the walk takes the sibling arm (ruling 19)',
    'map037/ev004/p0/b1': 'unselected_arm: blocked by fork:whiteout; the walk takes the sibling arm (ruling 19)',
    'map037/ev005/p0/b1': 'unselected_arm: blocked by harness:full_bag; the walk takes the sibling arm (ruling 19)',
}

REFUSED: dict[str, str] = {}

CHAPTER = ch05.build()
