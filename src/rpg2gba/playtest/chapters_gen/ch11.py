"""GENERATED -- do not edit.

Chapter CH11. Regenerate with `python -m rpg2gba.beat_gen generate --chapter CH11`.
"""

from __future__ import annotations

from rpg2gba.playtest.archetypes.arrival_nudge import arrival_nudge_beat
from rpg2gba.playtest.archetypes.flavour_npc import flavour_npc_beat
from rpg2gba.playtest.archetypes.generic import generic_beat, stair_beat, transit_beat
from rpg2gba.playtest.archetypes.item_ball import item_ball_beats
from rpg2gba.playtest.archetypes.trainer import trainer_beats
from rpg2gba.playtest.archetypes.warp import warp_beat
from rpg2gba.playtest.chapter import ChapterBuilder

ch11 = ChapterBuilder('CH11', doc='beat_gen-generated module for CH11', predecessor='CH10', suite='gen')

warp_beat(
    ch11,
    chapter_id='CH11',
    beat_name='m060e032_warp',
    group='m060e032_warp',
    dest_map_constant='MAP_ROUTE_04_GATEHOUSE',
    direction='RIGHT',
    end_side='dest',
    event_id=32,
    manifest_chapter_id='CH10',
    map_constant='MAP_BUROLE_TOWN',
    map_id=60,
    mechanism='threshold',
    start_side='origin',
)

warp_beat(
    ch11,
    chapter_id='CH11',
    beat_name='m009e001_warp',
    group='m009e001_warp',
    dest_map_constant='MAP_BUROLE_TOWN',
    direction='LEFT',
    end_side='dest',
    event_id=1,
    map_constant='MAP_ROUTE_04_GATEHOUSE',
    map_id=9,
    mechanism='threshold',
    start_side='origin',
)

arrival_nudge_beat(
    ch11,
    chapter_id='CH11',
    beat_name='m060e032_arrival_nudge',
    group='m060e032_arrival_nudge',
    event_id=32,
    from_event_id=1,
    from_map_constant='MAP_ROUTE_04_GATEHOUSE',
    manifest_chapter_id='CH10',
    map_constant='MAP_BUROLE_TOWN',
    map_id=60,
)

generic_beat(
    ch11,
    chapter_id='CH11',
    beat_name='m060e032_arrival_nudge_arms',
    group='m060e032_arrival_nudge',
    rows=('map060/ev032/p1/b0',),
    manifest_chapter_id='CH10',
    skip_claimed=True,
)

transit_beat(
    ch11,
    chapter_id='CH11',
    beat_name='m009e002_warp_transit',
    group='m009e002_warp',
    hops=(('MAP_BUROLE_TOWN', 69, 22, 'RIGHT', 'MAP_ROUTE_04_GATEHOUSE'),),
)

warp_beat(
    ch11,
    chapter_id='CH11',
    beat_name='m009e002_warp',
    group='m009e002_warp',
    dest_map_constant='MAP_ROUTE_04',
    direction='RIGHT',
    end_side='dest',
    event_id=2,
    map_constant='MAP_ROUTE_04_GATEHOUSE',
    map_id=9,
    mechanism='threshold',
    start_side='origin',
)

warp_beat(
    ch11,
    chapter_id='CH11',
    beat_name='m076e001_warp',
    group='m076e001_warp',
    dest_map_constant='MAP_ROUTE_04_GATEHOUSE',
    direction='DOWN',
    end_side='origin',
    event_id=1,
    map_constant='MAP_ROUTE_04',
    map_id=76,
    mechanism='threshold',
    return_direction='RIGHT',
    start_side='origin',
)

arrival_nudge_beat(
    ch11,
    chapter_id='CH11',
    beat_name='m076e001_arrival_nudge',
    group='m076e001_arrival_nudge',
    event_id=1,
    from_event_id=2,
    from_map_constant='MAP_ROUTE_04_GATEHOUSE',
    map_constant='MAP_ROUTE_04',
    map_id=76,
)

