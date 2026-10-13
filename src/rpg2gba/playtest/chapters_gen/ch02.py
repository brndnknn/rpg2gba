"""GENERATED -- do not edit.

Chapter CH02. Regenerate with `python -m rpg2gba.beat_gen generate --chapter CH02`.
"""

from __future__ import annotations

from rpg2gba.playtest.archetypes.arrival_nudge import arrival_nudge_beat
from rpg2gba.playtest.archetypes.flavour_npc import flavour_npc_beat
from rpg2gba.playtest.archetypes.generic import generic_beat, obstacle_beat, stair_beat, transit_beat
from rpg2gba.playtest.archetypes.item_ball import item_ball_beats
from rpg2gba.playtest.archetypes.trainer import trainer_beats
from rpg2gba.playtest.archetypes.warp import warp_beat
from rpg2gba.playtest.chapter import ChapterBuilder

ch02 = ChapterBuilder('CH02', doc='beat_gen-generated module for CH02', predecessor='CH01', suite='gen')

warp_beat(
    ch02,
    chapter_id='CH02',
    beat_name='m032e037_warp',
    group='m032e037_warp',
    dest_map_constant='MAP_ROUTE_01',
    direction='LEFT',
    end_side='origin',
    event_id=37,
    manifest_chapter_id='CH01',
    map_constant='MAP_MOKI_TOWN',
    map_id=32,
    mechanism='threshold',
    return_direction='RIGHT',
    start_side='origin',
)

warp_beat(
    ch02,
    chapter_id='CH02',
    beat_name='m032e023_warp',
    group='m032e023_warp',
    dest_map_constant='MAP_ROUTE_01',
    direction='LEFT',
    end_side='origin',
    event_id=23,
    manifest_chapter_id='CH01',
    map_constant='MAP_MOKI_TOWN',
    map_id=32,
    mechanism='threshold',
    return_direction='RIGHT',
    start_side='origin',
)

warp_beat(
    ch02,
    chapter_id='CH02',
    beat_name='m032e036_warp',
    group='m032e036_warp',
    dest_map_constant='MAP_ROUTE_01',
    direction='LEFT',
    end_side='dest',
    event_id=36,
    manifest_chapter_id='CH01',
    map_constant='MAP_MOKI_TOWN',
    map_id=32,
    mechanism='threshold',
    start_side='origin',
)

generic_beat(
    ch02,
    chapter_id='CH02',
    beat_name='m033e004p0',
    group='m033e004p0',
    rows=('map033/ev004/p0',),
    approach_prefer='arrive@(70,11)',
)

transit_beat(
    ch02,
    chapter_id='CH02',
    beat_name='m033e023_arrival_nudge_transit',
    group='m033e023_arrival_nudge',
    hops=(('MAP_ROUTE_01', 69, 11, 'RIGHT', 'MAP_MOKI_TOWN'), ('MAP_MOKI_TOWN', 9, 44, 'LEFT', 'MAP_ROUTE_01')),
)

arrival_nudge_beat(
    ch02,
    chapter_id='CH02',
    beat_name='m033e023_arrival_nudge',
    group='m033e023_arrival_nudge',
    event_id=23,
    from_event_id=23,
    from_map_constant='MAP_MOKI_TOWN',
    map_constant='MAP_ROUTE_01',
    map_id=33,
)

generic_beat(
    ch02,
    chapter_id='CH02',
    beat_name='m033e023_arrival_nudge_arms',
    group='m033e023_arrival_nudge',
    rows=('map033/ev023/p1/b0',),
    skip_claimed=True,
)

warp_beat(
    ch02,
    chapter_id='CH02',
    beat_name='m033e023_warp',
    group='m033e023_warp',
    dest_map_constant='MAP_MOKI_TOWN',
    direction='RIGHT',
    end_side='origin',
    event_id=23,
    map_constant='MAP_ROUTE_01',
    map_id=33,
    mechanism='threshold',
    return_direction='LEFT',
    start_side='origin',
)

