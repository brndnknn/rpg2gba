"""GENERATED -- do not edit.

Chapter CH10. Regenerate with `python -m rpg2gba.beat_gen generate --chapter CH10`.
"""

from __future__ import annotations

from rpg2gba.playtest.archetypes.arrival_nudge import arrival_nudge_beat
from rpg2gba.playtest.archetypes.flavour_npc import flavour_npc_beat
from rpg2gba.playtest.archetypes.generic import generic_beat, smash_beat, stair_beat, transit_beat
from rpg2gba.playtest.archetypes.trainer import trainer_beats
from rpg2gba.playtest.archetypes.warp import warp_beat
from rpg2gba.playtest.chapter import ChapterBuilder
from rpg2gba.playtest.whiteout import whiteout_fork_beat

ch10 = ChapterBuilder('CH10', doc='beat_gen-generated module for CH10', predecessor='CH09', suite='gen')

warp_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m001e005_warp',
    group='m001e005_warp',
    dest_map_constant='MAP_BUROLE_TOWN',
    direction='UP',
    end_side='origin',
    event_id=5,
    manifest_chapter_id='CH09',
    map_constant='MAP_ROUTE_03_GATEHOUSE',
    map_id=1,
    mechanism='threshold',
    return_direction='DOWN',
    start_side='origin',
)

warp_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m001e002_warp',
    group='m001e002_warp',
    dest_map_constant='MAP_BUROLE_TOWN',
    direction='UP',
    end_side='dest',
    event_id=2,
    manifest_chapter_id='CH09',
    map_constant='MAP_ROUTE_03_GATEHOUSE',
    map_id=1,
    mechanism='threshold',
    start_side='origin',
)

arrival_nudge_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m060e001_arrival_nudge',
    group='m060e001_arrival_nudge',
    event_id=1,
    from_event_id=2,
    from_map_constant='MAP_ROUTE_03_GATEHOUSE',
    map_constant='MAP_BUROLE_TOWN',
    map_id=60,
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m060e001_arrival_nudge_arms',
    group='m060e001_arrival_nudge',
    rows=('map060/ev001/p1/b0',),
    skip_claimed=True,
)

warp_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m060e001_warp',
    group='m060e001_warp',
    dest_map_constant='MAP_ROUTE_03_GATEHOUSE',
    direction='DOWN',
    end_side='origin',
    event_id=1,
    map_constant='MAP_BUROLE_TOWN',
    map_id=60,
    mechanism='threshold',
    return_direction='UP',
    start_side='origin',
)

warp_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m060e062_warp',
    group='m060e062_warp',
    dest_map_constant='MAP_ROUTE_03_GATEHOUSE',
    direction='DOWN',
    end_side='origin',
    event_id=62,
    map_constant='MAP_BUROLE_TOWN',
    map_id=60,
    mechanism='threshold',
    return_direction='UP',
    start_side='origin',
)

arrival_nudge_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m060e062_arrival_nudge',
    group='m060e062_arrival_nudge',
    event_id=62,
    from_event_id=5,
    from_map_constant='MAP_ROUTE_03_GATEHOUSE',
    map_constant='MAP_BUROLE_TOWN',
    map_id=60,
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m060e062_arrival_nudge_arms',
    group='m060e062_arrival_nudge',
    rows=('map060/ev062/p1/b0',),
    skip_claimed=True,
)

transit_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m001e002_arrival_nudge_transit',
    group='m001e002_arrival_nudge',
    hops=(('MAP_BUROLE_TOWN', 18, 57, 'DOWN', 'MAP_ROUTE_03_GATEHOUSE'),),
)

arrival_nudge_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m001e002_arrival_nudge',
    group='m001e002_arrival_nudge',
    event_id=2,
    from_event_id=1,
    from_map_constant='MAP_BUROLE_TOWN',
    manifest_chapter_id='CH09',
    map_constant='MAP_ROUTE_03_GATEHOUSE',
    map_id=1,
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m001e002_arrival_nudge_arms',
    group='m001e002_arrival_nudge',
    rows=('map001/ev002/p1/b0',),
    manifest_chapter_id='CH09',
    skip_claimed=True,
)

transit_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m001e005_arrival_nudge_transit',
    group='m001e005_arrival_nudge',
    hops=(('MAP_ROUTE_03_GATEHOUSE', 5, 4, 'UP', 'MAP_BUROLE_TOWN'), ('MAP_BUROLE_TOWN', 19, 57, 'DOWN', 'MAP_ROUTE_03_GATEHOUSE')),
)

arrival_nudge_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m001e005_arrival_nudge',
    group='m001e005_arrival_nudge',
    event_id=5,
    from_event_id=62,
    from_map_constant='MAP_BUROLE_TOWN',
    manifest_chapter_id='CH09',
    map_constant='MAP_ROUTE_03_GATEHOUSE',
    map_id=1,
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m001e005_arrival_nudge_arms',
    group='m001e005_arrival_nudge',
    rows=('map001/ev005/p1/b0',),
    manifest_chapter_id='CH09',
    skip_claimed=True,
)

transit_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m060e016p0_transit',
    group='m060e016p0',
    hops=(('MAP_ROUTE_03_GATEHOUSE', 5, 4, 'UP', 'MAP_BUROLE_TOWN'),),
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m060e016p0',
    group='m060e016p0',
    rows=('map060/ev016/p0', 'map060/ev016/p0/b0', 'map060/ev016/p0/b1', 'map060/ev016/p0/b2', 'map060/ev016/p0/b3'),
    approach_prefer='west',
    random_arms=(('map060/ev016/p0/b0', ((102, '==', 2),)), ('map060/ev016/p0/b1', ((102, '!=', 2),)), ('map060/ev016/p0/b2', ((102, '!=', 2), (102, '==', 1))), ('map060/ev016/p0/b3', ((102, '!=', 2), (102, '!=', 1)))),
)

warp_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m060e003_warp',
    group='m060e003_warp',
    dest_map_constant='MAP_BUROLE_TOWN_POKEMART',
    direction='UP',
    end_side='dest',
    event_id=3,
    map_constant='MAP_BUROLE_TOWN',
    map_id=60,
    mechanism='threshold',
    start_side='origin',
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m004e002p0',
    group='m004e002p0',
    rows=('map004/ev002/p0',),
    approach_prefer='south',
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m004e003p0',
    group='m004e003p0',
    rows=('map004/ev003/p0',),
    approach_prefer='east',
)

flavour_npc_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m004e005_flavour_npc',
    group='m004e005_flavour_npc',
    approach_prefer='south',
    event_id=5,
    map_constant='MAP_BUROLE_TOWN_POKEMART',
    map_id=4,
    variant='plain',
)

flavour_npc_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m004e004_flavour_npc',
    group='m004e004_flavour_npc',
    approach_prefer='west',
    event_id=4,
    map_constant='MAP_BUROLE_TOWN_POKEMART',
    map_id=4,
    variant='plain',
)

warp_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m004e001_warp',
    group='m004e001_warp',
    dest_map_constant='MAP_BUROLE_TOWN',
    direction='DOWN',
    end_side='dest',
    event_id=1,
    map_constant='MAP_BUROLE_TOWN_POKEMART',
    map_id=4,
    mechanism='threshold',
    start_side='origin',
)

arrival_nudge_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m060e003_arrival_nudge',
    group='m060e003_arrival_nudge',
    event_id=3,
    from_event_id=1,
    from_map_constant='MAP_BUROLE_TOWN_POKEMART',
    map_constant='MAP_BUROLE_TOWN',
    map_id=60,
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m060e003_arrival_nudge_arms',
    group='m060e003_arrival_nudge',
    rows=('map060/ev003/p1/b0',),
    skip_claimed=True,
)

flavour_npc_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m060e011_flavour_npc',
    group='m060e011_flavour_npc',
    approach_prefer='north',
    event_id=11,
    map_constant='MAP_BUROLE_TOWN',
    map_id=60,
    variant='plain',
)

flavour_npc_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m060e059_flavour_npc',
    group='m060e059_flavour_npc',
    approach_prefer='south',
    event_id=59,
    map_constant='MAP_BUROLE_TOWN',
    map_id=60,
    variant='plain',
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m060e043p0',
    group='m060e043p0',
    rows=('map060/ev043/p0',),
    approach_prefer='south',
)