generic_beat(
    ch11,
    chapter_id='CH11',
    beat_name='m076e001_arrival_nudge_arms',
    group='m076e001_arrival_nudge',
    rows=('map076/ev001/p1/b0',),
    skip_claimed=True,
)

flavour_npc_beat(
    ch11,
    chapter_id='CH11',
    beat_name='m076e005_flavour_npc',
    group='m076e005_flavour_npc',
    approach_prefer='north',
    event_id=5,
    map_constant='MAP_ROUTE_04',
    map_id=76,
    variant='plain',
)

trainer_beats(
    ch11,
    chapter_id='CH11',
    beat_prefix='m076e010_trainer',
    group='m076e010_trainer',
    approach_prefer='east',
    defeat_flag='TRAINER_FLAGS_START + TRAINER_MARTA_33',
    double=False,
    event_id=10,
    map_constant='MAP_ROUTE_04',
    map_id=76,
    phone=False,
    retalk_pages=1,
    rider=False,
    trainer_const='TRAINER_MARTA_33',
    trigger='event_touch',
)

generic_beat(
    ch11,
    chapter_id='CH11',
    beat_name='m076e010_trainer_arms',
    group='m076e010_trainer',
    rows=('map076/ev010/p0/b0',),
    approach_prefer='east',
    skip_claimed=True,
)

generic_beat(
    ch11,
    chapter_id='CH11',
    beat_name='m076e038p0',
    group='m076e038p0',
    rows=('map076/ev038/p0', 'map076/ev038/p0/b0'),
    approach_prefer='north',
)

generic_beat(
    ch11,
    chapter_id='CH11',
    beat_name='m076e038p1',
    group='m076e038p1',
    rows=('map076/ev038/p1',),
    approach_prefer='north',
)

generic_beat(
    ch11,
    chapter_id='CH11',
    beat_name='m076e039p0',
    group='m076e039p0',
    rows=('map076/ev039/p0', 'map076/ev039/p0/b0'),
    approach_prefer='north',
)

generic_beat(
    ch11,
    chapter_id='CH11',
    beat_name='m076e039p1',
    group='m076e039p1',
    rows=('map076/ev039/p1',),
    approach_prefer='north',
)

generic_beat(
    ch11,
    chapter_id='CH11',
    beat_name='m076e040p0',
    group='m076e040p0',
    rows=('map076/ev040/p0', 'map076/ev040/p0/b0'),
    approach_prefer='north',
)

generic_beat(
    ch11,
    chapter_id='CH11',
    beat_name='m076e040p1',
    group='m076e040p1',
    rows=('map076/ev040/p1',),
    approach_prefer='north',
)

item_ball_beats(
    ch11,
    chapter_id='CH11',
    beat_prefix='m076e004_item_ball',
    group='m076e004_item_ball',
    approach_prefer='west',
    event_id=4,
    item='ITEM_ELIXIR',
    map_constant='MAP_ROUTE_04',
    map_id=76,
    negative_beat=True,
)

generic_beat(
    ch11,
    chapter_id='CH11',
    beat_name='m076e004_item_ball_arms',
    group='m076e004_item_ball',
    rows=('map076/ev004/p0/b0',),
    approach_prefer='west',
    skip_claimed=True,
)

trainer_beats(
    ch11,
    chapter_id='CH11',
    beat_prefix='m076e002_trainer',
    group='m076e002_trainer',
    approach_prefer='south',
    defeat_flag='TRAINER_FLAGS_START + TRAINER_CARLTON_34',
    double=False,
    event_id=2,
    map_constant='MAP_ROUTE_04',
    map_id=76,
    phone=False,
    retalk_pages=1,
    rider=False,
    trainer_const='TRAINER_CARLTON_34',
    trigger='event_touch',
)

generic_beat(
    ch11,
    chapter_id='CH11',
    beat_name='m076e002_trainer_arms',
    group='m076e002_trainer',
    rows=('map076/ev002/p0/b0',),
    approach_prefer='south',
    skip_claimed=True,
)

