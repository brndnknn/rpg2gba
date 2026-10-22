"""GENERATED -- do not edit.

Chapter CH09. Regenerate with `python -m rpg2gba.beat_gen generate --chapter CH09`.
"""

from __future__ import annotations

from rpg2gba.playtest.archetypes.arrival_nudge import arrival_nudge_beat
from rpg2gba.playtest.archetypes.flavour_npc import flavour_npc_beat
from rpg2gba.playtest.archetypes.generic import generic_beat, seam_beat, stair_beat, transit_beat
from rpg2gba.playtest.archetypes.item_ball import item_ball_beats
from rpg2gba.playtest.archetypes.trainer import trainer_beats
from rpg2gba.playtest.archetypes.warp import warp_beat
from rpg2gba.playtest.chapter import ChapterBuilder

ch09 = ChapterBuilder('CH09', doc='beat_gen-generated module for CH09', predecessor='CH08', suite='gen')

transit_beat(
    ch09,
    chapter_id='CH09',
    beat_name='m059seamW032_transit',
    group='m059seamW032',
    hops=(('MAP_MOKI_TOWN', 71, 43, 'RIGHT', 'MAP_ROUTE_03'),),
)

seam_beat(
    ch09,
    chapter_id='CH09',
    beat_name='m059seamW032',
    group='m059seamW032',
    rows=('map059/seam/W/map032',),
    approach_prefer='LEFT@(0,19)',
)

trainer_beats(
    ch09,
    chapter_id='CH09',
    beat_prefix='m059e050_trainer',
    group='m059e050_trainer',
    approach_prefer='north',
    defeat_flag='TRAINER_FLAGS_START + TRAINER_SHAUNA_249',
    double=False,
    event_id=50,
    map_constant='MAP_ROUTE_03',
    map_id=59,
    phone=False,
    retalk_pages=1,
    rider=False,
    trainer_const='TRAINER_SHAUNA_249',
    trigger='event_touch',
)

generic_beat(
    ch09,
    chapter_id='CH09',
    beat_name='m059e050_trainer_arms',
    group='m059e050_trainer',
    rows=('map059/ev050/p0/b0',),
    approach_prefer='north',
    skip_claimed=True,
)

flavour_npc_beat(
    ch09,
    chapter_id='CH09',
    beat_name='m059e035_flavour_npc',
    group='m059e035_flavour_npc',
    approach_prefer='south',
    event_id=35,
    map_constant='MAP_ROUTE_03',
    map_id=59,
    variant='plain',
)

item_ball_beats(
    ch09,
    chapter_id='CH09',
    beat_prefix='m059e051_item_ball',
    group='m059e051_item_ball',
    approach_prefer='south',
    event_id=51,
    item='ITEM_TM19',
    map_constant='MAP_ROUTE_03',
    map_id=59,
    negative_beat=True,
)

generic_beat(
    ch09,
    chapter_id='CH09',
    beat_name='m059e051_item_ball_arms',
    group='m059e051_item_ball',
    rows=('map059/ev051/p0/b0',),
    approach_prefer='south',
    skip_claimed=True,
)

item_ball_beats(
    ch09,
    chapter_id='CH09',
    beat_prefix='m059e037_item_ball',
    group='m059e037_item_ball',
    approach_prefer='south',
    event_id=37,
    item='ITEM_BURN_HEAL',
    map_constant='MAP_ROUTE_03',
    map_id=59,
    negative_beat=True,
)

generic_beat(
    ch09,
    chapter_id='CH09',
    beat_name='m059e037_item_ball_arms',
    group='m059e037_item_ball',
    rows=('map059/ev037/p0/b0',),
    approach_prefer='south',
    skip_claimed=True,
)

warp_beat(
    ch09,
    chapter_id='CH09',
    beat_name='m059e023_warp',
    group='m059e023_warp',
    dest_map_constant='MAP_ROUTE_03_HOUSE',
    direction='UP',
    end_side='dest',
    event_id=23,
    map_constant='MAP_ROUTE_03',
    map_id=59,
    mechanism='threshold',
    start_side='origin',
)