warp_beat(
    ch02,
    chapter_id='CH02',
    beat_name='m033e022_warp',
    group='m033e022_warp',
    dest_map_constant='MAP_MOKI_TOWN',
    direction='RIGHT',
    end_side='origin',
    event_id=22,
    map_constant='MAP_ROUTE_01',
    map_id=33,
    mechanism='threshold',
    return_direction='LEFT',
    start_side='origin',
)

warp_beat(
    ch02,
    chapter_id='CH02',
    beat_name='m033e024_warp',
    group='m033e024_warp',
    dest_map_constant='MAP_MOKI_TOWN',
    direction='RIGHT',
    end_side='dest',
    event_id=24,
    map_constant='MAP_ROUTE_01',
    map_id=33,
    mechanism='threshold',
    start_side='origin',
)

transit_beat(
    ch02,
    chapter_id='CH02',
    beat_name='m032e037_arrival_nudge_transit',
    group='m032e037_arrival_nudge',
    hops=(('MAP_MOKI_TOWN', 9, 43, 'LEFT', 'MAP_ROUTE_01'), ('MAP_ROUTE_01', 69, 12, 'RIGHT', 'MAP_MOKI_TOWN')),
)

arrival_nudge_beat(
    ch02,
    chapter_id='CH02',
    beat_name='m032e037_arrival_nudge',
    group='m032e037_arrival_nudge',
    event_id=37,
    from_event_id=22,
    from_map_constant='MAP_ROUTE_01',
    manifest_chapter_id='CH01',
    map_constant='MAP_MOKI_TOWN',
    map_id=32,
)

generic_beat(
    ch02,
    chapter_id='CH02',
    beat_name='m032e037_arrival_nudge_arms',
    group='m032e037_arrival_nudge',
    rows=('map032/ev037/p1/b0',),
    manifest_chapter_id='CH01',
    skip_claimed=True,
)

transit_beat(
    ch02,
    chapter_id='CH02',
    beat_name='m033stair57x9_transit',
    group='m033stair57x9',
    hops=(('MAP_MOKI_TOWN', 9, 43, 'LEFT', 'MAP_ROUTE_01'),),
)

stair_beat(
    ch02,
    chapter_id='CH02',
    beat_name='m033stair57x9',
    group='m033stair57x9',
    rows=('map033/terrain/stairs/57,9', 'map033/terrain/stairs/57,10', 'map033/terrain/stairs/57,11'),
    approach_prefer='east',
)

item_ball_beats(
    ch02,
    chapter_id='CH02',
    beat_prefix='m033e002_item_ball',
    group='m033e002_item_ball',
    approach_prefer='south',
    event_id=2,
    item='ITEM_POTION',
    map_constant='MAP_ROUTE_01',
    map_id=33,
    negative_beat=True,
)

generic_beat(
    ch02,
    chapter_id='CH02',
    beat_name='m033e002_item_ball_arms',
    group='m033e002_item_ball',
    rows=('map033/ev002/p0/b0',),
    approach_prefer='south',
    skip_claimed=True,
)

flavour_npc_beat(
    ch02,
    chapter_id='CH02',
    beat_name='m033e098_flavour_npc',
    group='m033e098_flavour_npc',
    approach_prefer='south',
    event_id=98,
    map_constant='MAP_ROUTE_01',
    map_id=33,
    variant='plain',
)

trainer_beats(
    ch02,
    chapter_id='CH02',
    beat_prefix='m033e034_trainer',
    group='m033e034_trainer',
    approach_prefer='south',
    defeat_flag='TRAINER_FLAGS_START + TRAINER_TATH_1',
    double=False,
    event_id=34,
    map_constant='MAP_ROUTE_01',
    map_id=33,
    phone=False,
    retalk_pages=1,
    rider=False,
    trainer_const='TRAINER_TATH_1',
    trigger='event_touch',
)