item_ball_beats(
    ch11,
    chapter_id='CH11',
    beat_prefix='m076e052_item_ball',
    group='m076e052_item_ball',
    approach_prefer='south',
    event_id=52,
    item='ITEM_SUPER_POTION',
    map_constant='MAP_ROUTE_04',
    map_id=76,
    negative_beat=True,
)

generic_beat(
    ch11,
    chapter_id='CH11',
    beat_name='m076e052_item_ball_arms',
    group='m076e052_item_ball',
    rows=('map076/ev052/p0/b0',),
    approach_prefer='south',
    skip_claimed=True,
)

flavour_npc_beat(
    ch11,
    chapter_id='CH11',
    beat_name='m076e013_flavour_npc',
    group='m076e013_flavour_npc',
    approach_prefer='north',
    event_id=13,
    map_constant='MAP_ROUTE_04',
    map_id=76,
    variant='plain',
)

trainer_beats(
    ch11,
    chapter_id='CH11',
    beat_prefix='m076e058_trainer',
    group='m076e058_trainer',
    approach_prefer='north',
    defeat_flag='TRAINER_FLAGS_START + TRAINER_NELSON_40',
    double=False,
    event_id=58,
    map_constant='MAP_ROUTE_04',
    map_id=76,
    phone=False,
    retalk_pages=1,
    rider=False,
    trainer_const='TRAINER_NELSON_40',
    trigger='event_touch',
)

generic_beat(
    ch11,
    chapter_id='CH11',
    beat_name='m076e058_trainer_arms',
    group='m076e058_trainer',
    rows=('map076/ev058/p0/b0',),
    approach_prefer='north',
    skip_claimed=True,
)

item_ball_beats(
    ch11,
    chapter_id='CH11',
    beat_prefix='m076e077_item_ball',
    group='m076e077_item_ball',
    approach_prefer='north',
    event_id=77,
    item='ITEM_TM10',
    map_constant='MAP_ROUTE_04',
    map_id=76,
    negative_beat=True,
)

generic_beat(
    ch11,
    chapter_id='CH11',
    beat_name='m076e077_item_ball_arms',
    group='m076e077_item_ball',
    rows=('map076/ev077/p0/b0',),
    approach_prefer='north',
    skip_claimed=True,
)

generic_beat(
    ch11,
    chapter_id='CH11',
    beat_name='m076e071p0',
    group='m076e071p0',
    rows=('map076/ev071/p0', 'map076/ev071/p0/b0'),
    approach_prefer='south',
)

generic_beat(
    ch11,
    chapter_id='CH11',
    beat_name='m076e071p2',
    group='m076e071p2',
    rows=('map076/ev071/p2',),
    approach_prefer='south',
)

item_ball_beats(
    ch11,
    chapter_id='CH11',
    beat_prefix='m076e080_item_ball',
    group='m076e080_item_ball',
    approach_prefer='west',
    event_id=80,
    item='ITEM_NUGGET',
    map_constant='MAP_ROUTE_04',
    map_id=76,
    negative_beat=True,
)

generic_beat(
    ch11,
    chapter_id='CH11',
    beat_name='m076e080_item_ball_arms',
    group='m076e080_item_ball',
    rows=('map076/ev080/p0/b0',),
    approach_prefer='west',
    skip_claimed=True,
)

item_ball_beats(
    ch11,
    chapter_id='CH11',
    beat_prefix='m076e022_item_ball',
    group='m076e022_item_ball',
    approach_prefer='north',
    event_id=22,
    item='ITEM_ETHER',
    map_constant='MAP_ROUTE_04',
    map_id=76,
    negative_beat=True,
)

generic_beat(
    ch11,
    chapter_id='CH11',
    beat_name='m076e022_item_ball_arms',
    group='m076e022_item_ball',
    rows=('map076/ev022/p0/b0',),
    approach_prefer='north',
    skip_claimed=True,
)