flavour_npc_beat(
    ch09,
    chapter_id='CH09',
    beat_name='m054e003_flavour_npc',
    group='m054e003_flavour_npc',
    approach_prefer='west',
    event_id=3,
    map_constant='MAP_ROUTE_03_HOUSE',
    map_id=54,
    variant='plain',
)

flavour_npc_beat(
    ch09,
    chapter_id='CH09',
    beat_name='m054e004_flavour_npc',
    group='m054e004_flavour_npc',
    approach_prefer='south',
    event_id=4,
    map_constant='MAP_ROUTE_03_HOUSE',
    map_id=54,
    variant='plain',
)

item_ball_beats(
    ch09,
    chapter_id='CH09',
    beat_prefix='m054e001_item_ball',
    group='m054e001_item_ball',
    approach_prefer='east',
    event_id=1,
    item='ITEM_NET_BALL',
    map_constant='MAP_ROUTE_03_HOUSE',
    map_id=54,
    negative_beat=True,
)

generic_beat(
    ch09,
    chapter_id='CH09',
    beat_name='m054e001_item_ball_arms',
    group='m054e001_item_ball',
    rows=('map054/ev001/p0/b0',),
    approach_prefer='east',
    skip_claimed=True,
)

flavour_npc_beat(
    ch09,
    chapter_id='CH09',
    beat_name='m054e005_flavour_npc',
    group='m054e005_flavour_npc',
    approach_prefer='north',
    event_id=5,
    map_constant='MAP_ROUTE_03_HOUSE',
    map_id=54,
    variant='plain',
)

warp_beat(
    ch09,
    chapter_id='CH09',
    beat_name='m054e002_warp',
    group='m054e002_warp',
    dest_map_constant='MAP_ROUTE_03',
    direction='DOWN',
    end_side='dest',
    event_id=2,
    map_constant='MAP_ROUTE_03_HOUSE',
    map_id=54,
    mechanism='threshold',
    start_side='origin',
)

arrival_nudge_beat(
    ch09,
    chapter_id='CH09',
    beat_name='m059e023_arrival_nudge',
    group='m059e023_arrival_nudge',
    event_id=23,
    from_event_id=2,
    from_map_constant='MAP_ROUTE_03_HOUSE',
    map_constant='MAP_ROUTE_03',
    map_id=59,
)

generic_beat(
    ch09,
    chapter_id='CH09',
    beat_name='m059e023_arrival_nudge_arms',
    group='m059e023_arrival_nudge',
    rows=('map059/ev023/p1/b0',),
    skip_claimed=True,
)

generic_beat(
    ch09,
    chapter_id='CH09',
    beat_name='m059e024p0',
    group='m059e024p0',
    rows=('map059/ev024/p0',),
    approach_prefer='arrive@(31,27)',
)

item_ball_beats(
    ch09,
    chapter_id='CH09',
    beat_prefix='m059e013_item_ball',
    group='m059e013_item_ball',
    approach_prefer='north',
    event_id=13,
    item='ITEM_RARE_CANDY',
    map_constant='MAP_ROUTE_03',
    map_id=59,
    negative_beat=True,
)

generic_beat(
    ch09,
    chapter_id='CH09',
    beat_name='m059e013_item_ball_arms',
    group='m059e013_item_ball',
    rows=('map059/ev013/p0/b0',),
    approach_prefer='north',
    skip_claimed=True,
)

flavour_npc_beat(
    ch09,
    chapter_id='CH09',
    beat_name='m059e004_flavour_npc',
    group='m059e004_flavour_npc',
    approach_prefer='north',
    event_id=4,
    map_constant='MAP_ROUTE_03',
    map_id=59,
    variant='plain',
)

trainer_beats(
    ch09,
    chapter_id='CH09',
    beat_prefix='m059e012_trainer',
    group='m059e012_trainer',
    approach_prefer='north',
    defeat_flag='TRAINER_FLAGS_START + TRAINER_LARA_21',
    double=False,
    event_id=12,
    map_constant='MAP_ROUTE_03',
    map_id=59,
    phone=False,
    retalk_pages=1,
    rider=False,
    trainer_const='TRAINER_LARA_21',
    trigger='event_touch',
)