generic_beat(
    ch02,
    chapter_id='CH02',
    beat_name='m033e034_trainer_arms',
    group='m033e034_trainer',
    rows=('map033/ev034/p0/b0',),
    approach_prefer='south',
    skip_claimed=True,
)

item_ball_beats(
    ch02,
    chapter_id='CH02',
    beat_prefix='m033e050_item_ball',
    group='m033e050_item_ball',
    approach_prefer='south',
    event_id=50,
    item='ITEM_ANTIDOTE',
    map_constant='MAP_ROUTE_01',
    map_id=33,
    negative_beat=True,
)

generic_beat(
    ch02,
    chapter_id='CH02',
    beat_name='m033e050_item_ball_arms',
    group='m033e050_item_ball',
    rows=('map033/ev050/p0/b0',),
    approach_prefer='south',
    skip_claimed=True,
)

warp_beat(
    ch02,
    chapter_id='CH02',
    beat_name='m033e027_warp',
    group='m033e027_warp',
    dest_map_constant='MAP_ROUTE_01_OLD_ROD_HOUSE',
    direction='UP',
    end_side='dest',
    event_id=27,
    map_constant='MAP_ROUTE_01',
    map_id=33,
    mechanism='threshold',
    start_side='origin',
)

generic_beat(
    ch02,
    chapter_id='CH02',
    beat_name='m081e001p0',
    group='m081e001p0',
    rows=('map081/ev001/p0', 'map081/ev001/p0/b3'),
    approach_prefer='east',
)

generic_beat(
    ch02,
    chapter_id='CH02',
    beat_name='m081e002p0',
    group='m081e002p0',
    rows=('map081/ev002/p0', 'map081/ev002/p0/b0', 'map081/ev002/p0/b1'),
    approach_prefer='west',
    random_arms=(('map081/ev002/p0/b0', ((102, '==', 1),)), ('map081/ev002/p0/b1', ((102, '!=', 1),))),
)

flavour_npc_beat(
    ch02,
    chapter_id='CH02',
    beat_name='m081e004_flavour_npc',
    group='m081e004_flavour_npc',
    approach_prefer='south',
    event_id=4,
    map_constant='MAP_ROUTE_01_OLD_ROD_HOUSE',
    map_id=81,
    variant='plain',
)

warp_beat(
    ch02,
    chapter_id='CH02',
    beat_name='m081e003_warp',
    group='m081e003_warp',
    dest_map_constant='MAP_ROUTE_01',
    direction='DOWN',
    end_side='dest',
    event_id=3,
    map_constant='MAP_ROUTE_01_OLD_ROD_HOUSE',
    map_id=81,
    mechanism='threshold',
    start_side='origin',
)

arrival_nudge_beat(
    ch02,
    chapter_id='CH02',
    beat_name='m033e027_arrival_nudge',
    group='m033e027_arrival_nudge',
    event_id=27,
    from_event_id=3,
    from_map_constant='MAP_ROUTE_01_OLD_ROD_HOUSE',
    map_constant='MAP_ROUTE_01',
    map_id=33,
)

generic_beat(
    ch02,
    chapter_id='CH02',
    beat_name='m033e027_arrival_nudge_arms',
    group='m033e027_arrival_nudge',
    rows=('map033/ev027/p1/b0',),
    skip_claimed=True,
)

flavour_npc_beat(
    ch02,
    chapter_id='CH02',
    beat_name='m033e099_flavour_npc',
    group='m033e099_flavour_npc',
    approach_prefer='west',
    event_id=99,
    map_constant='MAP_ROUTE_01',
    map_id=33,
    variant='plain',
)

item_ball_beats(
    ch02,
    chapter_id='CH02',
    beat_prefix='m033e003_item_ball',
    group='m033e003_item_ball',
    approach_prefer='north',
    event_id=3,
    item='ITEM_POTION',
    map_constant='MAP_ROUTE_01',
    map_id=33,
    negative_beat=True,
)