trainer_beats(
    ch11,
    chapter_id='CH11',
    beat_prefix='m076e043_trainer',
    group='m076e043_trainer',
    approach_prefer='north',
    defeat_flag='TRAINER_FLAGS_START + TRAINER_OGILVY_253',
    double=False,
    event_id=43,
    map_constant='MAP_ROUTE_04',
    map_id=76,
    phone=False,
    retalk_pages=1,
    rider=False,
    trainer_const='TRAINER_OGILVY_253',
    trigger='event_touch',
)

generic_beat(
    ch11,
    chapter_id='CH11',
    beat_name='m076e043_trainer_arms',
    group='m076e043_trainer',
    rows=('map076/ev043/p0/b0',),
    approach_prefer='north',
    skip_claimed=True,
)

trainer_beats(
    ch11,
    chapter_id='CH11',
    beat_prefix='m076e044_trainer',
    group='m076e044_trainer',
    approach_prefer='south',
    defeat_flag='TRAINER_FLAGS_START + TRAINER_LARAMIE_254',
    double=False,
    event_id=44,
    map_constant='MAP_ROUTE_04',
    map_id=76,
    phone=False,
    retalk_pages=1,
    rider=False,
    trainer_const='TRAINER_LARAMIE_254',
    trigger='event_touch',
)

generic_beat(
    ch11,
    chapter_id='CH11',
    beat_name='m076e044_trainer_arms',
    group='m076e044_trainer',
    rows=('map076/ev044/p0/b0',),
    approach_prefer='south',
    skip_claimed=True,
)

item_ball_beats(
    ch11,
    chapter_id='CH11',
    beat_prefix='m076e078_item_ball',
    group='m076e078_item_ball',
    approach_prefer='north',
    event_id=78,
    item='ITEM_THUNDERSTONE',
    map_constant='MAP_ROUTE_04',
    map_id=76,
    negative_beat=True,
)

generic_beat(
    ch11,
    chapter_id='CH11',
    beat_name='m076e078_item_ball_arms',
    group='m076e078_item_ball',
    rows=('map076/ev078/p0/b0',),
    approach_prefer='north',
    skip_claimed=True,
)

flavour_npc_beat(
    ch11,
    chapter_id='CH11',
    beat_name='m076e011p0_flavour_npc',
    group='m076e011p0_flavour_npc',
    approach_prefer='south',
    event_id=11,
    map_constant='MAP_ROUTE_04',
    map_id=76,
    variant='plain',
)

stair_beat(
    ch11,
    chapter_id='CH11',
    beat_name='m076stair23x32',
    group='m076stair23x32',
    rows=('map076/terrain/stairs/23,32', 'map076/terrain/stairs/23,33', 'map076/terrain/stairs/24,30', 'map076/terrain/stairs/24,31'),
    approach_prefer='east',
)

generic_beat(
    ch11,
    chapter_id='CH11',
    beat_name='m076e003p0',
    group='m076e003p0',
    rows=('map076/ev003/p0',),
    approach_prefer='south',
)

trainer_beats(
    ch11,
    chapter_id='CH11',
    beat_prefix='m076e059_trainer',
    group='m076e059_trainer',
    approach_prefer='west',
    defeat_flag='TRAINER_FLAGS_START + TRAINER_WILLIAM_35',
    double=False,
    event_id=59,
    map_constant='MAP_ROUTE_04',
    map_id=76,
    phone=False,
    retalk_pages=1,
    rider=False,
    trainer_const='TRAINER_WILLIAM_35',
    trigger='event_touch',
)

generic_beat(
    ch11,
    chapter_id='CH11',
    beat_name='m076e059_trainer_arms',
    group='m076e059_trainer',
    rows=('map076/ev059/p0/b0',),
    approach_prefer='west',
    skip_claimed=True,
)