generic_beat(
    ch09,
    chapter_id='CH09',
    beat_name='m059e012_trainer_arms',
    group='m059e012_trainer',
    rows=('map059/ev012/p0/b0',),
    approach_prefer='north',
    skip_claimed=True,
)

generic_beat(
    ch09,
    chapter_id='CH09',
    beat_name='m059e026p0',
    group='m059e026p0',
    rows=('map059/ev026/p0',),
    approach_prefer='south',
)

trainer_beats(
    ch09,
    chapter_id='CH09',
    beat_prefix='m059e027_trainer',
    group='m059e027_trainer',
    approach_prefer='north',
    defeat_flag='TRAINER_FLAGS_START + TRAINER_JOHNNY_22',
    double=False,
    event_id=27,
    map_constant='MAP_ROUTE_03',
    map_id=59,
    phone=False,
    retalk_pages=1,
    rider=False,
    trainer_const='TRAINER_JOHNNY_22',
    trigger='event_touch',
)

generic_beat(
    ch09,
    chapter_id='CH09',
    beat_name='m059e027_trainer_arms',
    group='m059e027_trainer',
    rows=('map059/ev027/p0/b0',),
    approach_prefer='north',
    skip_claimed=True,
)

generic_beat(
    ch09,
    chapter_id='CH09',
    beat_name='m059e024p1',
    group='m059e024p1',
    rows=('map059/ev024/p1',),
    approach_prefer='east',
)

trainer_beats(
    ch09,
    chapter_id='CH09',
    beat_prefix='m059e031_trainer',
    group='m059e031_trainer',
    approach_prefer='east',
    defeat_flag='TRAINER_FLAGS_START + TRAINER_JULIANNA_250',
    double=False,
    event_id=31,
    map_constant='MAP_ROUTE_03',
    map_id=59,
    phone=False,
    retalk_pages=1,
    rider=False,
    trainer_const='TRAINER_JULIANNA_250',
    trigger='event_touch',
)

generic_beat(
    ch09,
    chapter_id='CH09',
    beat_name='m059e031_trainer_arms',
    group='m059e031_trainer',
    rows=('map059/ev031/p0/b0',),
    approach_prefer='east',
    skip_claimed=True,
)

stair_beat(
    ch09,
    chapter_id='CH09',
    beat_name='m059stair43x32',
    group='m059stair43x32',
    rows=('map059/terrain/stairs/43,32', 'map059/terrain/stairs/43,33', 'map059/terrain/stairs/44,30', 'map059/terrain/stairs/44,31'),
    approach_prefer='east',
)

generic_beat(
    ch09,
    chapter_id='CH09',
    beat_name='m059e009p0',
    group='m059e009p0',
    rows=('map059/ev009/p0', 'map059/ev009/p0/b0'),
    approach_prefer='south',
)

generic_beat(
    ch09,
    chapter_id='CH09',
    beat_name='m059e009p2',
    group='m059e009p2',
    rows=('map059/ev009/p2',),
    approach_prefer='south',
)

item_ball_beats(
    ch09,
    chapter_id='CH09',
    beat_prefix='m059e034_item_ball',
    group='m059e034_item_ball',
    approach_prefer='south',
    event_id=34,
    item='ITEM_TM49',
    map_constant='MAP_ROUTE_03',
    map_id=59,
    negative_beat=True,
)

generic_beat(
    ch09,
    chapter_id='CH09',
    beat_name='m059e034_item_ball_arms',
    group='m059e034_item_ball',
    rows=('map059/ev034/p0/b0',),
    approach_prefer='south',
    skip_claimed=True,
)

trainer_beats(
    ch09,
    chapter_id='CH09',
    beat_prefix='m059e029_trainer',
    group='m059e029_trainer',
    approach_prefer='north',
    defeat_flag='TRAINER_FLAGS_START + TRAINER_MARC_41',
    double=False,
    event_id=29,
    map_constant='MAP_ROUTE_03',
    map_id=59,
    phone=False,
    retalk_pages=1,
    rider=False,
    trainer_const='TRAINER_MARC_41',
    trigger='event_touch',
)