generic_beat(
    ch02,
    chapter_id='CH02',
    beat_name='m033e003_item_ball_arms',
    group='m033e003_item_ball',
    rows=('map033/ev003/p0/b0',),
    approach_prefer='north',
    skip_claimed=True,
)

trainer_beats(
    ch02,
    chapter_id='CH02',
    beat_prefix='m033e030_trainer',
    group='m033e030_trainer',
    approach_prefer='north',
    defeat_flag='TRAINER_FLAGS_START + TRAINER_FLOOD_2',
    double=False,
    event_id=30,
    map_constant='MAP_ROUTE_01',
    map_id=33,
    phone=False,
    retalk_pages=1,
    rider=False,
    trainer_const='TRAINER_FLOOD_2',
    trigger='event_touch',
)

generic_beat(
    ch02,
    chapter_id='CH02',
    beat_name='m033e030_trainer_arms',
    group='m033e030_trainer',
    rows=('map033/ev030/p0/b0',),
    approach_prefer='north',
    skip_claimed=True,
)

generic_beat(
    ch02,
    chapter_id='CH02',
    beat_name='m033e053p0',
    group='m033e053p0',
    rows=('map033/ev053/p0', 'map033/ev053/p0/b0'),
    approach_prefer='south',
)

generic_beat(
    ch02,
    chapter_id='CH02',
    beat_name='m033e053p2',
    group='m033e053p2',
    rows=('map033/ev053/p2',),
    approach_prefer='south',
)

item_ball_beats(
    ch02,
    chapter_id='CH02',
    beat_prefix='m033e025_item_ball',
    group='m033e025_item_ball',
    approach_prefer='south',
    event_id=25,
    item='ITEM_ANTIDOTE',
    map_constant='MAP_ROUTE_01',
    map_id=33,
    negative_beat=True,
)

generic_beat(
    ch02,
    chapter_id='CH02',
    beat_name='m033e025_item_ball_arms',
    group='m033e025_item_ball',
    rows=('map033/ev025/p0/b0',),
    approach_prefer='south',
    skip_claimed=True,
)

obstacle_beat(
    ch02,
    chapter_id='CH02',
    beat_name='m033obstacle_rock_smash',
    group='m033obstacle_rock_smash',
    rows=('map033/ev036/p0', 'map033/ev038/p0'),
    approach_prefer='north',
    capability='rock_smash',
)

trainer_beats(
    ch02,
    chapter_id='CH02',
    beat_prefix='m033e103_trainer',
    group='m033e103_trainer',
    approach_prefer='east',
    defeat_flag='TRAINER_FLAGS_START + TRAINER_LYNETTE_246',
    double=False,
    event_id=103,
    map_constant='MAP_ROUTE_01',
    map_id=33,
    phone=False,
    retalk_pages=1,
    rider=False,
    trainer_const='TRAINER_LYNETTE_246',
    trigger='event_touch',
)

generic_beat(
    ch02,
    chapter_id='CH02',
    beat_name='m033e103_trainer_arms',
    group='m033e103_trainer',
    rows=('map033/ev103/p0/b0',),
    approach_prefer='east',
    skip_claimed=True,
)

generic_beat(
    ch02,
    chapter_id='CH02',
    beat_name='m033e102p0',
    group='m033e102p0',
    rows=('map033/ev102/p0', 'map033/ev102/p0/b0'),
    approach_prefer='west',
)

generic_beat(
    ch02,
    chapter_id='CH02',
    beat_name='m033e102p1',
    group='m033e102p1',
    rows=('map033/ev102/p1',),
    approach_prefer='west',
)

generic_beat(
    ch02,
    chapter_id='CH02',
    beat_name='m033e101p0',
    group='m033e101p0',
    rows=('map033/ev101/p0',),
    approach_prefer='west',
)

