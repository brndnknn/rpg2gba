"""GENERATED -- do not edit.

Chapter CH03. Regenerate with `python -m rpg2gba.beat_gen generate --chapter CH03`.
"""

from __future__ import annotations

from rpg2gba.playtest.archetypes.arrival_nudge import arrival_nudge_beat
from rpg2gba.playtest.archetypes.escort import escort_beat
from rpg2gba.playtest.archetypes.flavour_npc import flavour_npc_beat
from rpg2gba.playtest.archetypes.generic import generic_beat, obstacle_beat, seam_beat, stair_beat, transit_beat
from rpg2gba.playtest.archetypes.item_ball import item_ball_beats
from rpg2gba.playtest.archetypes.warp import warp_beat
from rpg2gba.playtest.chapter import ChapterBuilder
from rpg2gba.playtest.whiteout import whiteout_fork_beat

ch03 = ChapterBuilder('CH03', doc='beat_gen-generated module for CH03', predecessor='CH02', suite='gen')

warp_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m033e046_warp',
    group='m033e046_warp',
    dest_map_constant='MAP_KEVLAR_TOWN',
    direction='UP',
    end_side='origin',
    event_id=46,
    manifest_chapter_id='CH02',
    map_constant='MAP_ROUTE_01',
    map_id=33,
    mechanism='threshold',
    return_direction='DOWN',
    start_side='origin',
)

warp_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m033e045_warp',
    group='m033e045_warp',
    dest_map_constant='MAP_KEVLAR_TOWN',
    direction='UP',
    end_side='dest',
    event_id=45,
    manifest_chapter_id='CH02',
    map_constant='MAP_ROUTE_01',
    map_id=33,
    mechanism='threshold',
    start_side='origin',
)

warp_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m031e023_warp',
    group='m031e023_warp',
    dest_map_constant='MAP_ROUTE_01',
    direction='DOWN',
    end_side='origin',
    event_id=23,
    map_constant='MAP_KEVLAR_TOWN',
    map_id=31,
    mechanism='threshold',
    return_direction='UP',
    start_side='origin',
)

warp_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m031e035_warp',
    group='m031e035_warp',
    dest_map_constant='MAP_ROUTE_01',
    direction='DOWN',
    end_side='origin',
    event_id=35,
    map_constant='MAP_KEVLAR_TOWN',
    map_id=31,
    mechanism='threshold',
    return_direction='UP',
    start_side='origin',
)

flavour_npc_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m031e048p0_flavour_npc',
    group='m031e048p0_flavour_npc',
    approach_prefer='north',
    event_id=48,
    map_constant='MAP_KEVLAR_TOWN',
    map_id=31,
    toggled_page_idx=None,
    variant='toggling',
)

flavour_npc_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m031e048p1_flavour_npc',
    group='m031e048p1_flavour_npc',
    approach_prefer='north',
    event_id=48,
    map_constant='MAP_KEVLAR_TOWN',
    map_id=31,
    page_idx=1,
    toggled_page_idx=None,
    variant='toggling',
)

warp_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m031e041_warp',
    group='m031e041_warp',
    dest_map_constant='MAP_KEVLAR_TOWN_BUILDINGS',
    direction='UP',
    end_side='dest',
    event_id=41,
    map_constant='MAP_KEVLAR_TOWN',
    map_id=31,
    mechanism='threshold',
    start_side='origin',
)

flavour_npc_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m073e010_flavour_npc',
    group='m073e010_flavour_npc',
    approach_prefer='west',
    event_id=10,
    map_constant='MAP_KEVLAR_TOWN_BUILDINGS',
    map_id=73,
    variant='plain',
)

flavour_npc_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m073e011_flavour_npc',
    group='m073e011_flavour_npc',
    approach_prefer='south',
    event_id=11,
    map_constant='MAP_KEVLAR_TOWN_BUILDINGS',
    map_id=73,
    variant='plain',
)

warp_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m073e009_warp',
    group='m073e009_warp',
    dest_map_constant='MAP_KEVLAR_TOWN',
    direction='DOWN',
    end_side='dest',
    event_id=9,
    map_constant='MAP_KEVLAR_TOWN_BUILDINGS',
    map_id=73,
    mechanism='threshold',
    start_side='origin',
)

arrival_nudge_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m031e041_arrival_nudge',
    group='m031e041_arrival_nudge',
    event_id=41,
    from_event_id=9,
    from_map_constant='MAP_KEVLAR_TOWN_BUILDINGS',
    map_constant='MAP_KEVLAR_TOWN',
    map_id=31,
)

generic_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m031e041_arrival_nudge_arms',
    group='m031e041_arrival_nudge',
    rows=('map031/ev041/p1/b0',),
    skip_claimed=True,
)