warp_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m060e044_warp',
    group='m060e044_warp',
    dest_map_constant='MAP_BUROLE_TOWN_SCHOOL',
    direction='UP',
    end_side='dest',
    event_id=44,
    map_constant='MAP_BUROLE_TOWN',
    map_id=60,
    mechanism='threshold',
    start_side='origin',
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m029e003p0',
    group='m029e003p0',
    rows=('map029/ev003/p0', 'map029/ev003/p0/b0', 'map029/ev003/p0/b1'),
    approach_prefer='east',
    random_arms=(('map029/ev003/p0/b0', ((102, '==', 1),)), ('map029/ev003/p0/b1', ((102, '!=', 1),))),
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m029e004p0',
    group='m029e004p0',
    rows=('map029/ev004/p0', 'map029/ev004/p0/b0', 'map029/ev004/p0/b1'),
    approach_prefer='north',
    random_arms=(('map029/ev004/p0/b0', ((102, '==', 1),)), ('map029/ev004/p0/b1', ((102, '!=', 1),))),
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m029e005p0',
    group='m029e005p0',
    rows=('map029/ev005/p0', 'map029/ev005/p0/b0', 'map029/ev005/p0/b1', 'map029/ev005/p0/b2', 'map029/ev005/p0/b3'),
    approach_prefer='south',
    random_arms=(('map029/ev005/p0/b0', ((102, '==', 1),)), ('map029/ev005/p0/b1', ((102, '!=', 1),)), ('map029/ev005/p0/b2', ((102, '!=', 1), (102, '==', 2))), ('map029/ev005/p0/b3', ((102, '!=', 1), (102, '!=', 2)))),
)

warp_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m029e007_warp',
    group='m029e007_warp',
    dest_map_constant='MAP_BUROLE_TOWN_SCHOOL',
    direction='RIGHT',
    end_side='dest',
    event_id=7,
    map_constant='MAP_BUROLE_TOWN_SCHOOL',
    map_id=29,
    mechanism='threshold',
    start_side='origin',
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m029e010p0_c3a1',
    group='m029e010p0',
    rows=('map029/ev010/p0/b3',),
    approach_prefer='south',
    archetype=(('map029/ev010/p0', 'trainer'),),
    choice_answers=((3, 1),),
    walk_rows=('map029/ev010/p0',),
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m029e010p0',
    group='m029e010p0',
    rows=('map029/ev010/p0', 'map029/ev010/p0/b0', 'map029/ev010/p0/b1'),
    approach_prefer='south',
    archetype=(('map029/ev010/p0', 'trainer'),),
    choice_answers=((3, 0),),
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m029e010p1',
    group='m029e010p1',
    rows=('map029/ev010/p1',),
    approach_prefer='south',
    archetype=(('map029/ev010/p1', 'trainer'),),
)

flavour_npc_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m029e011p0_flavour_npc',
    group='m029e011p0_flavour_npc',
    approach_prefer='south',
    event_id=11,
    map_constant='MAP_BUROLE_TOWN_SCHOOL',
    map_id=29,
    variant='plain',
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m029e002p0_c3a1',
    group='m029e002p0',
    rows=('map029/ev002/p0/b3',),
    approach_prefer='east',
    archetype=(('map029/ev002/p0', 'trainer'),),
    choice_answers=((3, 1),),
    walk_rows=('map029/ev002/p0',),
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m029e002p0',
    group='m029e002p0',
    rows=('map029/ev002/p0', 'map029/ev002/p0/b0', 'map029/ev002/p0/b1'),
    approach_prefer='east',
    archetype=(('map029/ev002/p0', 'trainer'),),
    choice_answers=((3, 0),),
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m029e002p1',
    group='m029e002p1',
    rows=('map029/ev002/p1',),
    approach_prefer='east',
    archetype=(('map029/ev002/p1', 'trainer'),),
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m029e009p0_c3a1',
    group='m029e009p0',
    rows=('map029/ev009/p0/b3',),
    approach_prefer='north',
    archetype=(('map029/ev009/p0', 'trainer'),),
    choice_answers=((3, 1),),
    walk_rows=('map029/ev009/p0',),
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m029e009p0',
    group='m029e009p0',
    rows=('map029/ev009/p0', 'map029/ev009/p0/b0', 'map029/ev009/p0/b1'),
    approach_prefer='north',
    archetype=(('map029/ev009/p0', 'trainer'),),
    choice_answers=((3, 0),),
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m029e009p1',
    group='m029e009p1',
    rows=('map029/ev009/p1',),
    approach_prefer='north',
    archetype=(('map029/ev009/p1', 'trainer'),),
)

warp_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m029e008_warp',
    group='m029e008_warp',
    dest_map_constant='MAP_BUROLE_TOWN_SCHOOL',
    direction='RIGHT',
    end_side='dest',
    event_id=8,
    map_constant='MAP_BUROLE_TOWN_SCHOOL',
    map_id=29,
    mechanism='threshold',
    start_side='origin',
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m029e006p0',
    group='m029e006p0',
    rows=('map029/ev006/p0', 'map029/ev006/p0/b0', 'map029/ev006/p0/b1'),
    approach_prefer='south',
    random_arms=(('map029/ev006/p0/b0', ((102, '==', 1),)), ('map029/ev006/p0/b1', ((102, '!=', 1),))),
)

warp_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m029e001_warp',
    group='m029e001_warp',
    dest_map_constant='MAP_BUROLE_TOWN',
    direction='DOWN',
    end_side='dest',
    event_id=1,
    map_constant='MAP_BUROLE_TOWN_SCHOOL',
    map_id=29,
    mechanism='threshold',
    start_side='origin',
)

arrival_nudge_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m060e044_arrival_nudge',
    group='m060e044_arrival_nudge',
    event_id=44,
    from_event_id=1,
    from_map_constant='MAP_BUROLE_TOWN_SCHOOL',
    map_constant='MAP_BUROLE_TOWN',
    map_id=60,
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m060e044_arrival_nudge_arms',
    group='m060e044_arrival_nudge',
    rows=('map060/ev044/p1/b0',),
    skip_claimed=True,
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m060e017p0',
    group='m060e017p0',
    rows=('map060/ev017/p0', 'map060/ev017/p0/b0', 'map060/ev017/p0/b1', 'map060/ev017/p0/b2', 'map060/ev017/p0/b3', 'map060/ev017/p0/b4', 'map060/ev017/p0/b5', 'map060/ev017/p0/b6', 'map060/ev017/p0/b7'),
    approach_prefer='west',
    random_arms=(('map060/ev017/p0/b0', ((102, '==', 0),)), ('map060/ev017/p0/b1', ((102, '!=', 0),)), ('map060/ev017/p0/b2', ((102, '==', 1),)), ('map060/ev017/p0/b3', ((102, '!=', 1),)), ('map060/ev017/p0/b4', ((102, '==', 2),)), ('map060/ev017/p0/b5', ((102, '!=', 2),)), ('map060/ev017/p0/b6', ((102, '==', 3),)), ('map060/ev017/p0/b7', ((102, '!=', 3),))),
)

warp_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m060e047_warp',
    group='m060e047_warp',
    dest_map_constant='MAP_BUROLE_TOWN_HOUSE_1',
    direction='UP',
    end_side='dest',
    event_id=47,
    map_constant='MAP_BUROLE_TOWN',
    map_id=60,
    mechanism='threshold',
    start_side='origin',
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m090e002p0',
    group='m090e002p0',
    rows=('map090/ev002/p0',),
    approach_prefer='west',
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m090e001p0',
    group='m090e001p0',
    rows=('map090/ev001/p0', 'map090/ev001/p0/b0', 'map090/ev001/p0/b1', 'map090/ev001/p0/b2', 'map090/ev001/p0/b3'),
    approach_prefer='south',
    random_arms=(('map090/ev001/p0/b0', ((102, '==', 2),)), ('map090/ev001/p0/b1', ((102, '!=', 2),)), ('map090/ev001/p0/b2', ((102, '!=', 2), (102, '==', 1))), ('map090/ev001/p0/b3', ((102, '!=', 2), (102, '!=', 1)))),
)

warp_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m090e003_warp',
    group='m090e003_warp',
    dest_map_constant='MAP_BUROLE_TOWN',
    direction='DOWN',
    end_side='dest',
    event_id=3,
    map_constant='MAP_BUROLE_TOWN_HOUSE_1',
    map_id=90,
    mechanism='threshold',
    start_side='origin',
)

arrival_nudge_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m060e047_arrival_nudge',
    group='m060e047_arrival_nudge',
    event_id=47,
    from_event_id=3,
    from_map_constant='MAP_BUROLE_TOWN_HOUSE_1',
    map_constant='MAP_BUROLE_TOWN',
    map_id=60,
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m060e047_arrival_nudge_arms',
    group='m060e047_arrival_nudge',
    rows=('map060/ev047/p1/b0',),
    skip_claimed=True,
)

warp_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m060e048_warp',
    group='m060e048_warp',
    dest_map_constant='MAP_BUROLE_TOWN_HOUSE_2',
    direction='UP',
    end_side='dest',
    event_id=48,
    map_constant='MAP_BUROLE_TOWN',
    map_id=60,
    mechanism='threshold',
    start_side='origin',
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m085e001p0',
    group='m085e001p0',
    rows=('map085/ev001/p0', 'map085/ev001/p0/b0', 'map085/ev001/p0/b1', 'map085/ev001/p0/b2', 'map085/ev001/p0/b3'),
    approach_prefer='east',
    random_arms=(('map085/ev001/p0/b0', ((102, '==', 2),)), ('map085/ev001/p0/b1', ((102, '!=', 2),)), ('map085/ev001/p0/b2', ((102, '!=', 2), (102, '==', 1))), ('map085/ev001/p0/b3', ((102, '!=', 2), (102, '!=', 1)))),
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m085e002p0',
    group='m085e002p0',
    rows=('map085/ev002/p0', 'map085/ev002/p0/b0', 'map085/ev002/p0/b1', 'map085/ev002/p0/b2', 'map085/ev002/p0/b3'),
    approach_prefer='south',
    random_arms=(('map085/ev002/p0/b0', ((102, '==', 2),)), ('map085/ev002/p0/b1', ((102, '!=', 2),)), ('map085/ev002/p0/b2', ((102, '!=', 2), (102, '==', 1))), ('map085/ev002/p0/b3', ((102, '!=', 2), (102, '!=', 1)))),
)