generic_beat(
    ch02,
    chapter_id='CH02',
    beat_name='m033e100p0',
    group='m033e100p0',
    rows=('map033/ev100/p0', 'map033/ev100/p0/b0'),
    approach_prefer='west',
)

generic_beat(
    ch02,
    chapter_id='CH02',
    beat_name='m033e100p1',
    group='m033e100p1',
    rows=('map033/ev100/p1',),
    approach_prefer='west',
)

warp_beat(
    ch02,
    chapter_id='CH02',
    beat_name='m033e045_warp',
    group='m033e045_warp',
    boundary=True,
    dest_map_constant='MAP_KEVLAR_TOWN',
    direction='UP',
    event_id=45,
    map_constant='MAP_ROUTE_01',
    map_id=33,
    mechanism='threshold',
)

warp_beat(
    ch02,
    chapter_id='CH02',
    beat_name='m033e046_warp',
    group='m033e045_warp',
    boundary=True,
    dest_map_constant='MAP_KEVLAR_TOWN',
    direction='UP',
    event_id=46,
    map_constant='MAP_ROUTE_01',
    map_id=33,
    mechanism='threshold',
)

NEVER_FIRES: dict[str, str] = {
    'map032/ev023/p1': "archetype_kwargs: map032/ev023/p1: no warp lands on this arrival autorun's cell (8,44) on map 32 -- it never fires",
    'map032/ev023/p1/b0': "archetype_kwargs: map032/ev023/p1: no warp lands on this arrival autorun's cell (8,44) on map 32 -- it never fires",
    'map032/ev023/p1/b1': "archetype_kwargs: map032/ev023/p1: no warp lands on this arrival autorun's cell (8,44) on map 32 -- it never fires",
    'map032/ev036/p1': "archetype_kwargs: map032/ev036/p1: no warp lands on this arrival autorun's cell (8,45) on map 32 -- it never fires",
    'map032/ev036/p1/b0': "archetype_kwargs: map032/ev036/p1: no warp lands on this arrival autorun's cell (8,45) on map 32 -- it never fires",
    'map032/ev036/p1/b1': "archetype_kwargs: map032/ev036/p1: no warp lands on this arrival autorun's cell (8,45) on map 32 -- it never fires",
    'map033/ev022/p1': "archetype_kwargs: map033/ev022/p1: no warp lands on this arrival autorun's cell (70,12) on map 33 -- it never fires",
    'map033/ev022/p1/b0': "archetype_kwargs: map033/ev022/p1: no warp lands on this arrival autorun's cell (70,12) on map 33 -- it never fires",
    'map033/ev022/p1/b1': "archetype_kwargs: map033/ev022/p1: no warp lands on this arrival autorun's cell (70,12) on map 33 -- it never fires",
    'map033/ev024/p1': "archetype_kwargs: map033/ev024/p1: no warp lands on this arrival autorun's cell (70,13) on map 33 -- it never fires",
    'map033/ev024/p1/b0': "archetype_kwargs: map033/ev024/p1: no warp lands on this arrival autorun's cell (70,13) on map 33 -- it never fires",
    'map033/ev024/p1/b1': "archetype_kwargs: map033/ev024/p1: no warp lands on this arrival autorun's cell (70,13) on map 33 -- it never fires",
}

EMPTY_PAGES: dict[str, str] = {
    'map033/ev013/p0': 'every page of the event is empty; nothing to check on the ROM',
    'map033/ev020/p0': 'every page of the event is empty; nothing to check on the ROM',
    'map033/ev097/p0': 'every page of the event is empty; nothing to check on the ROM',
    'map033/ev141/p0': 'every page of the event is empty; nothing to check on the ROM',
}

WALK_CHECKED: dict[str, str] = {
    'map081/ev002/p0/b0': 'arm on a rolled or computed value (var 102 == 1); the walk checks whichever fires',
    'map081/ev002/p0/b1': 'arm on a rolled or computed value (var 102 != 1); the walk checks whichever fires',
}