warp_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m031e013_warp',
    group='m031e013_warp',
    dest_map_constant='MAP_KEVLAR_TOWN_BUILDINGS',
    direction='UP',
    end_side='dest',
    event_id=13,
    map_constant='MAP_KEVLAR_TOWN',
    map_id=31,
    mechanism='threshold',
    start_side='origin',
)

warp_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m073e004_warp',
    group='m073e004_warp',
    dest_map_constant='MAP_KEVLAR_TOWN',
    direction='DOWN',
    end_side='dest',
    event_id=4,
    map_constant='MAP_KEVLAR_TOWN_BUILDINGS',
    map_id=73,
    mechanism='threshold',
    start_side='origin',
)

arrival_nudge_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m031e013_arrival_nudge',
    group='m031e013_arrival_nudge',
    event_id=13,
    from_event_id=4,
    from_map_constant='MAP_KEVLAR_TOWN_BUILDINGS',
    map_constant='MAP_KEVLAR_TOWN',
    map_id=31,
)

generic_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m031e013_arrival_nudge_arms',
    group='m031e013_arrival_nudge',
    rows=('map031/ev013/p1/b0',),
    skip_claimed=True,
)

flavour_npc_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m031e010_flavour_npc',
    group='m031e010_flavour_npc',
    approach_prefer='east',
    event_id=10,
    map_constant='MAP_KEVLAR_TOWN',
    map_id=31,
    variant='plain',
)

warp_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m031e012_warp',
    group='m031e012_warp',
    dest_map_constant='MAP_KEVLAR_TOWN_BUILDINGS',
    direction='UP',
    end_side='dest',
    event_id=12,
    map_constant='MAP_KEVLAR_TOWN',
    map_id=31,
    mechanism='threshold',
    start_side='origin',
)

generic_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m073e001p0',
    group='m073e001p0',
    rows=('map073/ev001/p0',),
    approach_prefer='east',
)

warp_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m073e002_warp',
    group='m073e002_warp',
    dest_map_constant='MAP_KEVLAR_TOWN',
    direction='DOWN',
    end_side='dest',
    event_id=2,
    map_constant='MAP_KEVLAR_TOWN_BUILDINGS',
    map_id=73,
    mechanism='threshold',
    start_side='origin',
)

arrival_nudge_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m031e012_arrival_nudge',
    group='m031e012_arrival_nudge',
    event_id=12,
    from_event_id=2,
    from_map_constant='MAP_KEVLAR_TOWN_BUILDINGS',
    map_constant='MAP_KEVLAR_TOWN',
    map_id=31,
)

generic_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m031e012_arrival_nudge_arms',
    group='m031e012_arrival_nudge',
    rows=('map031/ev012/p1/b0',),
    skip_claimed=True,
)

flavour_npc_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m031e040_flavour_npc',
    group='m031e040_flavour_npc',
    approach_prefer='south',
    event_id=40,
    map_constant='MAP_KEVLAR_TOWN',
    map_id=31,
    variant='plain',
)

flavour_npc_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m031e009_flavour_npc',
    group='m031e009_flavour_npc',
    approach_prefer='east',
    event_id=9,
    map_constant='MAP_KEVLAR_TOWN',
    map_id=31,
    variant='plain',
)

generic_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m031e008p0',
    group='m031e008p0',
    rows=('map031/ev008/p0', 'map031/ev008/p0/b0', 'map031/ev008/p0/b1', 'map031/ev008/p0/b2', 'map031/ev008/p0/b3'),
    approach_prefer='east',
    archetype=(('map031/ev008/p0', 'flavour_npc'),),
    random_arms=(('map031/ev008/p0/b0', ((102, '==', 0),)), ('map031/ev008/p0/b1', ((102, '!=', 0),)), ('map031/ev008/p0/b2', ((102, '==', 1),)), ('map031/ev008/p0/b3', ((102, '!=', 1),))),
)

generic_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m031e014p0_c3a0',
    group='m031e014p0',
    rows=('map031/ev014/p0/b0',),
    approach_prefer='south',
    choice_answers=((3, 0),),
    walk_rows=('map031/ev014/p0',),
)

generic_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m031e014p0',
    group='m031e014p0',
    rows=('map031/ev014/p0', 'map031/ev014/p0/b1', 'map031/ev014/p0/b3'),
    approach_prefer='south',
    choice_answers=((3, 1),),
)

flavour_npc_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m031e019_flavour_npc',
    group='m031e019_flavour_npc',
    approach_prefer='south',
    event_id=19,
    map_constant='MAP_KEVLAR_TOWN',
    map_id=31,
    variant='plain',
)

flavour_npc_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m031e039_flavour_npc',
    group='m031e039_flavour_npc',
    approach_prefer='north',
    event_id=39,
    map_constant='MAP_KEVLAR_TOWN',
    map_id=31,
    variant='plain',
)