item_ball_beats(
    ch11,
    chapter_id='CH11',
    beat_prefix='m076e082_item_ball',
    group='m076e082_item_ball',
    approach_prefer='east',
    event_id=82,
    item='ITEM_DUSK_BALL',
    map_constant='MAP_ROUTE_04',
    map_id=76,
    negative_beat=True,
)

generic_beat(
    ch11,
    chapter_id='CH11',
    beat_name='m076e082_item_ball_arms',
    group='m076e082_item_ball',
    rows=('map076/ev082/p0/b0',),
    approach_prefer='east',
    skip_claimed=True,
)

item_ball_beats(
    ch11,
    chapter_id='CH11',
    beat_prefix='m076e079_item_ball',
    group='m076e079_item_ball',
    approach_prefer='south',
    event_id=79,
    item='ITEM_TM08',
    map_constant='MAP_ROUTE_04',
    map_id=76,
    negative_beat=True,
)

generic_beat(
    ch11,
    chapter_id='CH11',
    beat_name='m076e079_item_ball_arms',
    group='m076e079_item_ball',
    rows=('map076/ev079/p0/b0',),
    approach_prefer='south',
    skip_claimed=True,
)

item_ball_beats(
    ch11,
    chapter_id='CH11',
    beat_prefix='m076e081_item_ball',
    group='m076e081_item_ball',
    approach_prefer='east',
    event_id=81,
    item='ITEM_ETHER',
    map_constant='MAP_ROUTE_04',
    map_id=76,
    negative_beat=True,
)

generic_beat(
    ch11,
    chapter_id='CH11',
    beat_name='m076e081_item_ball_arms',
    group='m076e081_item_ball',
    rows=('map076/ev081/p0/b0',),
    approach_prefer='east',
    skip_claimed=True,
)

item_ball_beats(
    ch11,
    chapter_id='CH11',
    beat_prefix='m076e084_item_ball',
    group='m076e084_item_ball',
    approach_prefer='north',
    event_id=84,
    item='ITEM_BIKE_WHEEL',
    map_constant='MAP_ROUTE_04',
    map_id=76,
    negative_beat=True,
)

generic_beat(
    ch11,
    chapter_id='CH11',
    beat_name='m076e084_item_ball_arms',
    group='m076e084_item_ball',
    rows=('map076/ev084/p0/b0',),
    approach_prefer='north',
    skip_claimed=True,
)

generic_beat(
    ch11,
    chapter_id='CH11',
    beat_name='m076e049p0',
    group='m076e049p0',
    rows=('map076/ev049/p0',),
    approach_prefer='west',
)

flavour_npc_beat(
    ch11,
    chapter_id='CH11',
    beat_name='m076e019_flavour_npc',
    group='m076e019_flavour_npc',
    approach_prefer='east',
    event_id=19,
    map_constant='MAP_ROUTE_04',
    map_id=76,
    moved_by=('map076/ev023/p0', 'map076/ev034/p0', 'map076/ev035/p0'),
    variant='plain',
)

warp_beat(
    ch11,
    chapter_id='CH11',
    beat_name='m076e023_warp',
    group='m076e023_warp',
    boundary=True,
    dest_map_constant='MAP_COMET_CAVE',
    direction='DOWN',
    event_id=23,
    map_constant='MAP_ROUTE_04',
    map_id=76,
    mechanism='threshold',
)

warp_beat(
    ch11,
    chapter_id='CH11',
    beat_name='m076e034_warp',
    group='m076e023_warp',
    boundary=True,
    dest_map_constant='MAP_COMET_CAVE',
    direction='DOWN',
    event_id=34,
    map_constant='MAP_ROUTE_04',
    map_id=76,
    mechanism='threshold',
)

warp_beat(
    ch11,
    chapter_id='CH11',
    beat_name='m076e035_warp',
    group='m076e023_warp',
    boundary=True,
    dest_map_constant='MAP_COMET_CAVE',
    direction='DOWN',
    event_id=35,
    map_constant='MAP_ROUTE_04',
    map_id=76,
    mechanism='threshold',
)