ELSEWHERE: dict[str, str] = {
    'map032/ev037/p1/b1': 'unselected_arm: not taken on the walk: else of `get_character(0).onEvent?` from cell (8, 43) (event at (8, 43)) (ruling 19)',
    'map033/ev002/p0/b1': 'unselected_arm: blocked by harness:full_bag; the walk takes the sibling arm (ruling 19)',
    'map033/ev003/p0/b1': 'unselected_arm: blocked by harness:full_bag; the walk takes the sibling arm (ruling 19)',
    'map033/ev023/p1/b1': 'unselected_arm: not taken on the walk: else of `get_character(0).onEvent?` from cell (70, 11) (event at (70, 11)) (ruling 19)',
    'map033/ev025/p0/b1': 'unselected_arm: blocked by harness:full_bag; the walk takes the sibling arm (ruling 19)',
    'map033/ev027/p1/b1': 'unselected_arm: not taken on the walk: else of `get_character(0).onEvent?` from cell (39, 18) (event at (39, 18)) (ruling 19)',
    'map033/ev028/p0': 'stripped: strip_list.json map_events (Luz)',
    'map033/ev029/p0': 'later',
    'map033/ev030/p0/b1': 'unselected_arm: blocked by fork:whiteout; the walk takes the sibling arm (ruling 19)',
    'map033/ev034/p0/b1': 'unselected_arm: blocked by fork:whiteout; the walk takes the sibling arm (ruling 19)',
    'map033/ev039/p1': 'unreachable',
    'map033/ev040/p0': 'later',
    'map033/ev042/p0': 'later',
    'map033/ev044/p0': 'later',
    'map033/ev045/p1': "later: CH03: its event crosses out of the chapter's map chain (to map(s) [31]); the rest of the event belongs to the chapter that builds the far side",
    'map033/ev045/p1/b0': "later: CH03: its event crosses out of the chapter's map chain (to map(s) [31]); the rest of the event belongs to the chapter that builds the far side",
    'map033/ev045/p1/b1': "later: CH03: its event crosses out of the chapter's map chain (to map(s) [31]); the rest of the event belongs to the chapter that builds the far side",
    'map033/ev046/p1': "later: CH03: its event crosses out of the chapter's map chain (to map(s) [31]); the rest of the event belongs to the chapter that builds the far side",
    'map033/ev046/p1/b0': "later: CH03: its event crosses out of the chapter's map chain (to map(s) [31]); the rest of the event belongs to the chapter that builds the far side",
    'map033/ev046/p1/b1': "later: CH03: its event crosses out of the chapter's map chain (to map(s) [31]); the rest of the event belongs to the chapter that builds the far side",
    'map033/ev050/p0/b1': 'unselected_arm: blocked by harness:full_bag; the walk takes the sibling arm (ruling 19)',
    'map033/ev053/p0/b1': 'unselected_arm: blocked by fork:whiteout; the walk takes the sibling arm (ruling 19)',
    'map033/ev053/p1': 'unreachable',
    'map033/ev100/p0/b1': 'unselected_arm: not taken on the walk: else of `pbPickBerry(PBItems::ORANBERRY,2)` from cell (61, 36) (event at (62, 36)) (ruling 19)',
    'map033/ev102/p0/b1': 'unselected_arm: not taken on the walk: else of `pbPickBerry(PBItems::ORANBERRY,2)` from cell (61, 34) (event at (62, 34)) (ruling 19)',
    'map033/ev103/p0/b1': 'unselected_arm: blocked by fork:whiteout; the walk takes the sibling arm (ruling 19)',
    'map033/ev143/p0': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer); script: $PokemonGlobal.surfing / Kernel.pbCancelVehicles',
    'map033/ev143/p0/b0': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer); script: $PokemonGlobal.surfing / Kernel.pbCancelVehicles',
    'map033/ev143/p0/b1': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer); script: $PokemonGlobal.surfing / Kernel.pbCancelVehicles',
    'map033/ev144/p0': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer); script: $PokemonGlobal.surfing / Kernel.pbCancelVehicles',
    'map033/ev144/p0/b0': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer); script: $PokemonGlobal.surfing / Kernel.pbCancelVehicles',
    'map033/ev144/p0/b1': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer); script: $PokemonGlobal.surfing / Kernel.pbCancelVehicles',
    'map033/ev145/p0': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer); script: $PokemonGlobal.surfing / Kernel.pbCancelVehicles',
    'map033/ev145/p0/b0': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer); script: $PokemonGlobal.surfing / Kernel.pbCancelVehicles',
    'map033/ev145/p0/b1': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer); script: $PokemonGlobal.surfing / Kernel.pbCancelVehicles',
    'map033/ev146/p0': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer); script: $PokemonGlobal.surfing / Kernel.pbCancelVehicles',
    'map033/ev146/p0/b0': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer); script: $PokemonGlobal.surfing / Kernel.pbCancelVehicles',
    'map033/ev146/p0/b1': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer); script: $PokemonGlobal.surfing / Kernel.pbCancelVehicles',
    'map033/ev147/p0': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer); script: $PokemonGlobal.surfing / Kernel.pbCancelVehicles',
    'map033/ev147/p0/b0': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer); script: $PokemonGlobal.surfing / Kernel.pbCancelVehicles',
    'map033/ev147/p0/b1': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer); script: $PokemonGlobal.surfing / Kernel.pbCancelVehicles',
    'map033/terrain/stairs/52,41': 'later',
    'map033/terrain/stairs/52,42': 'later',
    'map033/terrain/stairs/53,43': 'later',
    'map033/terrain/stairs/53,44': 'later',
    'map081/ev001/p0/b0': 'unreachable',
    'map081/ev001/p1': 'unreachable',
}