warp_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m031e002_warp',
    group='m031e002_warp',
    dest_map_constant='MAP_KEVLAR_TOWN_POKEMART',
    direction='UP',
    end_side='dest',
    event_id=2,
    map_constant='MAP_KEVLAR_TOWN',
    map_id=31,
    mechanism='threshold',
    start_side='origin',
)

generic_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m067e001p0',
    group='m067e001p0',
    rows=('map067/ev001/p0',),
    approach_prefer='south',
)

generic_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m067e009p0',
    group='m067e009p0',
    rows=('map067/ev009/p0',),
    approach_prefer='east',
)

generic_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m067e004p0',
    group='m067e004p0',
    rows=('map067/ev004/p0', 'map067/ev004/p0/b0', 'map067/ev004/p0/b1'),
    approach_prefer='west',
    random_arms=(('map067/ev004/p0/b0', ((102, '==', 1),)), ('map067/ev004/p0/b1', ((102, '!=', 1),))),
)

flavour_npc_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m067e008_flavour_npc',
    group='m067e008_flavour_npc',
    approach_prefer='south',
    event_id=8,
    map_constant='MAP_KEVLAR_TOWN_POKEMART',
    map_id=67,
    variant='plain',
)

flavour_npc_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m067e006_flavour_npc',
    group='m067e006_flavour_npc',
    approach_prefer='south',
    event_id=6,
    map_constant='MAP_KEVLAR_TOWN_POKEMART',
    map_id=67,
    variant='plain',
)

flavour_npc_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m067e007_flavour_npc',
    group='m067e007_flavour_npc',
    approach_prefer='south',
    event_id=7,
    map_constant='MAP_KEVLAR_TOWN_POKEMART',
    map_id=67,
    variant='plain',
)

warp_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m067e002_warp',
    group='m067e002_warp',
    dest_map_constant='MAP_KEVLAR_TOWN',
    direction='DOWN',
    end_side='dest',
    event_id=2,
    map_constant='MAP_KEVLAR_TOWN_POKEMART',
    map_id=67,
    mechanism='threshold',
    start_side='origin',
)

arrival_nudge_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m031e002_arrival_nudge',
    group='m031e002_arrival_nudge',
    event_id=2,
    from_event_id=2,
    from_map_constant='MAP_KEVLAR_TOWN_POKEMART',
    map_constant='MAP_KEVLAR_TOWN',
    map_id=31,
)

generic_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m031e002_arrival_nudge_arms',
    group='m031e002_arrival_nudge',
    rows=('map031/ev002/p1/b0',),
    skip_claimed=True,
)

flavour_npc_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m031e007_flavour_npc',
    group='m031e007_flavour_npc',
    approach_prefer='west',
    event_id=7,
    map_constant='MAP_KEVLAR_TOWN',
    map_id=31,
    moved_by=('map031/ev007/p1',),
    variant='plain',
)

stair_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m031stair25x16',
    group='m031stair25x16',
    rows=('map031/terrain/stairs/25,16', 'map031/terrain/stairs/25,17', 'map031/terrain/stairs/25,18'),
    approach_prefer='east',
)

generic_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m031e006p0',
    group='m031e006p0',
    rows=('map031/ev006/p0', 'map031/ev006/p0/b0', 'map031/ev006/p0/b1', 'map031/ev006/p0/b2', 'map031/ev006/p0/b3', 'map031/ev006/p0/b4', 'map031/ev006/p0/b5'),
    approach_prefer='north',
    random_arms=(('map031/ev006/p0/b0', ((102, '==', 0),)), ('map031/ev006/p0/b1', ((102, '!=', 0),)), ('map031/ev006/p0/b2', ((102, '==', 1),)), ('map031/ev006/p0/b3', ((102, '!=', 1),)), ('map031/ev006/p0/b4', ((102, '==', 2),)), ('map031/ev006/p0/b5', ((102, '!=', 2),))),
)

warp_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m031e003_warp',
    group='m031e003_warp',
    dest_map_constant='MAP_KEVLAR_TOWN_POKEMON_CENTER',
    direction='UP',
    end_side='dest',
    event_id=3,
    map_constant='MAP_KEVLAR_TOWN',
    map_id=31,
    mechanism='threshold',
    start_side='origin',
)

flavour_npc_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m068e010_flavour_npc',
    group='m068e010_flavour_npc',
    approach_prefer='west',
    event_id=10,
    map_constant='MAP_KEVLAR_TOWN_POKEMON_CENTER',
    map_id=68,
    variant='plain',
)

generic_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m068e007p0',
    group='m068e007p0',
    rows=('map068/ev007/p0',),
    approach_prefer='south',
)

generic_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m068e001p0_c5a0',
    group='m068e001p0',
    rows=('map068/ev001/p0/b0', 'map068/ev001/p0/b2'),
    approach_prefer='south',
    choice_answers=((5, 0),),
    walk_rows=('map068/ev001/p0',),
)