warp_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m085e003_warp',
    group='m085e003_warp',
    dest_map_constant='MAP_BUROLE_TOWN',
    direction='DOWN',
    end_side='dest',
    event_id=3,
    map_constant='MAP_BUROLE_TOWN_HOUSE_2',
    map_id=85,
    mechanism='threshold',
    start_side='origin',
)

arrival_nudge_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m060e048_arrival_nudge',
    group='m060e048_arrival_nudge',
    event_id=48,
    from_event_id=3,
    from_map_constant='MAP_BUROLE_TOWN_HOUSE_2',
    map_constant='MAP_BUROLE_TOWN',
    map_id=60,
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m060e048_arrival_nudge_arms',
    group='m060e048_arrival_nudge',
    rows=('map060/ev048/p1/b0',),
    skip_claimed=True,
)

warp_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m060e002_warp',
    group='m060e002_warp',
    dest_map_constant='MAP_BUROLE_TOWN_POKEMON_CENTER',
    direction='UP',
    end_side='dest',
    event_id=2,
    map_constant='MAP_BUROLE_TOWN',
    map_id=60,
    mechanism='threshold',
    start_side='origin',
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m002e004p0',
    group='m002e004p0',
    rows=('map002/ev004/p0', 'map002/ev004/p0/b0', 'map002/ev004/p0/b1', 'map002/ev004/p0/b2', 'map002/ev004/p0/b3'),
    approach_prefer='west',
    archetype=(('map002/ev004/p0', 'flavour_npc'),),
    random_arms=(('map002/ev004/p0/b0', ((102, '==', 1),)), ('map002/ev004/p0/b1', ((102, '!=', 1),)), ('map002/ev004/p0/b2', ((102, '!=', 1), (102, '==', 2))), ('map002/ev004/p0/b3', ((102, '!=', 1), (102, '!=', 2)))),
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m002e003p0',
    group='m002e003p0',
    rows=('map002/ev003/p0',),
    approach_prefer='west',
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m002e001p0_c5a0',
    group='m002e001p0',
    rows=('map002/ev001/p0/b0', 'map002/ev001/p0/b2'),
    approach_prefer='south',
    choice_answers=((5, 0),),
    walk_rows=('map002/ev001/p0',),
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m002e001p0',
    group='m002e001p0',
    rows=('map002/ev001/p0', 'map002/ev001/p0/b3'),
    approach_prefer='south',
    choice_answers=((5, 1),),
)

whiteout_fork_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m002_whiteout',
    group='m002e001p0',
    rows=('map002/ev001/p1',),
    heal_location_id='HEAL_LOCATION_BUROLE_TOWN_POKEMON_CENTER',
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m002e011p0',
    group='m002e011p0',
    rows=('map002/ev011/p0',),
    approach_prefer='south',
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m002e012p0',
    group='m002e012p0',
    rows=('map002/ev012/p0',),
    approach_prefer='south',
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m002e009p0',
    group='m002e009p0',
    rows=('map002/ev009/p0',),
    approach_prefer='south',
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m002e010p0',
    group='m002e010p0',
    rows=('map002/ev010/p0',),
    approach_prefer='south',
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m002e007p0',
    group='m002e007p0',
    rows=('map002/ev007/p0', 'map002/ev007/p0/b0', 'map002/ev007/p0/b1', 'map002/ev007/p0/b2', 'map002/ev007/p0/b3'),
    approach_prefer='north',
    archetype=(('map002/ev007/p0', 'flavour_npc'),),
    random_arms=(('map002/ev007/p0/b0', ((102, '==', 2),)), ('map002/ev007/p0/b1', ((102, '!=', 2),)), ('map002/ev007/p0/b2', ((102, '!=', 2), (102, '==', 1))), ('map002/ev007/p0/b3', ((102, '!=', 2), (102, '!=', 1)))),
)

warp_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m002e002_warp',
    group='m002e002_warp',
    dest_map_constant='MAP_BUROLE_TOWN',
    direction='DOWN',
    end_side='origin',
    event_id=2,
    map_constant='MAP_BUROLE_TOWN_POKEMON_CENTER',
    map_id=2,
    mechanism='threshold',
    return_direction='UP',
    start_side='origin',
)

warp_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m002e008_warp',
    group='m002e008_warp',
    dest_map_constant='MAP_BUROLE_TOWN',
    direction='DOWN',
    end_side='dest',
    event_id=8,
    map_constant='MAP_BUROLE_TOWN_POKEMON_CENTER',
    map_id=2,
    mechanism='threshold',
    start_side='origin',
)

transit_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m060e002_arrival_nudge_transit',
    group='m060e002_arrival_nudge',
    hops=(('MAP_BUROLE_TOWN', 21, 21, 'UP', 'MAP_BUROLE_TOWN_POKEMON_CENTER'), ('MAP_BUROLE_TOWN_POKEMON_CENTER', 7, 18, 'DOWN', 'MAP_BUROLE_TOWN')),
)

arrival_nudge_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m060e002_arrival_nudge',
    group='m060e002_arrival_nudge',
    event_id=2,
    from_event_id=2,
    from_map_constant='MAP_BUROLE_TOWN_POKEMON_CENTER',
    map_constant='MAP_BUROLE_TOWN',
    map_id=60,
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m060e002_arrival_nudge_arms',
    group='m060e002_arrival_nudge',
    rows=('map060/ev002/p1/b0',),
    skip_claimed=True,
)

flavour_npc_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m060e086_flavour_npc',
    group='m060e086_flavour_npc',
    approach_prefer='north',
    event_id=86,
    map_constant='MAP_BUROLE_TOWN',
    map_id=60,
    variant='plain',
)

flavour_npc_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m060e045_flavour_npc',
    group='m060e045_flavour_npc',
    approach_prefer='west',
    event_id=45,
    map_constant='MAP_BUROLE_TOWN',
    map_id=60,
    variant='plain',
)

flavour_npc_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m060e031_flavour_npc',
    group='m060e031_flavour_npc',
    approach_prefer='east',
    event_id=31,
    map_constant='MAP_BUROLE_TOWN',
    map_id=60,
    variant='plain',
)

warp_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m060e004_warp',
    group='m060e004_warp',
    dest_map_constant='MAP_BUROLE_TOWN_GYM',
    direction='UP',
    end_side='dest',
    event_id=4,
    map_constant='MAP_BUROLE_TOWN',
    map_id=60,
    mechanism='threshold',
    start_side='origin',
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m066e021p0',
    group='m066e021p0',
    rows=('map066/ev021/p0',),
    approach_prefer='arrive@(19,36)',
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m066e024p0',
    group='m066e024p0',
    rows=('map066/ev024/p0', 'map066/ev024/p0/b0'),
    approach_prefer='east',
)

flavour_npc_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m066e024p1_flavour_npc',
    group='m066e024p1_flavour_npc',
    approach_prefer='east',
    event_id=24,
    map_constant='MAP_BUROLE_TOWN_GYM',
    map_id=66,
    page_idx=1,
    variant='plain',
)

trainer_beats(
    ch10,
    chapter_id='CH10',
    beat_prefix='m066e002_trainer',
    group='m066e002_trainer',
    approach_prefer='north',
    defeat_flag='TRAINER_FLAGS_START + TRAINER_JANG_31',
    deferred_retalks=('map066/ev002/p2',),
    double=False,
    event_id=2,
    map_constant='MAP_BUROLE_TOWN_GYM',
    map_id=66,
    phone=False,
    retalk_pages=2,
    rider=False,
    trainer_const='TRAINER_JANG_31',
    trigger='event_touch',
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m066e002_trainer_arms',
    group='m066e002_trainer',
    rows=('map066/ev002/p0/b0',),
    approach_prefer='north',
    skip_claimed=True,
)

stair_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m066stair14x21',
    group='m066stair14x21',
    rows=('map066/terrain/stairs/14,21', 'map066/terrain/stairs/14,22', 'map066/terrain/stairs/15,23', 'map066/terrain/stairs/15,24'),
    approach_prefer='east',
)

trainer_beats(
    ch10,
    chapter_id='CH10',
    beat_prefix='m066e001_trainer',
    group='m066e001_trainer',
    approach_prefer='east',
    defeat_flag='TRAINER_FLAGS_START + TRAINER_TOD_30',
    deferred_retalks=('map066/ev001/p2',),
    double=False,
    event_id=1,
    map_constant='MAP_BUROLE_TOWN_GYM',
    map_id=66,
    phone=False,
    retalk_pages=2,
    rider=False,
    trainer_const='TRAINER_TOD_30',
    trigger='event_touch',
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m066e001_trainer_arms',
    group='m066e001_trainer',
    rows=('map066/ev001/p0/b0',),
    approach_prefer='east',
    skip_claimed=True,
)