generic_beat(
    ch09,
    chapter_id='CH09',
    beat_name='m059e029_trainer_arms',
    group='m059e029_trainer',
    rows=('map059/ev029/p0/b0',),
    approach_prefer='north',
    skip_claimed=True,
)

item_ball_beats(
    ch09,
    chapter_id='CH09',
    beat_prefix='m059e033_item_ball',
    group='m059e033_item_ball',
    approach_prefer='west',
    event_id=33,
    item='ITEM_REPEL',
    map_constant='MAP_ROUTE_03',
    map_id=59,
    negative_beat=True,
)

generic_beat(
    ch09,
    chapter_id='CH09',
    beat_name='m059e033_item_ball_arms',
    group='m059e033_item_ball',
    rows=('map059/ev033/p0/b0',),
    approach_prefer='west',
    skip_claimed=True,
)

trainer_beats(
    ch09,
    chapter_id='CH09',
    beat_prefix='m059e018_trainer',
    group='m059e018_trainer',
    approach_prefer='west',
    defeat_flag='TRAINER_FLAGS_START + TRAINER_CHAN_27',
    double=False,
    event_id=18,
    map_constant='MAP_ROUTE_03',
    map_id=59,
    phone=False,
    retalk_pages=1,
    rider=False,
    trainer_const='TRAINER_CHAN_27',
    trigger='event_touch',
)

generic_beat(
    ch09,
    chapter_id='CH09',
    beat_name='m059e018_trainer_arms',
    group='m059e018_trainer',
    rows=('map059/ev018/p0/b0',),
    approach_prefer='west',
    skip_claimed=True,
)

trainer_beats(
    ch09,
    chapter_id='CH09',
    beat_prefix='m059e032_trainer',
    group='m059e032_trainer',
    approach_prefer='west',
    defeat_flag='TRAINER_FLAGS_START + TRAINER_SOPHY_42',
    double=False,
    event_id=32,
    map_constant='MAP_ROUTE_03',
    map_id=59,
    phone=False,
    retalk_pages=1,
    rider=False,
    trainer_const='TRAINER_SOPHY_42',
    trigger='event_touch',
)

generic_beat(
    ch09,
    chapter_id='CH09',
    beat_name='m059e032_trainer_arms',
    group='m059e032_trainer',
    rows=('map059/ev032/p0/b0',),
    approach_prefer='west',
    skip_claimed=True,
)

generic_beat(
    ch09,
    chapter_id='CH09',
    beat_name='m059e007p0',
    group='m059e007p0',
    rows=('map059/ev007/p0', 'map059/ev007/p0/b0'),
    approach_prefer='south',
)

generic_beat(
    ch09,
    chapter_id='CH09',
    beat_name='m059e007p1',
    group='m059e007p1',
    rows=('map059/ev007/p1',),
    approach_prefer='south',
)

generic_beat(
    ch09,
    chapter_id='CH09',
    beat_name='m059e006p0',
    group='m059e006p0',
    rows=('map059/ev006/p0', 'map059/ev006/p0/b0'),
    approach_prefer='south',
)

generic_beat(
    ch09,
    chapter_id='CH09',
    beat_name='m059e006p1',
    group='m059e006p1',
    rows=('map059/ev006/p1',),
    approach_prefer='south',
)

generic_beat(
    ch09,
    chapter_id='CH09',
    beat_name='m059e005p0',
    group='m059e005p0',
    rows=('map059/ev005/p0', 'map059/ev005/p0/b0'),
    approach_prefer='south',
)

generic_beat(
    ch09,
    chapter_id='CH09',
    beat_name='m059e005p1',
    group='m059e005p1',
    rows=('map059/ev005/p1',),
    approach_prefer='south',
)

item_ball_beats(
    ch09,
    chapter_id='CH09',
    beat_prefix='m059e014_item_ball',
    group='m059e014_item_ball',
    approach_prefer='north',
    event_id=14,
    item='ITEM_WATER_STONE',
    map_constant='MAP_ROUTE_03',
    map_id=59,
    negative_beat=True,
)