generic_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m068e001p0',
    group='m068e001p0',
    rows=('map068/ev001/p0', 'map068/ev001/p0/b3'),
    approach_prefer='south',
    choice_answers=((5, 1),),
)

whiteout_fork_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m068_whiteout',
    group='m068e001p0',
    rows=('map068/ev001/p1',),
    heal_location_id='HEAL_LOCATION_KEVLAR_TOWN_POKEMON_CENTER',
)

generic_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m068e012p0',
    group='m068e012p0',
    rows=('map068/ev012/p0',),
    approach_prefer='south',
)

generic_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m068e004p0',
    group='m068e004p0',
    rows=('map068/ev004/p0', 'map068/ev004/p0/b0', 'map068/ev004/p0/b1', 'map068/ev004/p0/b2', 'map068/ev004/p0/b3', 'map068/ev004/p0/b4', 'map068/ev004/p0/b5'),
    approach_prefer='north',
    random_arms=(('map068/ev004/p0/b0', ((102, '==', 0),)), ('map068/ev004/p0/b1', ((102, '!=', 0),)), ('map068/ev004/p0/b2', ((102, '==', 1),)), ('map068/ev004/p0/b3', ((102, '!=', 1),)), ('map068/ev004/p0/b4', ((102, '==', 2),)), ('map068/ev004/p0/b5', ((102, '!=', 2),))),
)

generic_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m068e003p0_c3a0',
    group='m068e003p0',
    rows=('map068/ev003/p0/b0',),
    approach_prefer='north',
    choice_answers=((3, 0),),
    walk_rows=('map068/ev003/p0',),
)

generic_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m068e003p0_c3a1',
    group='m068e003p0',
    rows=('map068/ev003/p0/b1',),
    approach_prefer='north',
    choice_answers=((3, 1),),
    walk_rows=('map068/ev003/p0',),
)

generic_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m068e003p0',
    group='m068e003p0',
    rows=('map068/ev003/p0', 'map068/ev003/p0/b2'),
    approach_prefer='north',
    choice_answers=((3, 2),),
)

item_ball_beats(
    ch03,
    chapter_id='CH03',
    beat_prefix='m068e018_item_ball',
    group='m068e018_item_ball',
    approach_prefer='north',
    event_id=18,
    item='ITEM_ANTIDOTE',
    map_constant='MAP_KEVLAR_TOWN_POKEMON_CENTER',
    map_id=68,
    negative_beat=False,
    self_switch_letter='A',
)

generic_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m068e018_item_ball_arms',
    group='m068e018_item_ball',
    rows=('map068/ev018/p0/b0',),
    approach_prefer='north',
    skip_claimed=True,
)

generic_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m068e013p0',
    group='m068e013p0',
    rows=('map068/ev013/p0',),
    approach_prefer='south',
)

generic_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m068e011p0',
    group='m068e011p0',
    rows=('map068/ev011/p0',),
    approach_prefer='south',
)

generic_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m068e009p0',
    group='m068e009p0',
    rows=('map068/ev009/p0',),
    approach_prefer='south',
)

generic_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m068e014p0_c4a0',
    group='m068e014p0',
    rows=('map068/ev014/p0/b0', 'map068/ev014/p0/b1'),
    approach_prefer='north',
    archetype=(('map068/ev014/p0', 'trainer'),),
    choice_answers=((4, 0),),
    walk_rows=('map068/ev014/p0',),
)

generic_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m068e014p0',
    group='m068e014p0',
    rows=('map068/ev014/p0', 'map068/ev014/p0/b3'),
    approach_prefer='north',
    archetype=(('map068/ev014/p0', 'trainer'),),
    choice_answers=((4, 1),),
)

warp_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m068e002_warp',
    group='m068e002_warp',
    dest_map_constant='MAP_KEVLAR_TOWN',
    direction='DOWN',
    end_side='dest',
    event_id=2,
    map_constant='MAP_KEVLAR_TOWN_POKEMON_CENTER',
    map_id=68,
    mechanism='threshold',
    start_side='origin',
)

arrival_nudge_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m031e003_arrival_nudge',
    group='m031e003_arrival_nudge',
    event_id=3,
    from_event_id=2,
    from_map_constant='MAP_KEVLAR_TOWN_POKEMON_CENTER',
    map_constant='MAP_KEVLAR_TOWN',
    map_id=31,
)

generic_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m031e003_arrival_nudge_arms',
    group='m031e003_arrival_nudge',
    rows=('map031/ev003/p1/b0',),
    skip_claimed=True,
)

transit_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m068e008_warp_transit',
    group='m068e008_warp',
    hops=(('MAP_KEVLAR_TOWN', 20, 13, 'UP', 'MAP_KEVLAR_TOWN_POKEMON_CENTER'),),
)