REFUSED: dict[str, str] = {
    'map033/ev004/p1': "cell: cell_error -- approach_to: MAP_ROUTE_01 event 4 (cell (62, 6)) has no walkable adjacent cell on any side -- this event cannot be approached at all under the offline graph's collision data",
    'map033/ev039/p1/b0': 'story-state: unmodelled_outcome:phone_battle_count(trainer)',
    'map033/ev039/p1/b1': 'story-state: unmodelled_outcome:phone_battle_count(trainer)',
    'map033/ev039/p1/b2': 'story-state: unmodelled_outcome:phone_battle_count(trainer)',
    'map033/ev039/p1/b3': 'story-state: unmodelled_outcome:phone_battle_count(trainer)',
    'map033/ev039/p2/b0': 'story-state: unmodelled_outcome:phone_battle_count(trainer)',
    'map033/ev039/p2/b1': 'story-state: unmodelled_outcome:phone_battle_count(trainer)',
    'map033/ev053/p1/b0': 'story-state: unmodelled_outcome:phone_battle_count(trainer)',
    'map033/ev053/p1/b1': 'story-state: unmodelled_outcome:phone_battle_count(trainer)',
    'map033/ev053/p1/b2': 'story-state: unmodelled_outcome:phone_battle_count(trainer)',
    'map033/ev053/p1/b3': 'story-state: unmodelled_outcome:phone_battle_count(trainer)',
    'map033/ev053/p2/b0': 'story-state: unmodelled_outcome:phone_battle_count(trainer)',
    'map033/ev053/p2/b1': 'story-state: unmodelled_outcome:phone_battle_count(trainer)',
    'map081/ev001/p0/b1': 'story-state: unmodelled_outcome:bag_contents',
    'map081/ev001/p0/b2': 'story-state: unmodelled_outcome:bag_contents',
}

CHAPTER = ch02.build()