NEVER_FIRES: dict[str, str] = {
    'map076/ev019/p1': "map076/ev019/p1 (needs var 106 >= 1) is not its event's live page at this route position: var 106 >= 1 fails: var 106 is [0] (seed state), never written on the route; the rows that could write it none are not walked before it; live page: map076/ev019/p0 (needs no condition)",
}

EMPTY_PAGES: dict[str, str] = {
    'map076/ev020/p0': 'every page of the event is empty; nothing to check on the ROM',
    'map076/ev020/p1': 'every page of the event is empty; nothing to check on the ROM',
    'map076/ev050/p0': 'every page of the event is empty; nothing to check on the ROM',
    'map076/ev051/p0': 'every page of the event is empty; nothing to check on the ROM',
    'map076/ev072/p0': 'every page of the event is empty; nothing to check on the ROM',
    'map076/ev072/p1': 'every page of the event is empty; nothing to check on the ROM',
    'map076/ev092/p0': 'every page of the event is empty; nothing to check on the ROM',
    'map076/ev093/p0': 'every page of the event is empty; nothing to check on the ROM',
}

WALK_CHECKED: dict[str, str] = {}

ELSEWHERE: dict[str, str] = {
    'map060/ev032/p1/b1': 'unselected_arm: not taken on the walk: else of `get_character(0).onEvent?` from cell (70, 22) (event at (70, 22)) (ruling 19)',
    'map076/ev001/p1/b1': 'unselected_arm: not taken on the walk: else of `get_character(0).onEvent?` from cell (18, 102) (event at (18, 102)) (ruling 19)',
    'map076/ev002/p0/b1': 'unselected_arm: blocked by fork:whiteout; the walk takes the sibling arm (ruling 19)',
    'map076/ev004/p0/b1': 'unselected_arm: blocked by harness:full_bag; the walk takes the sibling arm (ruling 19)',
    'map076/ev010/p0/b1': 'unselected_arm: blocked by fork:whiteout; the walk takes the sibling arm (ruling 19)',
    'map076/ev021/p0': 'later: CH12',
    'map076/ev021/p1': "later: CH12: its event crosses out of the chapter's map chain (to map(s) [7]); the rest of the event belongs to the chapter that builds the far side",
    'map076/ev021/p1/b0': "later: CH12: its event crosses out of the chapter's map chain (to map(s) [7]); the rest of the event belongs to the chapter that builds the far side",
    'map076/ev021/p1/b1': "later: CH12: its event crosses out of the chapter's map chain (to map(s) [7]); the rest of the event belongs to the chapter that builds the far side",
    'map076/ev022/p0/b1': 'unselected_arm: blocked by harness:full_bag; the walk takes the sibling arm (ruling 19)',
    'map076/ev023/p1': "later: CH12: its event crosses out of the chapter's map chain (to map(s) [7]); the rest of the event belongs to the chapter that builds the far side",
    'map076/ev032/p0': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer)',
    'map076/ev032/p1': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer)',
    'map076/ev032/p2': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer)',
    'map076/ev033/p0': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer)',
    'map076/ev033/p1': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer)',
    'map076/ev033/p2': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer)',
    'map076/ev034/p1': "later: CH12: its event crosses out of the chapter's map chain (to map(s) [7]); the rest of the event belongs to the chapter that builds the far side",
    'map076/ev035/p1': "later: CH12: its event crosses out of the chapter's map chain (to map(s) [7]); the rest of the event belongs to the chapter that builds the far side",
    'map076/ev038/p0/b1': 'unselected_arm: not taken on the walk: else of `pbPickBerry(PBItems::SITRUSBERRY,2)` from cell (34, 87) (event at (34, 88)) (ruling 19)',
    'map076/ev039/p0/b1': 'unselected_arm: not taken on the walk: else of `pbPickBerry(PBItems::PERSIMBERRY,2)` from cell (35, 87) (event at (35, 88)) (ruling 19)',
    'map076/ev040/p0/b1': 'unselected_arm: not taken on the walk: else of `pbPickBerry(PBItems::CHESTOBERRY,2)` from cell (36, 87) (event at (36, 88)) (ruling 19)',
    'map076/ev043/p0/b1': 'unselected_arm: blocked by fork:whiteout; the walk takes the sibling arm (ruling 19)',
    'map076/ev044/p0/b1': 'unselected_arm: blocked by fork:whiteout; the walk takes the sibling arm (ruling 19)',
    'map076/ev052/p0/b1': 'unselected_arm: blocked by harness:full_bag; the walk takes the sibling arm (ruling 19)',
    'map076/ev058/p0/b1': 'unselected_arm: blocked by fork:whiteout; the walk takes the sibling arm (ruling 19)',
    'map076/ev059/p0/b1': 'unselected_arm: blocked by fork:whiteout; the walk takes the sibling arm (ruling 19)',
    'map076/ev070/p0': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer); script: pbCallBub(2,72,3)',
    'map076/ev070/p1': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer); script: pbCallBub(2,72,3)',
    'map076/ev071/p0/b1': 'unselected_arm: blocked by fork:whiteout; the walk takes the sibling arm (ruling 19)',
    'map076/ev077/p0/b1': 'unselected_arm: blocked by harness:full_bag; the walk takes the sibling arm (ruling 19)',
    'map076/ev078/p0/b1': 'unselected_arm: blocked by harness:full_bag; the walk takes the sibling arm (ruling 19)',
    'map076/ev079/p0/b1': 'unselected_arm: blocked by harness:full_bag; the walk takes the sibling arm (ruling 19)',
    'map076/ev080/p0/b1': 'unselected_arm: blocked by harness:full_bag; the walk takes the sibling arm (ruling 19)',
    'map076/ev081/p0/b1': 'unselected_arm: blocked by harness:full_bag; the walk takes the sibling arm (ruling 19)',
    'map076/ev082/p0/b1': 'unselected_arm: blocked by harness:full_bag; the walk takes the sibling arm (ruling 19)',
    'map076/ev084/p0/b1': 'unselected_arm: blocked by harness:full_bag; the walk takes the sibling arm (ruling 19)',
    'map076/seam/N/map142': 'later',
}