warp_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m068e008_warp',
    group='m068e008_warp',
    dest_map_constant='MAP_KEVLAR_TOWN',
    direction='DOWN',
    end_side='dest',
    event_id=8,
    map_constant='MAP_KEVLAR_TOWN_POKEMON_CENTER',
    map_id=68,
    mechanism='threshold',
    start_side='origin',
)

escort_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m031e049_escort',
    group='m031e049_escort',
    rows=('map031/ev049/p0', 'map031/ev049/p0/b1', 'map031/ev049/p0/b3'),
    approach_prefer='west',
    dest_map_constant='MAP_KEVLAR_TOWN_POKEMON_CENTER',
    event_id=49,
    map_constant='MAP_KEVLAR_TOWN',
    map_id=31,
)

transit_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m031e049p1_transit',
    group='m031e049p1',
    hops=(('MAP_KEVLAR_TOWN_POKEMON_CENTER', 7, 18, 'DOWN', 'MAP_KEVLAR_TOWN'),),
)

generic_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m031e049p1',
    group='m031e049p1',
    rows=('map031/ev049/p1',),
    approach_prefer='west',
)

transit_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m068e015p0_transit',
    group='m068e015p0',
    hops=(('MAP_KEVLAR_TOWN', 20, 13, 'UP', 'MAP_KEVLAR_TOWN_POKEMON_CENTER'),),
)

generic_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m068e015p0',
    group='m068e015p0',
    rows=('map068/ev015/p0', 'map068/ev015/p0/b2'),
    approach_prefer='arrive@(8,18)',
)

generic_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m068e015p1',
    group='m068e015p1',
    rows=('map068/ev015/p1',),
    approach_prefer='north',
)

flavour_npc_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m068e017_flavour_npc',
    group='m068e017_flavour_npc',
    approach_prefer='south',
    event_id=17,
    map_constant='MAP_KEVLAR_TOWN_POKEMON_CENTER',
    map_id=68,
    variant='plain',
)

transit_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m031obstacle_strength_transit',
    group='m031obstacle_strength',
    hops=(('MAP_KEVLAR_TOWN_POKEMON_CENTER', 7, 18, 'DOWN', 'MAP_KEVLAR_TOWN'),),
)

obstacle_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m031obstacle_strength',
    group='m031obstacle_strength',
    rows=('map031/ev001/p0', 'map031/ev037/p0'),
    approach_prefer='south',
    capability='strength',
)

generic_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m031e042p0',
    group='m031e042p0',
    rows=('map031/ev042/p0', 'map031/ev042/p0/b0'),
    approach_prefer='south',
)

generic_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m031e042p1',
    group='m031e042p1',
    rows=('map031/ev042/p1',),
    approach_prefer='south',
)

warp_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m031e004_warp',
    group='m031e004_warp',
    dest_map_constant='MAP_KEVLAR_TOWN_BUILDINGS',
    direction='UP',
    end_side='dest',
    event_id=4,
    map_constant='MAP_KEVLAR_TOWN',
    map_id=31,
    mechanism='threshold',
    start_side='origin',
)

flavour_npc_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m073e008_flavour_npc',
    group='m073e008_flavour_npc',
    approach_prefer='east',
    event_id=8,
    map_constant='MAP_KEVLAR_TOWN_BUILDINGS',
    map_id=73,
    variant='plain',
)

generic_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m073e006p0',
    group='m073e006p0',
    rows=('map073/ev006/p0',),
    approach_prefer='south',
)

generic_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m073e006p1',
    group='m073e006p1',
    rows=('map073/ev006/p1', 'map073/ev006/p1/b0'),
    approach_prefer='south',
)

generic_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m073e006p1_r1',
    group='m073e006p1',
    rows=('map073/ev006/p1/b1',),
    approach_prefer='south',
    walk_rows=('map073/ev006/p1',),
)

warp_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m073e007_warp',
    group='m073e007_warp',
    dest_map_constant='MAP_KEVLAR_TOWN',
    direction='DOWN',
    end_side='dest',
    event_id=7,
    map_constant='MAP_KEVLAR_TOWN_BUILDINGS',
    map_id=73,
    mechanism='threshold',
    start_side='origin',
)

arrival_nudge_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m031e004_arrival_nudge',
    group='m031e004_arrival_nudge',
    event_id=4,
    from_event_id=7,
    from_map_constant='MAP_KEVLAR_TOWN_BUILDINGS',
    map_constant='MAP_KEVLAR_TOWN',
    map_id=31,
)

generic_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m031e004_arrival_nudge_arms',
    group='m031e004_arrival_nudge',
    rows=('map031/ev004/p1/b0',),
    skip_claimed=True,
)

generic_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m031e045p0',
    group='m031e045p0',
    rows=('map031/ev045/p0', 'map031/ev045/p0/b0'),
    approach_prefer='north',
)