trainer_beats(
    ch10,
    chapter_id='CH10',
    beat_prefix='m066e003_trainer',
    group='m066e003_trainer',
    approach_prefer='west',
    defeat_flag='TRAINER_FLAGS_START + TRAINER_MARTIN_32',
    deferred_retalks=('map066/ev003/p2',),
    double=False,
    event_id=3,
    map_constant='MAP_BUROLE_TOWN_GYM',
    map_id=66,
    phone=False,
    retalk_pages=2,
    rider=False,
    trainer_const='TRAINER_MARTIN_32',
    trigger='event_touch',
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m066e003_trainer_arms',
    group='m066e003_trainer',
    rows=('map066/ev003/p0/b0',),
    approach_prefer='west',
    skip_claimed=True,
)

stair_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m066stair23x23',
    group='m066stair23x23',
    rows=('map066/terrain/stairs/23,23', 'map066/terrain/stairs/23,24', 'map066/terrain/stairs/24,21', 'map066/terrain/stairs/24,22'),
    approach_prefer='west',
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m066e045p0',
    group='m066e045p0',
    rows=('map066/ev045/p0', 'map066/ev045/p0/b0', 'map066/ev045/p0/b1'),
    approach_prefer='north',
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m066e004p0',
    group='m066e004p0',
    rows=('map066/ev004/p0', 'map066/ev004/p0/b0', 'map066/ev004/p0/b1'),
    approach_prefer='south',
    archetype=(('map066/ev004/p0', 'trainer'),),
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m066e004p1',
    group='m066e004p1',
    rows=('map066/ev004/p1',),
    approach_prefer='south',
    archetype=(('map066/ev004/p1', 'trainer'),),
)

smash_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m066smash_rock_smash',
    group='m066smash_rock_smash',
    rows=('map066/ev005/p0', 'map066/ev005/p0/b0', 'map066/ev006/p0', 'map066/ev006/p0/b0', 'map066/ev007/p0', 'map066/ev007/p0/b0', 'map066/ev008/p0', 'map066/ev008/p0/b0', 'map066/ev009/p0', 'map066/ev009/p0/b0', 'map066/ev010/p0', 'map066/ev010/p0/b0', 'map066/ev011/p0', 'map066/ev011/p0/b0', 'map066/ev013/p0', 'map066/ev013/p0/b0', 'map066/ev014/p0', 'map066/ev014/p0/b0', 'map066/ev015/p0', 'map066/ev015/p0/b0', 'map066/ev016/p0', 'map066/ev016/p0/b0', 'map066/ev017/p0', 'map066/ev017/p0/b0', 'map066/ev018/p0', 'map066/ev018/p0/b0', 'map066/ev019/p0', 'map066/ev019/p0/b0', 'map066/ev020/p0', 'map066/ev020/p0/b0'),
    approach_prefer='east',
    capability='rock_smash',
    sight_trainers=(),
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m066e003p2',
    group='m066e003p2',
    rows=('map066/ev003/p2',),
    approach_prefer='west',
    archetype=(('map066/ev003/p2', 'trainer'),),
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m066e001p2',
    group='m066e001p2',
    rows=('map066/ev001/p2',),
    approach_prefer='east',
    archetype=(('map066/ev001/p2', 'trainer'),),
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m066e002p2',
    group='m066e002p2',
    rows=('map066/ev002/p2',),
    approach_prefer='south',
    archetype=(('map066/ev002/p2', 'trainer'),),
)

flavour_npc_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m066e024p2_flavour_npc',
    group='m066e024p2_flavour_npc',
    approach_prefer='east',
    event_id=24,
    map_constant='MAP_BUROLE_TOWN_GYM',
    map_id=66,
    page_idx=2,
    variant='plain',
)

warp_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m066e012_warp',
    group='m066e012_warp',
    dest_map_constant='MAP_BUROLE_TOWN',
    direction='DOWN',
    end_side='dest',
    event_id=12,
    map_constant='MAP_BUROLE_TOWN_GYM',
    map_id=66,
    mechanism='threshold',
    start_side='origin',
)

arrival_nudge_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m060e004_arrival_nudge',
    group='m060e004_arrival_nudge',
    event_id=4,
    from_event_id=12,
    from_map_constant='MAP_BUROLE_TOWN_GYM',
    map_constant='MAP_BUROLE_TOWN',
    map_id=60,
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m060e004_arrival_nudge_arms',
    group='m060e004_arrival_nudge',
    rows=('map060/ev004/p1/b0',),
    skip_claimed=True,
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m060e012p0',
    group='m060e012p0',
    rows=('map060/ev012/p0', 'map060/ev012/p0/b0', 'map060/ev012/p0/b1'),
    approach_prefer='north',
    archetype=(('map060/ev012/p0', 'flavour_npc'),),
    random_arms=(('map060/ev012/p0/b0', ((102, '==', 1),)), ('map060/ev012/p0/b1', ((102, '!=', 1),))),
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m060e010p0',
    group='m060e010p0',
    rows=('map060/ev010/p0', 'map060/ev010/p0/b0', 'map060/ev010/p0/b1'),
    approach_prefer='north',
    random_arms=(('map060/ev010/p0/b0', ((102, '==', 1),)), ('map060/ev010/p0/b1', ((102, '!=', 1),))),
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m060e014p0',
    group='m060e014p0',
    rows=('map060/ev014/p0', 'map060/ev014/p0/b0', 'map060/ev014/p0/b1'),
    approach_prefer='north',
    random_arms=(('map060/ev014/p0/b0', ((102, '==', 1),)), ('map060/ev014/p0/b1', ((102, '!=', 1),))),
)

flavour_npc_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m060e087_flavour_npc',
    group='m060e087_flavour_npc',
    approach_prefer='east',
    event_id=87,
    map_constant='MAP_BUROLE_TOWN',
    map_id=60,
    variant='plain',
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m060e042p0',
    group='m060e042p0',
    rows=('map060/ev042/p0', 'map060/ev042/p0/b17'),
    approach_prefer='south',
    choice_answers=((2, 1),),
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m060e005p0_c4a0',
    group='m060e005p0',
    rows=('map060/ev005/p0/b0',),
    approach_prefer='east',
    choice_answers=((4, 0),),
    walk_rows=('map060/ev005/p0',),
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m060e005p0',
    group='m060e005p0',
    rows=('map060/ev005/p0', 'map060/ev005/p0/b1'),
    approach_prefer='east',
    choice_answers=((4, 1),),
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m060e018p0',
    group='m060e018p0',
    rows=('map060/ev018/p0',),
    approach_prefer='north',
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m060e006p0',
    group='m060e006p0',
    rows=('map060/ev006/p0',),
    approach_prefer='north',
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m060e007p0',
    group='m060e007p0',
    rows=('map060/ev007/p0', 'map060/ev007/p0/b21'),
    approach_prefer='west',
    choice_answers=((2, 3),),
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m060e013p0',
    group='m060e013p0',
    rows=('map060/ev013/p0', 'map060/ev013/p0/b0', 'map060/ev013/p0/b1'),
    approach_prefer='north',
    random_arms=(('map060/ev013/p0/b0', ((102, '==', 1),)), ('map060/ev013/p0/b1', ((102, '!=', 1),))),
)

generic_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m060e015p0',
    group='m060e015p0',
    rows=('map060/ev015/p0', 'map060/ev015/p0/b0', 'map060/ev015/p0/b1'),
    approach_prefer='south',
    random_arms=(('map060/ev015/p0/b0', ((102, '==', 1),)), ('map060/ev015/p0/b1', ((102, '!=', 1),))),
)

flavour_npc_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m060e020_flavour_npc',
    group='m060e020_flavour_npc',
    approach_prefer='south',
    event_id=20,
    map_constant='MAP_BUROLE_TOWN',
    map_id=60,
    variant='plain',
)

warp_beat(
    ch10,
    chapter_id='CH10',
    beat_name='m060e032_warp',
    group='m060e032_warp',
    boundary=True,
    dest_map_constant='MAP_ROUTE_04',
    direction='RIGHT',
    event_id=32,
    map_constant='MAP_BUROLE_TOWN',
    map_id=60,
    mechanism='threshold',
)