generic_beat(
    ch09,
    chapter_id='CH09',
    beat_name='m059e014_item_ball_arms',
    group='m059e014_item_ball',
    rows=('map059/ev014/p0/b0',),
    approach_prefer='north',
    skip_claimed=True,
)

item_ball_beats(
    ch09,
    chapter_id='CH09',
    beat_prefix='m059e019_item_ball',
    group='m059e019_item_ball',
    approach_prefer='east',
    event_id=19,
    item='ITEM_STARDUST',
    map_constant='MAP_ROUTE_03',
    map_id=59,
    negative_beat=True,
)

generic_beat(
    ch09,
    chapter_id='CH09',
    beat_name='m059e019_item_ball_arms',
    group='m059e019_item_ball',
    rows=('map059/ev019/p0/b0',),
    approach_prefer='east',
    skip_claimed=True,
)

transit_beat(
    ch09,
    chapter_id='CH09',
    beat_name='m001e001_warp_transit',
    group='m001e001_warp',
    hops=(('MAP_ROUTE_03', 87, 9, 'UP', 'MAP_ROUTE_03_GATEHOUSE'),),
)

warp_beat(
    ch09,
    chapter_id='CH09',
    beat_name='m001e001_warp',
    group='m001e001_warp',
    dest_map_constant='MAP_ROUTE_03',
    direction='DOWN',
    end_side='origin',
    event_id=1,
    map_constant='MAP_ROUTE_03_GATEHOUSE',
    map_id=1,
    mechanism='threshold',
    return_direction='UP',
    start_side='origin',
)

flavour_npc_beat(
    ch09,
    chapter_id='CH09',
    beat_name='m001e004_flavour_npc',
    group='m001e004_flavour_npc',
    approach_prefer='south',
    event_id=4,
    map_constant='MAP_ROUTE_03_GATEHOUSE',
    map_id=1,
    variant='plain',
)

flavour_npc_beat(
    ch09,
    chapter_id='CH09',
    beat_name='m001e003_flavour_npc',
    group='m001e003_flavour_npc',
    approach_prefer='north',
    event_id=3,
    map_constant='MAP_ROUTE_03_GATEHOUSE',
    map_id=1,
    variant='plain',
)

warp_beat(
    ch09,
    chapter_id='CH09',
    beat_name='m001e006_warp',
    group='m001e006_warp',
    dest_map_constant='MAP_ROUTE_03',
    direction='DOWN',
    end_side='dest',
    event_id=6,
    map_constant='MAP_ROUTE_03_GATEHOUSE',
    map_id=1,
    mechanism='threshold',
    start_side='origin',
)

transit_beat(
    ch09,
    chapter_id='CH09',
    beat_name='m059e010_arrival_nudge_transit',
    group='m059e010_arrival_nudge',
    hops=(('MAP_ROUTE_03', 87, 9, 'UP', 'MAP_ROUTE_03_GATEHOUSE'), ('MAP_ROUTE_03_GATEHOUSE', 5, 11, 'DOWN', 'MAP_ROUTE_03')),
)

arrival_nudge_beat(
    ch09,
    chapter_id='CH09',
    beat_name='m059e010_arrival_nudge',
    group='m059e010_arrival_nudge',
    event_id=10,
    from_event_id=1,
    from_map_constant='MAP_ROUTE_03_GATEHOUSE',
    map_constant='MAP_ROUTE_03',
    map_id=59,
)

generic_beat(
    ch09,
    chapter_id='CH09',
    beat_name='m059e010_arrival_nudge_arms',
    group='m059e010_arrival_nudge',
    rows=('map059/ev010/p1/b0',),
    skip_claimed=True,
)

transit_beat(
    ch09,
    chapter_id='CH09',
    beat_name='m059e020_arrival_nudge_transit',
    group='m059e020_arrival_nudge',
    hops=(('MAP_ROUTE_03', 87, 9, 'UP', 'MAP_ROUTE_03_GATEHOUSE'), ('MAP_ROUTE_03_GATEHOUSE', 6, 11, 'DOWN', 'MAP_ROUTE_03')),
)