generic_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m031e045p1',
    group='m031e045p1',
    rows=('map031/ev045/p1',),
    approach_prefer='north',
)

generic_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m031e044p0',
    group='m031e044p0',
    rows=('map031/ev044/p0', 'map031/ev044/p0/b0'),
    approach_prefer='north',
)

generic_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m031e044p1',
    group='m031e044p1',
    rows=('map031/ev044/p1',),
    approach_prefer='north',
)

generic_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m031e046p0',
    group='m031e046p0',
    rows=('map031/ev046/p0',),
    approach_prefer='north',
)

generic_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m031e043p0',
    group='m031e043p0',
    rows=('map031/ev043/p0',),
    approach_prefer='north',
)

seam_beat(
    ch03,
    chapter_id='CH03',
    beat_name='m031seamN035',
    group='m031seamN035',
    rows=('map031/seam/N/map035',),
    approach_prefer='UP@(32,0)',
)

NEVER_FIRES: dict[str, str] = {
    'map031/ev023/p1': "archetype_kwargs: map031/ev023/p1: no warp lands on this arrival autorun's cell (15,43) on map 31 -- it never fires",
    'map031/ev023/p1/b0': "archetype_kwargs: map031/ev023/p1: no warp lands on this arrival autorun's cell (15,43) on map 31 -- it never fires",
    'map031/ev023/p1/b1': "archetype_kwargs: map031/ev023/p1: no warp lands on this arrival autorun's cell (15,43) on map 31 -- it never fires",
    'map031/ev035/p1': "archetype_kwargs: map031/ev035/p1: no warp lands on this arrival autorun's cell (16,43) on map 31 -- it never fires",
    'map031/ev035/p1/b0': "archetype_kwargs: map031/ev035/p1: no warp lands on this arrival autorun's cell (16,43) on map 31 -- it never fires",
    'map031/ev035/p1/b1': "archetype_kwargs: map031/ev035/p1: no warp lands on this arrival autorun's cell (16,43) on map 31 -- it never fires",
    'map033/ev045/p1': "archetype_kwargs: map033/ev045/p1: no warp lands on this arrival autorun's cell (15,5) on map 33 -- it never fires",
    'map033/ev045/p1/b0': "archetype_kwargs: map033/ev045/p1: no warp lands on this arrival autorun's cell (15,5) on map 33 -- it never fires",
    'map033/ev045/p1/b1': "archetype_kwargs: map033/ev045/p1: no warp lands on this arrival autorun's cell (15,5) on map 33 -- it never fires",
    'map033/ev046/p1': "archetype_kwargs: map033/ev046/p1: no warp lands on this arrival autorun's cell (16,5) on map 33 -- it never fires",
    'map033/ev046/p1/b0': "archetype_kwargs: map033/ev046/p1: no warp lands on this arrival autorun's cell (16,5) on map 33 -- it never fires",
    'map033/ev046/p1/b1': "archetype_kwargs: map033/ev046/p1: no warp lands on this arrival autorun's cell (16,5) on map 33 -- it never fires",
    'map067/ev003/p0': 'map067/ev003/p0: its event on counter cell (10, 8) is no object event, and pokeemerald reaches across the counter to an object first from every side (south (10, 9) -> object at (10, 7)) -- it never fires on the ROM',
    'map068/ev012/p1': "archetype_kwargs: map068/ev012/p1: no warp lands on this arrival autorun's cell (7,12) on map 68 -- it never fires",
    'map068/ev012/p1/b0': "archetype_kwargs: map068/ev012/p1: no warp lands on this arrival autorun's cell (7,12) on map 68 -- it never fires",
    'map068/ev012/p1/b1': "archetype_kwargs: map068/ev012/p1: no warp lands on this arrival autorun's cell (7,12) on map 68 -- it never fires",
    'map073/ev005/p1': "map073/ev005/p1 (needs switch 100 == True) is not its event's live page at this route position: switch 100 == True fails: switch 100 is [False] (seed state), never written on the route; the rows that could write it none are not walked before it; live page: no page is certainly live",
    'map073/ev005/p2': "map073/ev005/p2 (needs self switch A == True) is not its event's live page at this route position: self switch A == True fails: self switch A is [False] (seed state), never written on the route; the rows that could write it ['map073/ev005/p1'] are not walked before it; live page: no page is certainly live",
}