NEVER_FIRES: dict[str, str] = {
    'map002/ev011/p1': "archetype_kwargs: map002/ev011/p1: no warp lands on this arrival autorun's cell (7,12) on map 2 -- it never fires",
    'map002/ev011/p1/b0': "archetype_kwargs: map002/ev011/p1: no warp lands on this arrival autorun's cell (7,12) on map 2 -- it never fires",
    'map002/ev011/p1/b1': "archetype_kwargs: map002/ev011/p1: no warp lands on this arrival autorun's cell (7,12) on map 2 -- it never fires",
    'map029/ev011/p1': "map029/ev011/p1 (needs var 107 >= 3) is not its event's live page at this route position: var 107 >= 3 fails: var 107 was set to [1] by map029/ev010/p0 (beat m029e010p0, #30); the rows that could write it none are not walked before it; live page: map029/ev011/p0 (needs no condition)",
    'map029/ev011/p1/b0': "map029/ev011/p1 (needs var 107 >= 3) is not its event's live page at this route position: var 107 >= 3 fails: var 107 was set to [1] by map029/ev010/p0 (beat m029e010p0, #30); the rows that could write it none are not walked before it; live page: map029/ev011/p0 (needs no condition)",
    'map029/ev011/p1/b1': "map029/ev011/p1 (needs var 107 >= 3) is not its event's live page at this route position: var 107 >= 3 fails: var 107 was set to [1] by map029/ev010/p0 (beat m029e010p0, #30); the rows that could write it none are not walked before it; live page: map029/ev011/p0 (needs no condition)",
    'map029/ev011/p1/b3': "map029/ev011/p1 (needs var 107 >= 3) is not its event's live page at this route position: var 107 >= 3 fails: var 107 was set to [1] by map029/ev010/p0 (beat m029e010p0, #30); the rows that could write it none are not walked before it; live page: map029/ev011/p0 (needs no condition)",
    'map029/ev011/p3': "map029/ev011/p3 (needs var 107 >= 3 and self switch B == True) is not its event's live page at this route position: var 107 >= 3 fails: var 107 was set to [1] by map029/ev010/p0 (beat m029e010p0, #30); the rows that could write it none are not walked before it; self switch B == True fails: self switch B is [False] (seed state), never written on the route; the rows that could write it ['map029/ev011/p2'] are not walked before it; live page: map029/ev011/p0 (needs no condition)",
    'map060/ev008/p1': "archetype_kwargs: map060/ev008/p1: no warp lands on this arrival autorun's cell (58,20) on map 60 -- it never fires",
    'map060/ev008/p1/b0': "archetype_kwargs: map060/ev008/p1: no warp lands on this arrival autorun's cell (58,20) on map 60 -- it never fires",
    'map060/ev008/p1/b1': "archetype_kwargs: map060/ev008/p1: no warp lands on this arrival autorun's cell (58,20) on map 60 -- it never fires",
    'map060/ev009/p1': "archetype_kwargs: map060/ev009/p1: no warp lands on this arrival autorun's cell (59,20) on map 60 -- it never fires",
    'map060/ev009/p1/b0': "archetype_kwargs: map060/ev009/p1: no warp lands on this arrival autorun's cell (59,20) on map 60 -- it never fires",
    'map060/ev009/p1/b1': "archetype_kwargs: map060/ev009/p1: no warp lands on this arrival autorun's cell (59,20) on map 60 -- it never fires",
}

EMPTY_PAGES: dict[str, str] = {
    'map002/ev005/p0': 'every page of the event is empty; nothing to check on the ROM',
    'map002/ev005/p1': 'every page of the event is empty; nothing to check on the ROM',
    'map002/ev005/p2': 'every page of the event is empty; nothing to check on the ROM',
    'map002/ev005/p3': 'every page of the event is empty; nothing to check on the ROM',
    'map002/ev005/p4': 'every page of the event is empty; nothing to check on the ROM',
    'map002/ev005/p5': 'every page of the event is empty; nothing to check on the ROM',
    'map002/ev005/p6': 'every page of the event is empty; nothing to check on the ROM',
    'map002/ev006/p0': 'every page of the event is empty; nothing to check on the ROM',
    'map002/ev006/p1': 'every page of the event is empty; nothing to check on the ROM',
    'map002/ev006/p2': 'every page of the event is empty; nothing to check on the ROM',
    'map002/ev006/p3': 'every page of the event is empty; nothing to check on the ROM',
    'map002/ev006/p4': 'every page of the event is empty; nothing to check on the ROM',
    'map002/ev006/p5': 'every page of the event is empty; nothing to check on the ROM',
    'map002/ev006/p6': 'every page of the event is empty; nothing to check on the ROM',
    'map060/ev019/p0': 'every page of the event is empty; nothing to check on the ROM',
    'map060/ev046/p0': 'every page of the event is empty; nothing to check on the ROM',
    'map066/ev005/p1': "the cleared obstacle's empty page; its smash beat asserts the obstacle is gone",
    'map066/ev006/p1': "the cleared obstacle's empty page; its smash beat asserts the obstacle is gone",
    'map066/ev007/p1': "the cleared obstacle's empty page; its smash beat asserts the obstacle is gone",
    'map066/ev008/p1': "the cleared obstacle's empty page; its smash beat asserts the obstacle is gone",
    'map066/ev009/p1': "the cleared obstacle's empty page; its smash beat asserts the obstacle is gone",
    'map066/ev010/p1': "the cleared obstacle's empty page; its smash beat asserts the obstacle is gone",
    'map066/ev011/p1': "the cleared obstacle's empty page; its smash beat asserts the obstacle is gone",
    'map066/ev013/p1': "the cleared obstacle's empty page; its smash beat asserts the obstacle is gone",
    'map066/ev014/p1': "the cleared obstacle's empty page; its smash beat asserts the obstacle is gone",
    'map066/ev015/p1': "the cleared obstacle's empty page; its smash beat asserts the obstacle is gone",
    'map066/ev016/p1': "the cleared obstacle's empty page; its smash beat asserts the obstacle is gone",
    'map066/ev017/p1': "the cleared obstacle's empty page; its smash beat asserts the obstacle is gone",
    'map066/ev018/p1': "the cleared obstacle's empty page; its smash beat asserts the obstacle is gone",
    'map066/ev019/p1': "the cleared obstacle's empty page; its smash beat asserts the obstacle is gone",
    'map066/ev020/p1': "the cleared obstacle's empty page; its smash beat asserts the obstacle is gone",
    'map066/ev045/p1': 'a blank, empty page: the ROM hides the object by flag on it, so there is nothing to talk to',
    'map066/ev046/p0': 'every page of the event is empty; nothing to check on the ROM',
    'map066/ev046/p1': 'every page of the event is empty; nothing to check on the ROM',
    'map066/ev047/p0': 'every page of the event is empty; nothing to check on the ROM',
    'map066/ev047/p1': 'every page of the event is empty; nothing to check on the ROM',
    'map066/ev048/p0': 'every page of the event is empty; nothing to check on the ROM',
    'map066/ev048/p1': 'every page of the event is empty; nothing to check on the ROM',
    'map066/ev049/p0': 'every page of the event is empty; nothing to check on the ROM',
    'map066/ev049/p1': 'every page of the event is empty; nothing to check on the ROM',
    'map066/ev050/p0': 'every page of the event is empty; nothing to check on the ROM',
    'map066/ev050/p1': 'every page of the event is empty; nothing to check on the ROM',
    'map066/ev051/p0': 'every page of the event is empty; nothing to check on the ROM',
    'map066/ev051/p1': 'every page of the event is empty; nothing to check on the ROM',
    'map066/ev052/p0': 'every page of the event is empty; nothing to check on the ROM',
    'map066/ev052/p1': 'every page of the event is empty; nothing to check on the ROM',
    'map066/ev053/p0': 'every page of the event is empty; nothing to check on the ROM',
    'map066/ev053/p1': 'every page of the event is empty; nothing to check on the ROM',
}