REFUSED: dict[str, str] = {
    'map076/ev007/p0': "story-state: unclassified_condition -- no family matches: 'pbPushThisBoulder'",
    'map076/ev007/p0/b0': 'story-state: unclassified_condition',
    'map076/ev007/p0/b1': 'story-state: unclassified_condition',
    'map076/ev007/p1': 'story-state: undetermined -- story model could not determine this row',
    'map076/ev007/p1/b0': 'story-state: unclassified_condition',
    'map076/ev007/p1/b1': 'story-state: unclassified_condition',
    'map076/ev011/p1': 'story-state: undetermined -- story model could not determine this row',
    'map076/ev011/p2': 'story-state: undetermined -- story model could not determine this row',
    'map076/ev071/p1': 'story-state: undetermined -- story model could not determine this row',
    'map076/ev071/p1/b0': 'story-state: unmodelled_outcome:phone_battle_count(trainer)',
    'map076/ev071/p1/b1': 'story-state: unmodelled_outcome:phone_battle_count(trainer)',
    'map076/ev071/p1/b2': 'story-state: unmodelled_outcome:phone_battle_count(trainer)',
    'map076/ev071/p1/b3': 'story-state: unmodelled_outcome:phone_battle_count(trainer)',
    'map076/ev071/p2/b0': 'story-state: unmodelled_outcome:phone_battle_count(trainer)',
    'map076/ev071/p2/b1': 'story-state: unmodelled_outcome:phone_battle_count(trainer)',
    'map076/ev076/p0': "cell: cell_error -- approach_to: MAP_ROUTE_04 event 76 (cell (27, 79)) has no walkable adjacent cell on any side -- this event cannot be approached at all under the offline graph's collision data",
}

CHAPTER = ch11.build()