EMPTY_PAGES: dict[str, str] = {
    'map031/ev031/p0': 'every page of the event is empty; nothing to check on the ROM',
    'map031/ev036/p0': 'every page of the event is empty; nothing to check on the ROM',
    'map067/ev005/p0': 'every page of the event is empty; nothing to check on the ROM',
    'map068/ev005/p0': 'every page of the event is empty; nothing to check on the ROM',
    'map068/ev005/p1': 'every page of the event is empty; nothing to check on the ROM',
    'map068/ev005/p2': 'every page of the event is empty; nothing to check on the ROM',
    'map068/ev005/p3': 'every page of the event is empty; nothing to check on the ROM',
    'map068/ev005/p4': 'every page of the event is empty; nothing to check on the ROM',
    'map068/ev005/p5': 'every page of the event is empty; nothing to check on the ROM',
    'map068/ev005/p6': 'every page of the event is empty; nothing to check on the ROM',
    'map068/ev006/p0': 'every page of the event is empty; nothing to check on the ROM',
    'map068/ev006/p1': 'every page of the event is empty; nothing to check on the ROM',
    'map068/ev006/p2': 'every page of the event is empty; nothing to check on the ROM',
    'map068/ev006/p3': 'every page of the event is empty; nothing to check on the ROM',
    'map068/ev006/p4': 'every page of the event is empty; nothing to check on the ROM',
    'map068/ev006/p5': 'every page of the event is empty; nothing to check on the ROM',
    'map068/ev006/p6': 'every page of the event is empty; nothing to check on the ROM',
    'map068/ev016/p0': 'every page of the event is empty; nothing to check on the ROM',
    'map068/ev016/p1': 'every page of the event is empty; nothing to check on the ROM',
}

WALK_CHECKED: dict[str, str] = {
    'map031/ev006/p0/b0': 'arm on a rolled or computed value (var 102 == 0); the walk checks whichever fires',
    'map031/ev006/p0/b1': 'arm on a rolled or computed value (var 102 != 0); the walk checks whichever fires',
    'map031/ev006/p0/b2': 'arm on a rolled or computed value (var 102 == 1); the walk checks whichever fires',
    'map031/ev006/p0/b3': 'arm on a rolled or computed value (var 102 != 1); the walk checks whichever fires',
    'map031/ev006/p0/b4': 'arm on a rolled or computed value (var 102 == 2); the walk checks whichever fires',
    'map031/ev006/p0/b5': 'arm on a rolled or computed value (var 102 != 2); the walk checks whichever fires',
    'map031/ev008/p0/b0': 'arm on a rolled or computed value (var 102 == 0); the walk checks whichever fires',
    'map031/ev008/p0/b1': 'arm on a rolled or computed value (var 102 != 0); the walk checks whichever fires',
    'map031/ev008/p0/b2': 'arm on a rolled or computed value (var 102 == 1); the walk checks whichever fires',
    'map031/ev008/p0/b3': 'arm on a rolled or computed value (var 102 != 1); the walk checks whichever fires',
    'map067/ev004/p0/b0': 'arm on a rolled or computed value (var 102 == 1); the walk checks whichever fires',
    'map067/ev004/p0/b1': 'arm on a rolled or computed value (var 102 != 1); the walk checks whichever fires',
    'map068/ev004/p0/b0': 'arm on a rolled or computed value (var 102 == 0); the walk checks whichever fires',
    'map068/ev004/p0/b1': 'arm on a rolled or computed value (var 102 != 0); the walk checks whichever fires',
    'map068/ev004/p0/b2': 'arm on a rolled or computed value (var 102 == 1); the walk checks whichever fires',
    'map068/ev004/p0/b3': 'arm on a rolled or computed value (var 102 != 1); the walk checks whichever fires',
    'map068/ev004/p0/b4': 'arm on a rolled or computed value (var 102 == 2); the walk checks whichever fires',
    'map068/ev004/p0/b5': 'arm on a rolled or computed value (var 102 != 2); the walk checks whichever fires',
}