WALK_CHECKED: dict[str, str] = {
    'map002/ev004/p0/b0': 'arm on a rolled or computed value (var 102 == 1); the walk checks whichever fires',
    'map002/ev004/p0/b1': 'arm on a rolled or computed value (var 102 != 1); the walk checks whichever fires',
    'map002/ev004/p0/b2': 'arm on a rolled or computed value (var 102 != 1 and var 102 == 2); the walk checks whichever fires',
    'map002/ev004/p0/b3': 'arm on a rolled or computed value (var 102 != 1 and var 102 != 2); the walk checks whichever fires',
    'map002/ev007/p0/b0': 'arm on a rolled or computed value (var 102 == 2); the walk checks whichever fires',
    'map002/ev007/p0/b1': 'arm on a rolled or computed value (var 102 != 2); the walk checks whichever fires',
    'map002/ev007/p0/b2': 'arm on a rolled or computed value (var 102 != 2 and var 102 == 1); the walk checks whichever fires',
    'map002/ev007/p0/b3': 'arm on a rolled or computed value (var 102 != 2 and var 102 != 1); the walk checks whichever fires',
    'map029/ev003/p0/b0': 'arm on a rolled or computed value (var 102 == 1); the walk checks whichever fires',
    'map029/ev003/p0/b1': 'arm on a rolled or computed value (var 102 != 1); the walk checks whichever fires',
    'map029/ev004/p0/b0': 'arm on a rolled or computed value (var 102 == 1); the walk checks whichever fires',
    'map029/ev004/p0/b1': 'arm on a rolled or computed value (var 102 != 1); the walk checks whichever fires',
    'map029/ev005/p0/b0': 'arm on a rolled or computed value (var 102 == 1); the walk checks whichever fires',
    'map029/ev005/p0/b1': 'arm on a rolled or computed value (var 102 != 1); the walk checks whichever fires',
    'map029/ev005/p0/b2': 'arm on a rolled or computed value (var 102 != 1 and var 102 == 2); the walk checks whichever fires',
    'map029/ev005/p0/b3': 'arm on a rolled or computed value (var 102 != 1 and var 102 != 2); the walk checks whichever fires',
    'map029/ev006/p0/b0': 'arm on a rolled or computed value (var 102 == 1); the walk checks whichever fires',
    'map029/ev006/p0/b1': 'arm on a rolled or computed value (var 102 != 1); the walk checks whichever fires',
    'map060/ev010/p0/b0': 'arm on a rolled or computed value (var 102 == 1); the walk checks whichever fires',
    'map060/ev010/p0/b1': 'arm on a rolled or computed value (var 102 != 1); the walk checks whichever fires',
    'map060/ev012/p0/b0': 'arm on a rolled or computed value (var 102 == 1); the walk checks whichever fires',
    'map060/ev012/p0/b1': 'arm on a rolled or computed value (var 102 != 1); the walk checks whichever fires',
    'map060/ev013/p0/b0': 'arm on a rolled or computed value (var 102 == 1); the walk checks whichever fires',
    'map060/ev013/p0/b1': 'arm on a rolled or computed value (var 102 != 1); the walk checks whichever fires',
    'map060/ev014/p0/b0': 'arm on a rolled or computed value (var 102 == 1); the walk checks whichever fires',
    'map060/ev014/p0/b1': 'arm on a rolled or computed value (var 102 != 1); the walk checks whichever fires',
    'map060/ev015/p0/b0': 'arm on a rolled or computed value (var 102 == 1); the walk checks whichever fires',
    'map060/ev015/p0/b1': 'arm on a rolled or computed value (var 102 != 1); the walk checks whichever fires',
    'map060/ev016/p0/b0': 'arm on a rolled or computed value (var 102 == 2); the walk checks whichever fires',
    'map060/ev016/p0/b1': 'arm on a rolled or computed value (var 102 != 2); the walk checks whichever fires',
    'map060/ev016/p0/b2': 'arm on a rolled or computed value (var 102 != 2 and var 102 == 1); the walk checks whichever fires',
    'map060/ev016/p0/b3': 'arm on a rolled or computed value (var 102 != 2 and var 102 != 1); the walk checks whichever fires',
    'map060/ev017/p0/b0': 'arm on a rolled or computed value (var 102 == 0); the walk checks whichever fires',
    'map060/ev017/p0/b1': 'arm on a rolled or computed value (var 102 != 0); the walk checks whichever fires',
    'map060/ev017/p0/b2': 'arm on a rolled or computed value (var 102 == 1); the walk checks whichever fires',
    'map060/ev017/p0/b3': 'arm on a rolled or computed value (var 102 != 1); the walk checks whichever fires',
    'map060/ev017/p0/b4': 'arm on a rolled or computed value (var 102 == 2); the walk checks whichever fires',
    'map060/ev017/p0/b5': 'arm on a rolled or computed value (var 102 != 2); the walk checks whichever fires',
    'map060/ev017/p0/b6': 'arm on a rolled or computed value (var 102 == 3); the walk checks whichever fires',
    'map060/ev017/p0/b7': 'arm on a rolled or computed value (var 102 != 3); the walk checks whichever fires',
    'map085/ev001/p0/b0': 'arm on a rolled or computed value (var 102 == 2); the walk checks whichever fires',
    'map085/ev001/p0/b1': 'arm on a rolled or computed value (var 102 != 2); the walk checks whichever fires',
    'map085/ev001/p0/b2': 'arm on a rolled or computed value (var 102 != 2 and var 102 == 1); the walk checks whichever fires',
    'map085/ev001/p0/b3': 'arm on a rolled or computed value (var 102 != 2 and var 102 != 1); the walk checks whichever fires',
    'map085/ev002/p0/b0': 'arm on a rolled or computed value (var 102 == 2); the walk checks whichever fires',
    'map085/ev002/p0/b1': 'arm on a rolled or computed value (var 102 != 2); the walk checks whichever fires',
    'map085/ev002/p0/b2': 'arm on a rolled or computed value (var 102 != 2 and var 102 == 1); the walk checks whichever fires',
    'map085/ev002/p0/b3': 'arm on a rolled or computed value (var 102 != 2 and var 102 != 1); the walk checks whichever fires',
    'map090/ev001/p0/b0': 'arm on a rolled or computed value (var 102 == 2); the walk checks whichever fires',
    'map090/ev001/p0/b1': 'arm on a rolled or computed value (var 102 != 2); the walk checks whichever fires',
    'map090/ev001/p0/b2': 'arm on a rolled or computed value (var 102 != 2 and var 102 == 1); the walk checks whichever fires',
    'map090/ev001/p0/b3': 'arm on a rolled or computed value (var 102 != 2 and var 102 != 1); the walk checks whichever fires',
}