arrival_nudge_beat(
    ch09,
    chapter_id='CH09',
    beat_name='m059e020_arrival_nudge',
    group='m059e020_arrival_nudge',
    event_id=20,
    from_event_id=6,
    from_map_constant='MAP_ROUTE_03_GATEHOUSE',
    map_constant='MAP_ROUTE_03',
    map_id=59,
)

generic_beat(
    ch09,
    chapter_id='CH09',
    beat_name='m059e020_arrival_nudge_arms',
    group='m059e020_arrival_nudge',
    rows=('map059/ev020/p1/b0',),
    skip_claimed=True,
)

warp_beat(
    ch09,
    chapter_id='CH09',
    beat_name='m059e020_warp',
    group='m059e020_warp',
    dest_map_constant='MAP_ROUTE_03_GATEHOUSE',
    direction='UP',
    end_side='origin',
    event_id=20,
    map_constant='MAP_ROUTE_03',
    map_id=59,
    mechanism='threshold',
    return_direction='DOWN',
    start_side='origin',
)

warp_beat(
    ch09,
    chapter_id='CH09',
    beat_name='m059e010_warp',
    group='m059e010_warp',
    dest_map_constant='MAP_ROUTE_03_GATEHOUSE',
    direction='UP',
    end_side='dest',
    event_id=10,
    map_constant='MAP_ROUTE_03',
    map_id=59,
    mechanism='threshold',
    start_side='origin',
)

warp_beat(
    ch09,
    chapter_id='CH09',
    beat_name='m001e002_warp',
    group='m001e002_warp',
    boundary=True,
    dest_map_constant='MAP_BUROLE_TOWN_60',
    direction='UP',
    event_id=2,
    map_constant='MAP_ROUTE_03_GATEHOUSE',
    map_id=1,
    mechanism='threshold',
)

warp_beat(
    ch09,
    chapter_id='CH09',
    beat_name='m001e005_warp',
    group='m001e002_warp',
    boundary=True,
    dest_map_constant='MAP_BUROLE_TOWN_60',
    direction='UP',
    event_id=5,
    map_constant='MAP_ROUTE_03_GATEHOUSE',
    map_id=1,
    mechanism='threshold',
)

NEVER_FIRES: dict[str, str] = {}

EMPTY_PAGES: dict[str, str] = {}

WALK_CHECKED: dict[str, str] = {}