ELSEWHERE: dict[str, str] = {
    'map019/ev001/p0': 'later',
    'map019/ev002/p0': 'later',
    'map019/ev003/p0': 'later',
    'map019/ev004/p0': 'later',
    'map019/ev004/p0/b0': 'later',
    'map019/ev004/p0/b1': 'unselected_arm: blocked by fork:whiteout; the walk takes the sibling arm (ruling 19)',
    'map019/ev004/p1': 'later',
    'map019/ev004/p2': 'later',
    'map019/ev006/p0/b0': 'unreachable',
    'map019/ev006/p0/b1': 'unreachable',
    'map019/ev006/p0/b2': 'unreachable',
    'map019/ev007/p0': 'later',
    'map031/ev002/p1/b1': 'unselected_arm: not taken on the walk: else of `get_character(0).onEvent?` from cell (37, 14) (event at (37, 14)) (ruling 19)',
    'map031/ev003/p1/b1': 'unselected_arm: not taken on the walk: else of `get_character(0).onEvent?` from cell (20, 12) (event at (20, 12)) (ruling 19)',
    'map031/ev004/p1/b1': 'unselected_arm: not taken on the walk: else of `get_character(0).onEvent?` from cell (35, 6) (event at (35, 6)) (ruling 19)',
    'map031/ev007/p1': 'unreachable',
    'map031/ev007/p1/b0': 'unreachable',
    'map031/ev007/p1/b1': 'unreachable',
    'map031/ev007/p2': 'unreachable',
    'map031/ev011/p0': 'stripped: strip_list.json map_events (Luz)',
    'map031/ev012/p1/b1': 'unselected_arm: not taken on the walk: else of `get_character(0).onEvent?` from cell (23, 28) (event at (23, 28)) (ruling 19)',
    'map031/ev013/p1/b1': 'unselected_arm: not taken on the walk: else of `get_character(0).onEvent?` from cell (37, 28) (event at (37, 28)) (ruling 19)',
    'map031/ev014/p0/b2': 'unselected_arm: not taken on the walk: needs var 200 == 99, and here var 200 is [0] (ruling 19)',
    'map031/ev017/p0': 'stripped: strip_list.json map_events (Luz)',
    'map031/ev028/p0': 'stripped: strip_list.json map_events (Luz)',
    'map031/ev029/p0': 'stripped: strip_list.json map_events (Luz)',
    'map031/ev030/p0': 'stripped: strip_list.json map_events (Luz)',
    'map031/ev032/p0': 'stripped: strip_list.json map_events (Luz)',
    'map031/ev033/p0': 'stripped: strip_list.json map_events (Luz)',
    'map031/ev034/p0': 'later',
    'map031/ev034/p1': 'later',
    'map031/ev034/p1/b0': 'later',
    'map031/ev034/p1/b1': 'later',
    'map031/ev041/p1/b1': 'unselected_arm: not taken on the walk: else of `get_character(0).onEvent?` from cell (32, 28) (event at (32, 28)) (ruling 19)',
    'map031/ev042/p0/b1': 'unselected_arm: not taken on the walk: else of `pbPickBerry(PBItems::PECHABERRY,1)` from cell (32, 6) (event at (32, 5)) (ruling 19)',
    'map031/ev044/p0/b1': 'unselected_arm: not taken on the walk: else of `pbPickBerry(PBItems::ORANBERRY,2)` from cell (34, 9) (event at (34, 10)) (ruling 19)',
    'map031/ev045/p0/b1': 'unselected_arm: not taken on the walk: else of `pbPickBerry(PBItems::ORANBERRY,2)` from cell (35, 9) (event at (35, 10)) (ruling 19)',
    'map031/ev049/p0/b0': 'unselected_arm: not taken on the walk: the player facing up, fired from cell (20, 13) (event at (21, 13)) (ruling 19)',
    'map031/ev049/p0/b2': 'unselected_arm: not taken on the walk: the player facing up, fired from cell (20, 13) (event at (21, 13)) (ruling 19)',
    'map031/ev049/p2': 'unreachable',
    'map031/ev050/p0': 'unreachable',
    'map031/ev050/p1': 'unreachable',
    'map068/ev001/p0/b1': 'unreachable',
    'map068/ev014/p0/b2': 'unselected_arm: blocked by fork:whiteout; the walk takes the sibling arm (ruling 19)',
    'map068/ev015/p0/b3': 'unselected_arm: blocked by harness:full_bag; the walk takes the sibling arm (ruling 19)',
    'map068/ev018/p0/b1': 'unselected_arm: blocked by harness:full_bag; the walk takes the sibling arm (ruling 19)',
    'map073/ev001/p0/b0': 'unreachable',
    'map073/ev001/p1': 'unreachable',
    'map073/ev003/p0': 'unreachable',
    'map073/ev003/p0/b0': 'unreachable',
    'map073/ev003/p0/b1': 'unreachable',
    'map073/ev003/p0/b2': 'unreachable',
    'map073/ev003/p0/b3': 'unreachable',
    'map073/ev005/p0': 'unreachable',
    'map073/ev006/p2': 'unreachable',
}

REFUSED: dict[str, str] = {
    'map067/ev009/p1': 'story-state: unmodelled_predicate',
    'map067/ev009/p1/b0': 'story-state: unmodelled_predicate',
    'map067/ev009/p1/b1': 'story-state: unmodelled_predicate',
    'map068/ev015/p0/b0': 'story-state: unmodelled_outcome:$PokemonGlobal.<attr>',
    'map068/ev015/p0/b1': 'story-state: unmodelled_outcome:$PokemonGlobal.<attr>',
    'map073/ev001/p0/b1': '#109: text_unnormalizable -- code 101 @list[17]: unrecognized control code in fragments ["Aww, you don\'t have one? Well, it figures... Haven\'t gotten many customers of late, now that I\'ve already sold everyone in Kevlar Town a bike... Actually, if you ", \'bring me a \\\\C[3]Bike wheel\\\\C[0] I can fix an old bicycle and give it to you.\']',
}

CHAPTER = ch03.build()