ELSEWHERE: dict[str, str] = {
    'map001/ev002/p1/b1': 'unselected_arm: not taken on the walk: else of `get_character(0).onEvent?` from cell (5, 3) (event at (5, 3)) (ruling 19)',
    'map001/ev005/p1/b1': 'unselected_arm: not taken on the walk: else of `get_character(0).onEvent?` from cell (6, 3) (event at (6, 3)) (ruling 19)',
    'map029/ev002/p0/b2': 'unselected_arm: blocked by fork:whiteout; the walk takes the sibling arm (ruling 19)',
    'map029/ev009/p0/b2': 'unselected_arm: blocked by fork:whiteout; the walk takes the sibling arm (ruling 19)',
    'map029/ev010/p0/b2': 'unselected_arm: blocked by fork:whiteout; the walk takes the sibling arm (ruling 19)',
    'map029/ev011/p1/b2': 'unselected_arm: blocked by fork:whiteout; the walk takes the sibling arm (ruling 19)',
    'map029/ev011/p2': "arm_gated: map029/ev011/p2 (needs var 107 >= 3 and self switch A == True) is not its event's live page at this route position: var 107 >= 3 fails: var 107 was set to [1] by map029/ev010/p0 (beat m029e010p0, #30); the rows that could write it none are not walked before it; self switch A == True fails: self switch A is [False] (seed state), never written on the route; the rows that could write it ['map029/ev011/p1/b1', 'map029/ev011/p2/b0'] are not walked before it; live page: map029/ev011/p0 (needs no condition); reachable on the ROM through the unwalked arm(s) ['map029/ev011/p1/b1', 'map029/ev011/p2/b0'] of a page the route fires",
    'map029/ev011/p2/b0': "arm_gated: map029/ev011/p2 (needs var 107 >= 3 and self switch A == True) is not its event's live page at this route position: var 107 >= 3 fails: var 107 was set to [1] by map029/ev010/p0 (beat m029e010p0, #30); the rows that could write it none are not walked before it; self switch A == True fails: self switch A is [False] (seed state), never written on the route; the rows that could write it ['map029/ev011/p1/b1', 'map029/ev011/p2/b0'] are not walked before it; live page: map029/ev011/p0 (needs no condition); reachable on the ROM through the unwalked arm(s) ['map029/ev011/p1/b1', 'map029/ev011/p2/b0'] of a page the route fires",
    'map029/ev011/p2/b1': 'unselected_arm: blocked by harness:full_bag; the walk takes the sibling arm (ruling 19)',
    'map060/ev001/p1/b1': 'unselected_arm: not taken on the walk: else of `get_character(0).onEvent?` from cell (18, 58) (event at (18, 58)) (ruling 19)',
    'map060/ev002/p1/b1': 'unselected_arm: not taken on the walk: else of `get_character(0).onEvent?` from cell (21, 20) (event at (21, 20)) (ruling 19)',
    'map060/ev003/p1/b1': 'unselected_arm: not taken on the walk: else of `get_character(0).onEvent?` from cell (22, 45) (event at (22, 45)) (ruling 19)',
    'map060/ev004/p1/b1': 'unselected_arm: not taken on the walk: else of `get_character(0).onEvent?` from cell (39, 7) (event at (39, 7)) (ruling 19)',
    'map060/ev007/p0/b1': "unselected_arm: not taken on the walk: it sits inside map060/ev007/p0/b0, which the walk doesn't take (ruling 19)",
    'map060/ev007/p0/b13': "unselected_arm: not taken on the walk: it sits inside map060/ev007/p0/b7, which the walk doesn't take (ruling 19)",
    'map060/ev007/p0/b15': "unselected_arm: not taken on the walk: it sits inside map060/ev007/p0/b14, which the walk doesn't take (ruling 19)",
    'map060/ev007/p0/b20': "unselected_arm: not taken on the walk: it sits inside map060/ev007/p0/b14, which the walk doesn't take (ruling 19)",
    'map060/ev007/p0/b6': "unselected_arm: not taken on the walk: it sits inside map060/ev007/p0/b0, which the walk doesn't take (ruling 19)",
    'map060/ev007/p0/b8': "unselected_arm: not taken on the walk: it sits inside map060/ev007/p0/b7, which the walk doesn't take (ruling 19)",
    'map060/ev021/p0': 'stripped: strip_list.json map_events (Luz)',
    'map060/ev022/p0': 'stripped: strip_list.json map_events (Luz)',
    'map060/ev023/p0': 'stripped: strip_list.json map_events (Luz)',
    'map060/ev024/p0': 'stripped: strip_list.json map_events (Luz)',
    'map060/ev025/p0': 'stripped: strip_list.json map_events (Luz)',
    'map060/ev026/p0': 'stripped: strip_list.json map_events (Luz)',
    'map060/ev027/p0': 'stripped: strip_list.json map_events (Luz)',
    'map060/ev028/p0': 'stripped: strip_list.json map_events (Luz)',
    'map060/ev029/p0': 'stripped: strip_list.json map_events (Luz)',
    'map060/ev030/p0': 'stripped: strip_list.json map_events (Luz)',
    'map060/ev032/p1': "later: CH11: its event crosses out of the chapter's map chain (to map(s) [9]); the rest of the event belongs to the chapter that builds the far side",
    'map060/ev032/p1/b0': "later: CH11: its event crosses out of the chapter's map chain (to map(s) [9]); the rest of the event belongs to the chapter that builds the far side",
    'map060/ev032/p1/b1': "later: CH11: its event crosses out of the chapter's map chain (to map(s) [9]); the rest of the event belongs to the chapter that builds the far side",
    'map060/ev033/p0': 'stripped: strip_list.json map_events (Luz)',
    'map060/ev034/p0': 'stripped: strip_list.json map_events (Luz)',
    'map060/ev035/p0': 'stripped: strip_list.json map_events (Luz)',
    'map060/ev036/p0': 'stripped: strip_list.json map_events (Luz)',
    'map060/ev037/p0': 'stripped: strip_list.json map_events (Luz)',
    'map060/ev038/p0': 'stripped: strip_list.json map_events (Luz)',
    'map060/ev039/p0': 'stripped: strip_list.json map_events (Luz)',
    'map060/ev040/p0': 'stripped: strip_list.json map_events (Luz)',
    'map060/ev041/p0': 'stripped: strip_list.json map_events (EV041)',
    'map060/ev044/p1/b1': 'unselected_arm: not taken on the walk: else of `get_character(0).onEvent?` from cell (12, 41) (event at (12, 41)) (ruling 19)',
    'map060/ev047/p1/b1': 'unselected_arm: not taken on the walk: else of `get_character(0).onEvent?` from cell (11, 31) (event at (11, 31)) (ruling 19)',
    'map060/ev048/p1/b1': 'unselected_arm: not taken on the walk: else of `get_character(0).onEvent?` from cell (14, 24) (event at (14, 24)) (ruling 19)',
    'map060/ev062/p1/b1': 'unselected_arm: not taken on the walk: else of `get_character(0).onEvent?` from cell (19, 58) (event at (19, 58)) (ruling 19)',
    'map060/ev065/p0': 'stripped: strip_list.json map_events (Luz)',
    'map060/ev066/p0': 'stripped: strip_list.json map_events (Luz)',
    'map060/ev071/p0': 'stripped: strip_list.json map_events (EV071)',
    'map060/ev072/p0': 'stripped: strip_list.json map_events (Luz)',
    'map060/ev073/p0': 'stripped: strip_list.json map_events (Luz)',
    'map060/ev074/p0': 'stripped: strip_list.json map_events (Luz)',
    'map060/ev075/p0': 'stripped: strip_list.json map_events (Luz)',
    'map060/ev076/p0': 'stripped: strip_list.json map_events (Luz)',
    'map060/ev077/p0': 'stripped: strip_list.json map_events (Luz)',
    'map060/ev078/p0': 'stripped: strip_list.json map_events (Luz)',
    'map060/ev079/p0': 'stripped: strip_list.json map_events (Luz)',
    'map060/ev080/p0': 'stripped: strip_list.json map_events (Luz)',
    'map060/ev081/p0': 'stripped: strip_list.json map_events (Luz)',
    'map060/ev082/p0': 'stripped: strip_list.json map_events (Luz)',
    'map060/ev083/p0': 'stripped: strip_list.json map_events (Luz)',
    'map060/ev084/p0': 'stripped: strip_list.json map_events (Luz)',
    'map066/ev001/p0/b1': 'unselected_arm: blocked by fork:whiteout; the walk takes the sibling arm (ruling 19)',
    'map066/ev002/p0/b1': 'unselected_arm: blocked by fork:whiteout; the walk takes the sibling arm (ruling 19)',
    'map066/ev003/p0/b1': 'unselected_arm: blocked by fork:whiteout; the walk takes the sibling arm (ruling 19)',
    'map066/ev004/p0/b2': 'unselected_arm: blocked by harness:full_bag; the walk takes the sibling arm (ruling 19)',
    'map066/ev004/p0/b3': 'unselected_arm: blocked by fork:whiteout; the walk takes the sibling arm (ruling 19)',
    'map066/ev005/p0/b1': 'unselected_arm: blocked by capability:rock_smash; the walk takes the sibling arm (ruling 19)',
    'map066/ev005/p0/b2': 'unselected_arm: blocked by capability:rock_smash; the walk takes the sibling arm (ruling 19)',
    'map066/ev005/p0/b3': 'unselected_arm: the no-capability branch; the walk holds the capability and its smash beat answers YES (CH08 §9)',
    'map066/ev006/p0/b1': 'unselected_arm: blocked by capability:rock_smash; the walk takes the sibling arm (ruling 19)',
    'map066/ev006/p0/b2': 'unselected_arm: blocked by capability:rock_smash; the walk takes the sibling arm (ruling 19)',
    'map066/ev006/p0/b3': 'unselected_arm: the no-capability branch; the walk holds the capability and its smash beat answers YES (CH08 §9)',
    'map066/ev007/p0/b1': 'unselected_arm: blocked by capability:rock_smash; the walk takes the sibling arm (ruling 19)',
    'map066/ev007/p0/b2': 'unselected_arm: blocked by capability:rock_smash; the walk takes the sibling arm (ruling 19)',
    'map066/ev007/p0/b3': 'unselected_arm: the no-capability branch; the walk holds the capability and its smash beat answers YES (CH08 §9)',
    'map066/ev008/p0/b1': 'unselected_arm: blocked by capability:rock_smash; the walk takes the sibling arm (ruling 19)',
    'map066/ev008/p0/b2': 'unselected_arm: blocked by capability:rock_smash; the walk takes the sibling arm (ruling 19)',
    'map066/ev008/p0/b3': 'unselected_arm: the no-capability branch; the walk holds the capability and its smash beat answers YES (CH08 §9)',
    'map066/ev009/p0/b1': 'unselected_arm: blocked by capability:rock_smash; the walk takes the sibling arm (ruling 19)',
    'map066/ev009/p0/b2': 'unselected_arm: blocked by capability:rock_smash; the walk takes the sibling arm (ruling 19)',
    'map066/ev009/p0/b3': 'unselected_arm: the no-capability branch; the walk holds the capability and its smash beat answers YES (CH08 §9)',
    'map066/ev010/p0/b1': 'unselected_arm: blocked by capability:rock_smash; the walk takes the sibling arm (ruling 19)',
    'map066/ev010/p0/b2': 'unselected_arm: blocked by capability:rock_smash; the walk takes the sibling arm (ruling 19)',
    'map066/ev010/p0/b3': 'unselected_arm: the no-capability branch; the walk holds the capability and its smash beat answers YES (CH08 §9)',
    'map066/ev011/p0/b1': 'unselected_arm: blocked by capability:rock_smash; the walk takes the sibling arm (ruling 19)',
    'map066/ev011/p0/b2': 'unselected_arm: blocked by capability:rock_smash; the walk takes the sibling arm (ruling 19)',
    'map066/ev011/p0/b3': 'unselected_arm: the no-capability branch; the walk holds the capability and its smash beat answers YES (CH08 §9)',
    'map066/ev013/p0/b1': 'unselected_arm: blocked by capability:rock_smash; the walk takes the sibling arm (ruling 19)',
    'map066/ev013/p0/b2': 'unselected_arm: blocked by capability:rock_smash; the walk takes the sibling arm (ruling 19)',
    'map066/ev013/p0/b3': 'unselected_arm: the no-capability branch; the walk holds the capability and its smash beat answers YES (CH08 §9)',
    'map066/ev014/p0/b1': 'unselected_arm: blocked by capability:rock_smash; the walk takes the sibling arm (ruling 19)',
    'map066/ev014/p0/b2': 'unselected_arm: blocked by capability:rock_smash; the walk takes the sibling arm (ruling 19)',
    'map066/ev014/p0/b3': 'unselected_arm: the no-capability branch; the walk holds the capability and its smash beat answers YES (CH08 §9)',
    'map066/ev015/p0/b1': 'unselected_arm: blocked by capability:rock_smash; the walk takes the sibling arm (ruling 19)',
    'map066/ev015/p0/b2': 'unselected_arm: blocked by capability:rock_smash; the walk takes the sibling arm (ruling 19)',
    'map066/ev015/p0/b3': 'unselected_arm: the no-capability branch; the walk holds the capability and its smash beat answers YES (CH08 §9)',
    'map066/ev016/p0/b1': 'unselected_arm: blocked by capability:rock_smash; the walk takes the sibling arm (ruling 19)',
    'map066/ev016/p0/b2': 'unselected_arm: blocked by capability:rock_smash; the walk takes the sibling arm (ruling 19)',
    'map066/ev016/p0/b3': 'unselected_arm: the no-capability branch; the walk holds the capability and its smash beat answers YES (CH08 §9)',
    'map066/ev017/p0/b1': 'unselected_arm: blocked by capability:rock_smash; the walk takes the sibling arm (ruling 19)',
    'map066/ev017/p0/b2': 'unselected_arm: blocked by capability:rock_smash; the walk takes the sibling arm (ruling 19)',
    'map066/ev017/p0/b3': 'unselected_arm: the no-capability branch; the walk holds the capability and its smash beat answers YES (CH08 §9)',
    'map066/ev018/p0/b1': 'unselected_arm: blocked by capability:rock_smash; the walk takes the sibling arm (ruling 19)',
    'map066/ev018/p0/b2': 'unselected_arm: blocked by capability:rock_smash; the walk takes the sibling arm (ruling 19)',
    'map066/ev018/p0/b3': 'unselected_arm: the no-capability branch; the walk holds the capability and its smash beat answers YES (CH08 §9)',
    'map066/ev019/p0/b1': 'unselected_arm: blocked by capability:rock_smash; the walk takes the sibling arm (ruling 19)',
    'map066/ev019/p0/b2': 'unselected_arm: blocked by capability:rock_smash; the walk takes the sibling arm (ruling 19)',
    'map066/ev019/p0/b3': 'unselected_arm: the no-capability branch; the walk holds the capability and its smash beat answers YES (CH08 §9)',
    'map066/ev020/p0/b1': 'unselected_arm: blocked by capability:rock_smash; the walk takes the sibling arm (ruling 19)',
    'map066/ev020/p0/b2': 'unselected_arm: blocked by capability:rock_smash; the walk takes the sibling arm (ruling 19)',
    'map066/ev020/p0/b3': 'unselected_arm: the no-capability branch; the walk holds the capability and its smash beat answers YES (CH08 §9)',
    'map066/ev024/p0/b1': 'unselected_arm: blocked by harness:full_bag; the walk takes the sibling arm (ruling 19)',
    'map066/ev033/p0': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer)',
    'map066/ev033/p0/b0': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer)',
    'map066/ev033/p0/b1': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer)',
    'map066/ev034/p0': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer)',
    'map066/ev034/p0/b0': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer)',
    'map066/ev034/p0/b1': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer)',
    'map066/ev035/p0': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer)',
    'map066/ev035/p0/b0': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer)',
    'map066/ev035/p0/b1': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer)',
    'map066/ev036/p0': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer)',
    'map066/ev036/p0/b0': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer)',
    'map066/ev036/p0/b1': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer)',
    'map066/ev037/p0': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer)',
    'map066/ev037/p0/b0': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer)',
    'map066/ev037/p0/b1': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer)',
    'map066/ev038/p0': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer)',
    'map066/ev038/p0/b0': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer)',
    'map066/ev038/p0/b1': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer)',
    'map066/ev039/p0': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer)',
    'map066/ev039/p0/b0': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer)',
    'map066/ev039/p0/b1': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer)',
    'map066/ev040/p0': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer)',
    'map066/ev040/p0/b0': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer)',
    'map066/ev040/p0/b1': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer)',
    'map066/ev041/p0': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer)',
    'map066/ev041/p0/b0': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer)',
    'map066/ev041/p0/b1': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer)',
    'map066/ev042/p0': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer)',
    'map066/ev042/p0/b0': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer)',
    'map066/ev042/p0/b1': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer)',
    'map066/ev043/p0': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer)',
    'map066/ev043/p0/b0': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer)',
    'map066/ev043/p0/b1': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer)',
    'map066/ev044/p0': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer)',
    'map066/ev044/p0/b0': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer)',
    'map066/ev044/p0/b1': 'converter_dropped: converter drops it (blank_trigger1: blank graphic, player touch, no transfer)',
}