ELSEWHERE: dict[str, str] = {
    'map001/ev002/p1': "later: CH10: its event crosses out of the chapter's map chain (to map(s) [60]); the rest of the event belongs to the chapter that builds the far side",
    'map001/ev002/p1/b0': "later: CH10: its event crosses out of the chapter's map chain (to map(s) [60]); the rest of the event belongs to the chapter that builds the far side",
    'map001/ev002/p1/b1': "later: CH10: its event crosses out of the chapter's map chain (to map(s) [60]); the rest of the event belongs to the chapter that builds the far side",
    'map001/ev005/p1': "later: CH10: its event crosses out of the chapter's map chain (to map(s) [60]); the rest of the event belongs to the chapter that builds the far side",
    'map001/ev005/p1/b0': "later: CH10: its event crosses out of the chapter's map chain (to map(s) [60]); the rest of the event belongs to the chapter that builds the far side",
    'map001/ev005/p1/b1': "later: CH10: its event crosses out of the chapter's map chain (to map(s) [60]); the rest of the event belongs to the chapter that builds the far side",
    'map054/ev001/p0/b1': 'unselected_arm: blocked by harness:full_bag; the walk takes the sibling arm (ruling 19)',
    'map059/ev001/p0': 'stripped: strip_list.json map_events (Luz)',
    'map059/ev002/p0': 'stripped: strip_list.json map_events (Luz)',
    'map059/ev003/p0': 'stripped: strip_list.json map_events (Luz)',
    'map059/ev005/p0/b1': 'unselected_arm: not taken on the walk: else of `pbPickBerry(PBItems::ORANBERRY,2)` from cell (74, 20) (event at (74, 19)) (ruling 19)',
    'map059/ev006/p0/b1': 'unselected_arm: not taken on the walk: else of `pbPickBerry(PBItems::RAWSTBERRY,2)` from cell (75, 20) (event at (75, 19)) (ruling 19)',
    'map059/ev007/p0/b1': 'unselected_arm: not taken on the walk: else of `pbPickBerry(PBItems::CHERIBERRY,2)` from cell (76, 20) (event at (76, 19)) (ruling 19)',
    'map059/ev009/p0/b1': 'unselected_arm: blocked by fork:whiteout; the walk takes the sibling arm (ruling 19)',
    'map059/ev009/p1': 'unreachable',
    'map059/ev010/p1/b1': 'unselected_arm: not taken on the walk: else of `get_character(0).onEvent?` from cell (87, 8) (event at (87, 8)) (ruling 19)',
    'map059/ev012/p0/b1': 'unselected_arm: blocked by fork:whiteout; the walk takes the sibling arm (ruling 19)',
    'map059/ev013/p0/b1': 'unselected_arm: blocked by harness:full_bag; the walk takes the sibling arm (ruling 19)',
    'map059/ev014/p0/b1': 'unselected_arm: blocked by harness:full_bag; the walk takes the sibling arm (ruling 19)',
    'map059/ev018/p0/b1': 'unselected_arm: blocked by fork:whiteout; the walk takes the sibling arm (ruling 19)',
    'map059/ev019/p0/b1': 'unselected_arm: blocked by harness:full_bag; the walk takes the sibling arm (ruling 19)',
    'map059/ev020/p1/b1': 'unselected_arm: not taken on the walk: else of `get_character(0).onEvent?` from cell (88, 8) (event at (88, 8)) (ruling 19)',
    'map059/ev023/p1/b1': 'unselected_arm: not taken on the walk: else of `get_character(0).onEvent?` from cell (31, 26) (event at (31, 26)) (ruling 19)',
    'map059/ev027/p0/b1': 'unselected_arm: blocked by fork:whiteout; the walk takes the sibling arm (ruling 19)',
    'map059/ev029/p0/b1': 'unselected_arm: blocked by fork:whiteout; the walk takes the sibling arm (ruling 19)',
    'map059/ev031/p0/b1': 'unselected_arm: blocked by fork:whiteout; the walk takes the sibling arm (ruling 19)',
    'map059/ev032/p0/b1': 'unselected_arm: blocked by fork:whiteout; the walk takes the sibling arm (ruling 19)',
    'map059/ev033/p0/b1': 'unselected_arm: blocked by harness:full_bag; the walk takes the sibling arm (ruling 19)',
    'map059/ev034/p0/b1': 'unselected_arm: blocked by harness:full_bag; the walk takes the sibling arm (ruling 19)',
    'map059/ev037/p0/b1': 'unselected_arm: blocked by harness:full_bag; the walk takes the sibling arm (ruling 19)',
    'map059/ev050/p0/b1': 'unselected_arm: blocked by fork:whiteout; the walk takes the sibling arm (ruling 19)',
    'map059/ev051/p0/b1': 'unselected_arm: blocked by harness:full_bag; the walk takes the sibling arm (ruling 19)',
}

REFUSED: dict[str, str] = {
    'map059/ev009/p1/b0': 'story-state: unmodelled_outcome:phone_battle_count(trainer)',
    'map059/ev009/p1/b1': 'story-state: unmodelled_outcome:phone_battle_count(trainer)',
    'map059/ev009/p1/b2': 'story-state: unmodelled_outcome:phone_battle_count(trainer)',
    'map059/ev009/p1/b3': 'story-state: unmodelled_outcome:phone_battle_count(trainer)',
    'map059/ev009/p2/b0': 'story-state: unmodelled_outcome:phone_battle_count(trainer)',
    'map059/ev009/p2/b1': 'story-state: unmodelled_outcome:phone_battle_count(trainer)',
}

CHAPTER = ch09.build()