REFUSED: dict[str, str] = {
    'map002/ev001/p0/b1': 'story-state: undetermined -- story model could not determine this row',
    'map004/ev003/p1': 'story-state: unmodelled_predicate',
    'map004/ev003/p1/b0': 'story-state: unmodelled_predicate',
    'map004/ev003/p1/b1': 'story-state: unmodelled_predicate',
    'map060/ev007/p0/b0': "#109: text_unnormalizable -- code 101 @list[6]: unrecognized control code in fragments ['\\\\G\\\\bSo, you want the Mareep for \\\\v[2]?']",
    'map060/ev007/p0/b10': 'story-state: unmodelled_outcome:$Trainer.money',
    'map060/ev007/p0/b11': 'story-state: unmodelled_outcome:$Trainer.money',
    'map060/ev007/p0/b12': 'story-state: unmodelled_outcome:$Trainer.money',
    'map060/ev007/p0/b14': "#109: text_unnormalizable -- code 101 @list[58]: unrecognized control code in fragments ['\\\\G\\\\bSo, you want the Magikarp for \\\\v[2]?']",
    'map060/ev007/p0/b16': 'story-state: unmodelled_outcome:$Trainer.money',
    'map060/ev007/p0/b17': 'story-state: unmodelled_outcome:$Trainer.money',
    'map060/ev007/p0/b18': 'story-state: unmodelled_outcome:$Trainer.money',
    'map060/ev007/p0/b19': 'story-state: unmodelled_outcome:$Trainer.money',
    'map060/ev007/p0/b2': 'story-state: unmodelled_outcome:$Trainer.money',
    'map060/ev007/p0/b3': 'story-state: unmodelled_outcome:$Trainer.money',
    'map060/ev007/p0/b4': 'story-state: unmodelled_outcome:$Trainer.money',
    'map060/ev007/p0/b5': 'story-state: unmodelled_outcome:$Trainer.money',
    'map060/ev007/p0/b7': "#109: text_unnormalizable -- code 101 @list[32]: unrecognized control code in fragments ['\\\\G\\\\bSo, you want the Pahar for \\\\v[2]?']",
    'map060/ev007/p0/b9': 'story-state: unmodelled_outcome:$Trainer.money',
    'map060/ev008/p0': 'story-state: undetermined -- story model could not determine this row',
    'map060/ev009/p0': 'story-state: undetermined -- story model could not determine this row',
    'map060/ev015/p1': 'story-state: undetermined -- story model could not determine this row',
    'map060/ev020/p1': 'story-state: undetermined -- story model could not determine this row',
    'map060/ev042/p0/b0': 'C8: ruby_unknown_call:pbChooseNonEggPokemon',
    'map060/ev042/p0/b1': 'C8: ruby_unknown_call:pbChooseNonEggPokemon',
    'map060/ev042/p0/b10': 'C8: ruby_unknown_call:pbChooseNonEggPokemon',
    'map060/ev042/p0/b11': 'C8: ruby_unknown_call:pbChooseNonEggPokemon',
    'map060/ev042/p0/b12': 'C8: ruby_unknown_call:pbChooseNonEggPokemon',
    'map060/ev042/p0/b13': 'C8: ruby_unknown_call:pbChooseNonEggPokemon',
    'map060/ev042/p0/b14': 'C8: ruby_unknown_call:pbChooseNonEggPokemon',
    'map060/ev042/p0/b15': 'C8: ruby_unknown_call:pbChooseNonEggPokemon',
    'map060/ev042/p0/b16': 'C8: ruby_unknown_call:pbChooseNonEggPokemon',
    'map060/ev042/p0/b2': 'C8: ruby_unknown_call:pbChooseNonEggPokemon',
    'map060/ev042/p0/b3': 'C8: ruby_unknown_call:pbChooseNonEggPokemon',
    'map060/ev042/p0/b4': 'C8: ruby_unknown_call:pbChooseNonEggPokemon',
    'map060/ev042/p0/b5': 'C8: ruby_unknown_call:pbChooseNonEggPokemon',
    'map060/ev042/p0/b6': 'C8: ruby_unknown_call:pbChooseNonEggPokemon',
    'map060/ev042/p0/b7': 'C8: ruby_unknown_call:pbChooseNonEggPokemon',
    'map060/ev042/p0/b8': 'C8: ruby_unknown_call:pbChooseNonEggPokemon',
    'map060/ev042/p0/b9': 'C8: ruby_unknown_call:pbChooseNonEggPokemon',
    'map066/ev021/p1': "cell: cell_error -- approach_to: MAP_BUROLE_TOWN_GYM event 21 (cell (17, 38)) has no walkable adjacent cell on any side -- this event cannot be approached at all under the offline graph's collision data",
}

CHAPTER = ch10.build()
