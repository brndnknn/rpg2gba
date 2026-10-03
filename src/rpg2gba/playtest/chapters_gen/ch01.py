"""GENERATED -- do not edit.

Chapter CH01. Regenerate with `python -m rpg2gba.beat_gen generate --chapter CH01`.
"""

from __future__ import annotations

from rpg2gba.playtest.archetypes.arrival_nudge import arrival_nudge_beat
from rpg2gba.playtest.archetypes.flavour_npc import flavour_npc_beat
from rpg2gba.playtest.archetypes.generic import generic_beat, obstacle_beat, transit_beat
from rpg2gba.playtest.archetypes.warp import warp_beat
from rpg2gba.playtest.chapter import ChapterBuilder
from rpg2gba.playtest.whiteout import whiteout_fork_beat

ch01 = ChapterBuilder('CH01', doc='beat_gen-generated module for CH01', suite='gen')

flavour_npc_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m049e004_flavour_npc',
    group='m049e004_flavour_npc',
    approach_prefer='south',
    event_id=4,
    map_constant='MAP_MOKI_TOWN_PLAYERS_HOUSE_1F',
    map_id=49,
    variant='plain',
)

flavour_npc_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m049e005_flavour_npc',
    group='m049e005_flavour_npc',
    approach_prefer='south',
    event_id=5,
    map_constant='MAP_MOKI_TOWN_PLAYERS_HOUSE_1F',
    map_id=49,
    variant='plain',
)

flavour_npc_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m049e006_flavour_npc',
    group='m049e006_flavour_npc',
    approach_prefer='south',
    event_id=6,
    map_constant='MAP_MOKI_TOWN_PLAYERS_HOUSE_1F',
    map_id=49,
    variant='plain',
)

flavour_npc_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m049e007_flavour_npc',
    group='m049e007_flavour_npc',
    approach_prefer='south',
    event_id=7,
    map_constant='MAP_MOKI_TOWN_PLAYERS_HOUSE_1F',
    map_id=49,
    variant='plain',
)

flavour_npc_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m049e008_flavour_npc',
    group='m049e008_flavour_npc',
    approach_prefer='south',
    event_id=8,
    map_constant='MAP_MOKI_TOWN_PLAYERS_HOUSE_1F',
    map_id=49,
    variant='plain',
)

warp_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m049e003_warp',
    group='m049e003_warp',
    dest_map_constant='MAP_MOKI_TOWN_PLAYERS_HOUSE_2F',
    direction='RIGHT',
    end_side='dest',
    event_id=3,
    map_constant='MAP_MOKI_TOWN_PLAYERS_HOUSE_1F',
    map_id=49,
    mechanism='threshold',
    start_side='origin',
)

generic_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m048e001p0',
    group='m048e001p0',
    rows=('map048/ev001/p0',),
    approach_prefer='arrive@(4,3)',
)

generic_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m048e005p0',
    group='m048e005p0',
    rows=('map048/ev005/p0',),
    approach_prefer='arrive@(4,3)',
)

generic_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m048e007p0',
    group='m048e007p0',
    rows=('map048/ev007/p0',),
    approach_prefer='south',
)

generic_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m048e008p0',
    group='m048e008p0',
    rows=('map048/ev008/p0',),
    approach_prefer='south',
)

flavour_npc_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m048e003_flavour_npc',
    group='m048e003_flavour_npc',
    approach_prefer='south',
    event_id=3,
    map_constant='MAP_MOKI_TOWN_PLAYERS_HOUSE_2F',
    map_id=48,
    variant='plain',
)

flavour_npc_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m048e009_flavour_npc',
    group='m048e009_flavour_npc',
    approach_prefer='west',
    event_id=9,
    map_constant='MAP_MOKI_TOWN_PLAYERS_HOUSE_2F',
    map_id=48,
    variant='plain',
)

generic_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m048e011p0',
    group='m048e011p0',
    rows=('map048/ev011/p0', 'map048/ev011/p0/b0', 'map048/ev011/p0/b1', 'map048/ev011/p0/b2', 'map048/ev011/p0/b3', 'map048/ev011/p0/b4', 'map048/ev011/p0/b5'),
    approach_prefer='south',
    random_arms=(('map048/ev011/p0/b0', ((1, '==', 0),)), ('map048/ev011/p0/b1', ((1, '!=', 0),)), ('map048/ev011/p0/b2', ((1, '==', 1),)), ('map048/ev011/p0/b3', ((1, '!=', 1),)), ('map048/ev011/p0/b4', ((1, '==', 2),)), ('map048/ev011/p0/b5', ((1, '!=', 2),))),
)

flavour_npc_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m048e006_flavour_npc',
    group='m048e006_flavour_npc',
    approach_prefer='east',
    event_id=6,
    map_constant='MAP_MOKI_TOWN_PLAYERS_HOUSE_2F',
    map_id=48,
    variant='plain',
)

flavour_npc_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m048e010_flavour_npc',
    group='m048e010_flavour_npc',
    approach_prefer='south',
    event_id=10,
    map_constant='MAP_MOKI_TOWN_PLAYERS_HOUSE_2F',
    map_id=48,
    variant='plain',
)

flavour_npc_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m048e012_flavour_npc',
    group='m048e012_flavour_npc',
    approach_prefer='south',
    event_id=12,
    map_constant='MAP_MOKI_TOWN_PLAYERS_HOUSE_2F',
    map_id=48,
    variant='plain',
)

generic_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m048e004p0',
    group='m048e004p0',
    rows=('map048/ev004/p0',),
    approach_prefer='south',
)

warp_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m048e002_warp',
    group='m048e002_warp',
    dest_map_constant='MAP_MOKI_TOWN_PLAYERS_HOUSE_1F',
    direction='LEFT',
    end_side='dest',
    event_id=2,
    map_constant='MAP_MOKI_TOWN_PLAYERS_HOUSE_2F',
    map_id=48,
    mechanism='threshold',
    start_side='origin',
)

flavour_npc_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m049e012_flavour_npc',
    group='m049e012_flavour_npc',
    approach_prefer='south',
    event_id=12,
    map_constant='MAP_MOKI_TOWN_PLAYERS_HOUSE_1F',
    map_id=49,
    variant='plain',
)

generic_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m049e002p0',
    group='m049e002p0',
    rows=('map049/ev002/p0',),
    approach_prefer='north',
)

flavour_npc_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m049e011_flavour_npc',
    group='m049e011_flavour_npc',
    approach_prefer='north',
    event_id=11,
    map_constant='MAP_MOKI_TOWN_PLAYERS_HOUSE_1F',
    map_id=49,
    variant='plain',
)

generic_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m049e001p0',
    group='m049e001p0',
    rows=('map049/ev001/p0',),
    approach_prefer='south',
)

flavour_npc_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m049e010_flavour_npc',
    group='m049e010_flavour_npc',
    approach_prefer='south',
    event_id=10,
    map_constant='MAP_MOKI_TOWN_PLAYERS_HOUSE_1F',
    map_id=49,
    variant='plain',
)

flavour_npc_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m049e009_flavour_npc',
    group='m049e009_flavour_npc',
    approach_prefer='south',
    event_id=9,
    map_constant='MAP_MOKI_TOWN_PLAYERS_HOUSE_1F',
    map_id=49,
    variant='plain',
)

flavour_npc_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m049e001_flavour_npc',
    group='m049e001_flavour_npc',
    approach_prefer='east',
    event_id=1,
    map_constant='MAP_MOKI_TOWN_PLAYERS_HOUSE_1F',
    map_id=49,
    page_idx=1,
    variant='plain',
)

flavour_npc_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m049e014_flavour_npc',
    group='m049e014_flavour_npc',
    approach_prefer='south',
    event_id=14,
    map_constant='MAP_MOKI_TOWN_PLAYERS_HOUSE_1F',
    map_id=49,
    variant='plain',
)

flavour_npc_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m049e013_flavour_npc',
    group='m049e013_flavour_npc',
    approach_prefer='south',
    event_id=13,
    map_constant='MAP_MOKI_TOWN_PLAYERS_HOUSE_1F',
    map_id=49,
    variant='plain',
)

flavour_npc_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m049e015_flavour_npc',
    group='m049e015_flavour_npc',
    approach_prefer='south',
    event_id=15,
    map_constant='MAP_MOKI_TOWN_PLAYERS_HOUSE_1F',
    map_id=49,
    variant='plain',
)

flavour_npc_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m049e016_flavour_npc',
    group='m049e016_flavour_npc',
    approach_prefer='south',
    event_id=16,
    map_constant='MAP_MOKI_TOWN_PLAYERS_HOUSE_1F',
    map_id=49,
    variant='plain',
)

warp_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m049e002p1_warp',
    group='m049e002p1_warp',
    dest_map_constant='MAP_MOKI_TOWN',
    direction='DOWN',
    end_side='dest',
    event_id=2,
    map_constant='MAP_MOKI_TOWN_PLAYERS_HOUSE_1F',
    map_id=49,
    mechanism='threshold',
    page_idx=1,
    start_side='origin',
)

arrival_nudge_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m032e005_arrival_nudge',
    group='m032e005_arrival_nudge',
    event_id=5,
    from_event_id=2,
    from_map_constant='MAP_MOKI_TOWN_PLAYERS_HOUSE_1F',
    map_constant='MAP_MOKI_TOWN',
    map_id=32,
)

generic_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m032e005_arrival_nudge_arms',
    group='m032e005_arrival_nudge',
    rows=('map032/ev005/p1/b0',),
    skip_claimed=True,
)

warp_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m032e005_warp',
    group='m032e005_warp',
    dest_map_constant='MAP_MOKI_TOWN_PLAYERS_HOUSE_1F',
    direction='UP',
    end_side='origin',
    event_id=5,
    map_constant='MAP_MOKI_TOWN',
    map_id=32,
    mechanism='threshold',
    return_direction='DOWN',
    start_side='origin',
)

flavour_npc_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m032e069p0_flavour_npc',
    group='m032e069p0_flavour_npc',
    approach_prefer='north',
    event_id=69,
    map_constant='MAP_MOKI_TOWN',
    map_id=32,
    variant='plain',
)

flavour_npc_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m032e004_flavour_npc',
    group='m032e004_flavour_npc',
    approach_prefer='east',
    event_id=4,
    map_constant='MAP_MOKI_TOWN',
    map_id=32,
    variant='plain',
)

flavour_npc_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m032e071p0_flavour_npc',
    group='m032e071p0_flavour_npc',
    approach_prefer='west',
    event_id=71,
    map_constant='MAP_MOKI_TOWN',
    map_id=32,
    variant='plain',
)

generic_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m032e074p0',
    group='m032e074p0',
    rows=('map032/ev074/p0', 'map032/ev074/p0/b0', 'map032/ev074/p0/b1', 'map032/ev074/p0/b2'),
    approach_prefer='south',
)

generic_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m032e074p1',
    group='m032e074p1',
    rows=('map032/ev074/p1',),
    approach_prefer='south',
)

warp_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m032e006_warp',
    group='m032e006_warp',
    dest_map_constant='MAP_MOKI_TOWN_HOUSE_2',
    direction='UP',
    end_side='dest',
    event_id=6,
    map_constant='MAP_MOKI_TOWN',
    map_id=32,
    mechanism='threshold',
    start_side='origin',
)

flavour_npc_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m064e001p0_flavour_npc',
    group='m064e001p0_flavour_npc',
    approach_prefer='south',
    event_id=1,
    map_constant='MAP_MOKI_TOWN_HOUSE_2',
    map_id=64,
    toggled_page_idx=None,
    variant='toggling',
)

generic_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m064e001p0_flavour_npc_arms',
    group='m064e001p0_flavour_npc',
    rows=('map064/ev001/p0/b1',),
    approach_prefer='south',
    skip_claimed=True,
)

generic_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m064e001p0_flavour_npc_arms_r1',
    group='m064e001p0_flavour_npc',
    rows=('map064/ev001/p0/b0',),
    approach_prefer='south',
    skip_claimed=True,
    walk_rows=('map064/ev001/p0',),
)

flavour_npc_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m064e004_flavour_npc',
    group='m064e004_flavour_npc',
    approach_prefer='south',
    event_id=4,
    map_constant='MAP_MOKI_TOWN_HOUSE_2',
    map_id=64,
    variant='plain',
)

flavour_npc_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m064e002p0_flavour_npc',
    group='m064e002p0_flavour_npc',
    approach_prefer='south',
    event_id=2,
    map_constant='MAP_MOKI_TOWN_HOUSE_2',
    map_id=64,
    toggled_page_idx=None,
    variant='toggling',
)

generic_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m064e002p0_flavour_npc_arms',
    group='m064e002p0_flavour_npc',
    rows=('map064/ev002/p0/b1',),
    approach_prefer='south',
    skip_claimed=True,
)

generic_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m064e002p0_flavour_npc_arms_r1',
    group='m064e002p0_flavour_npc',
    rows=('map064/ev002/p0/b0',),
    approach_prefer='south',
    skip_claimed=True,
    walk_rows=('map064/ev002/p0',),
)

warp_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m064e003_warp',
    group='m064e003_warp',
    dest_map_constant='MAP_MOKI_TOWN',
    direction='DOWN',
    end_side='dest',
    event_id=3,
    map_constant='MAP_MOKI_TOWN_HOUSE_2',
    map_id=64,
    mechanism='threshold',
    start_side='origin',
)

arrival_nudge_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m032e006_arrival_nudge',
    group='m032e006_arrival_nudge',
    event_id=6,
    from_event_id=3,
    from_map_constant='MAP_MOKI_TOWN_HOUSE_2',
    map_constant='MAP_MOKI_TOWN',
    map_id=32,
)

generic_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m032e006_arrival_nudge_arms',
    group='m032e006_arrival_nudge',
    rows=('map032/ev006/p1/b0',),
    skip_claimed=True,
)

generic_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m032e027p0',
    group='m032e027p0',
    rows=('map032/ev027/p0', 'map032/ev027/p0/b0'),
    approach_prefer='west',
)

flavour_npc_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m032e027p1_flavour_npc',
    group='m032e027p1_flavour_npc',
    approach_prefer='west',
    event_id=27,
    map_constant='MAP_MOKI_TOWN',
    map_id=32,
    page_idx=1,
    variant='plain',
)

flavour_npc_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m032e008_flavour_npc',
    group='m032e008_flavour_npc',
    approach_prefer='north',
    event_id=8,
    map_constant='MAP_MOKI_TOWN',
    map_id=32,
    variant='plain',
)

generic_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m032e012p0',
    group='m032e012p0',
    rows=('map032/ev012/p0', 'map032/ev012/p0/b0', 'map032/ev012/p0/b1', 'map032/ev012/p0/b2', 'map032/ev012/p0/b3', 'map032/ev012/p0/b4', 'map032/ev012/p0/b5'),
    approach_prefer='east',
    random_arms=(('map032/ev012/p0/b0', ((102, '==', 0),)), ('map032/ev012/p0/b1', ((102, '!=', 0),)), ('map032/ev012/p0/b2', ((102, '==', 1),)), ('map032/ev012/p0/b3', ((102, '!=', 1),)), ('map032/ev012/p0/b4', ((102, '==', 2),)), ('map032/ev012/p0/b5', ((102, '!=', 2),))),
)

flavour_npc_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m032e073p0_flavour_npc',
    group='m032e073p0_flavour_npc',
    approach_prefer='north',
    event_id=73,
    map_constant='MAP_MOKI_TOWN',
    map_id=32,
    variant='plain',
)

flavour_npc_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m032e072p0_flavour_npc',
    group='m032e072p0_flavour_npc',
    approach_prefer='north',
    event_id=72,
    map_constant='MAP_MOKI_TOWN',
    map_id=32,
    variant='plain',
)

flavour_npc_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m032e001_flavour_npc',
    group='m032e001_flavour_npc',
    approach_prefer='south',
    event_id=1,
    map_constant='MAP_MOKI_TOWN',
    map_id=32,
    variant='plain',
)

generic_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m032e013p0',
    group='m032e013p0',
    rows=('map032/ev013/p0', 'map032/ev013/p0/b0', 'map032/ev013/p0/b1', 'map032/ev013/p0/b2', 'map032/ev013/p0/b3'),
    approach_prefer='north',
    random_arms=(('map032/ev013/p0/b0', ((102, '==', 0),)), ('map032/ev013/p0/b1', ((102, '!=', 0),)), ('map032/ev013/p0/b2', ((102, '==', 1),)), ('map032/ev013/p0/b3', ((102, '!=', 1),))),
)

flavour_npc_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m032e070p0_flavour_npc',
    group='m032e070p0_flavour_npc',
    approach_prefer='north',
    event_id=70,
    map_constant='MAP_MOKI_TOWN',
    map_id=32,
    variant='plain',
)

flavour_npc_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m032e048p0_flavour_npc',
    group='m032e048p0_flavour_npc',
    approach_prefer='south',
    event_id=48,
    map_constant='MAP_MOKI_TOWN',
    map_id=32,
    variant='plain',
)

flavour_npc_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m032e068p0_flavour_npc',
    group='m032e068p0_flavour_npc',
    approach_prefer='north',
    event_id=68,
    map_constant='MAP_MOKI_TOWN',
    map_id=32,
    variant='plain',
)

warp_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m032e017_warp',
    group='m032e017_warp',
    dest_map_constant='MAP_MOKI_TOWN_THEOS_HOUSE_1F',
    direction='UP',
    end_side='dest',
    event_id=17,
    map_constant='MAP_MOKI_TOWN',
    map_id=32,
    mechanism='threshold',
    start_side='origin',
)

flavour_npc_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m172e001p0_flavour_npc',
    group='m172e001p0_flavour_npc',
    approach_prefer='east',
    event_id=1,
    map_constant='MAP_MOKI_TOWN_THEOS_HOUSE_1F',
    map_id=172,
    moved_by=('map172/ev004/p0', 'map172/ev004/p2'),
    variant='plain',
)

warp_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m172e003_warp',
    group='m172e003_warp',
    dest_map_constant='MAP_MOKI_TOWN_THEOS_HOUSE_2F',
    direction='RIGHT',
    end_side='dest',
    event_id=3,
    map_constant='MAP_MOKI_TOWN_THEOS_HOUSE_1F',
    map_id=172,
    mechanism='threshold',
    start_side='origin',
)

generic_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m089e005p0',
    group='m089e005p0',
    rows=('map089/ev005/p0',),
    approach_prefer='south',
)

generic_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m089e003p0',
    group='m089e003p0',
    rows=('map089/ev003/p0',),
    approach_prefer='south',
)

flavour_npc_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m089e007_flavour_npc',
    group='m089e007_flavour_npc',
    approach_prefer='south',
    event_id=7,
    map_constant='MAP_MOKI_TOWN_THEOS_HOUSE_2F',
    map_id=89,
    variant='plain',
)

flavour_npc_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m089e006_flavour_npc',
    group='m089e006_flavour_npc',
    approach_prefer='south',
    event_id=6,
    map_constant='MAP_MOKI_TOWN_THEOS_HOUSE_2F',
    map_id=89,
    variant='plain',
)

generic_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m089e004p0_c2a0',
    group='m089e004p0',
    rows=('map089/ev004/p0/b0',),
    approach_prefer='south',
    choice_answers=((2, 0),),
    walk_rows=('map089/ev004/p0',),
)

generic_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m089e004p0',
    group='m089e004p0',
    rows=('map089/ev004/p0', 'map089/ev004/p0/b1'),
    approach_prefer='south',
    choice_answers=((2, 1),),
)

warp_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m089e002_warp',
    group='m089e002_warp',
    dest_map_constant='MAP_MOKI_TOWN_THEOS_HOUSE_1F',
    direction='LEFT',
    end_side='dest',
    event_id=2,
    map_constant='MAP_MOKI_TOWN_THEOS_HOUSE_2F',
    map_id=89,
    mechanism='threshold',
    start_side='origin',
)

warp_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m172e002_warp',
    group='m172e002_warp',
    dest_map_constant='MAP_MOKI_TOWN',
    direction='DOWN',
    end_side='dest',
    event_id=2,
    map_constant='MAP_MOKI_TOWN_THEOS_HOUSE_1F',
    map_id=172,
    mechanism='threshold',
    start_side='origin',
)

arrival_nudge_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m032e017_arrival_nudge',
    group='m032e017_arrival_nudge',
    event_id=17,
    from_event_id=2,
    from_map_constant='MAP_MOKI_TOWN_THEOS_HOUSE_1F',
    map_constant='MAP_MOKI_TOWN',
    map_id=32,
)

generic_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m032e017_arrival_nudge_arms',
    group='m032e017_arrival_nudge',
    rows=('map032/ev017/p1/b0',),
    skip_claimed=True,
)

flavour_npc_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m032e011_flavour_npc',
    group='m032e011_flavour_npc',
    approach_prefer='south',
    event_id=11,
    map_constant='MAP_MOKI_TOWN',
    map_id=32,
    variant='plain',
)

obstacle_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m032obstacle_rock_smash',
    group='m032obstacle_rock_smash',
    rows=('map032/ev014/p0', 'map032/ev015/p0', 'map032/ev033/p0'),
    approach_prefer='west',
    capability='rock_smash',
)

warp_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m032e007_warp',
    group='m032e007_warp',
    dest_map_constant='MAP_MOKI_TOWN_HOUSE_1',
    direction='UP',
    end_side='dest',
    event_id=7,
    map_constant='MAP_MOKI_TOWN',
    map_id=32,
    mechanism='threshold',
    start_side='origin',
)

flavour_npc_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m065e001p0_flavour_npc',
    group='m065e001p0_flavour_npc',
    approach_prefer='west',
    event_id=1,
    map_constant='MAP_MOKI_TOWN_HOUSE_1',
    map_id=65,
    toggled_page_idx=None,
    variant='toggling',
)

generic_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m065e001p0_flavour_npc_arms',
    group='m065e001p0_flavour_npc',
    rows=('map065/ev001/p0/b1',),
    approach_prefer='west',
    skip_claimed=True,
)

generic_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m065e001p0_flavour_npc_arms_r1',
    group='m065e001p0_flavour_npc',
    rows=('map065/ev001/p0/b0',),
    approach_prefer='west',
    skip_claimed=True,
    walk_rows=('map065/ev001/p0',),
)

flavour_npc_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m065e002p0_flavour_npc',
    group='m065e002p0_flavour_npc',
    approach_prefer='south',
    event_id=2,
    map_constant='MAP_MOKI_TOWN_HOUSE_1',
    map_id=65,
    toggled_page_idx=None,
    variant='toggling',
)

generic_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m065e002p0_flavour_npc_arms',
    group='m065e002p0_flavour_npc',
    rows=('map065/ev002/p0/b1',),
    approach_prefer='south',
    skip_claimed=True,
)

generic_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m065e002p0_flavour_npc_arms_r1',
    group='m065e002p0_flavour_npc',
    rows=('map065/ev002/p0/b0',),
    approach_prefer='south',
    skip_claimed=True,
    walk_rows=('map065/ev002/p0',),
)

warp_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m065e003_warp',
    group='m065e003_warp',
    dest_map_constant='MAP_MOKI_TOWN',
    direction='DOWN',
    end_side='dest',
    event_id=3,
    map_constant='MAP_MOKI_TOWN_HOUSE_1',
    map_id=65,
    mechanism='threshold',
    start_side='origin',
)

arrival_nudge_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m032e007_arrival_nudge',
    group='m032e007_arrival_nudge',
    event_id=7,
    from_event_id=3,
    from_map_constant='MAP_MOKI_TOWN_HOUSE_1',
    map_constant='MAP_MOKI_TOWN',
    map_id=32,
)

generic_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m032e007_arrival_nudge_arms',
    group='m032e007_arrival_nudge',
    rows=('map032/ev007/p1/b0',),
    skip_claimed=True,
)

generic_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m032e009p0',
    group='m032e009p0',
    rows=('map032/ev009/p0', 'map032/ev009/p0/b1'),
    approach_prefer='south',
)

warp_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m032e003_warp',
    group='m032e003_warp',
    dest_map_constant='MAP_MOKI_TOWN_PROFESSOR_LAB',
    direction='UP',
    end_side='dest',
    event_id=3,
    map_constant='MAP_MOKI_TOWN',
    map_id=32,
    mechanism='threshold',
    start_side='origin',
)

generic_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m050e005p0',
    group='m050e005p0',
    rows=('map050/ev005/p0', 'map050/ev005/p0/b1', 'map050/ev005/p0/b3'),
    approach_prefer='arrive@(14,18)',
    choice_answers=((48, 1),),
)

generic_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m050e002p0',
    group='m050e002p0',
    rows=('map050/ev002/p0',),
    approach_prefer='east',
)

generic_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m050e007p0',
    group='m050e007p0',
    rows=('map050/ev007/p0',),
    approach_prefer='south',
)

generic_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m050e006p0',
    group='m050e006p0',
    rows=('map050/ev006/p0',),
    approach_prefer='south',
)

flavour_npc_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m050e014_flavour_npc',
    group='m050e014_flavour_npc',
    approach_prefer='south',
    event_id=14,
    map_constant='MAP_MOKI_TOWN_PROFESSOR_LAB',
    map_id=50,
    variant='plain',
)

flavour_npc_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m050e020_flavour_npc',
    group='m050e020_flavour_npc',
    approach_prefer='south',
    event_id=20,
    map_constant='MAP_MOKI_TOWN_PROFESSOR_LAB',
    map_id=50,
    moved_by=('map050/ev019/p0',),
    variant='plain',
)

generic_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m050e005p2_c2a1',
    group='m050e005p2',
    rows=('map050/ev005/p2/b5',),
    approach_prefer='south',
    choice_answers=((2, 1),),
    walk_rows=('map050/ev005/p2',),
)

generic_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m050e005p2',
    group='m050e005p2',
    rows=('map050/ev005/p2', 'map050/ev005/p2/b0', 'map050/ev005/p0/b2'),
    approach_prefer='south',
    choice_answers=((2, 0), (57, 0), (68, 0), (77, 0), (86, 0)),
)

flavour_npc_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m050e005p1_flavour_npc',
    group='m050e005p1_flavour_npc',
    approach_prefer='south',
    event_id=5,
    map_constant='MAP_MOKI_TOWN_PROFESSOR_LAB',
    map_id=50,
    moved_by=('map050/ev005/p0', 'map050/ev019/p0'),
    page_idx=1,
    variant='plain',
)

flavour_npc_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m050e016_flavour_npc',
    group='m050e016_flavour_npc',
    approach_prefer='south',
    event_id=16,
    map_constant='MAP_MOKI_TOWN_PROFESSOR_LAB',
    map_id=50,
    variant='plain',
)

flavour_npc_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m050e015_flavour_npc',
    group='m050e015_flavour_npc',
    approach_prefer='south',
    event_id=15,
    map_constant='MAP_MOKI_TOWN_PROFESSOR_LAB',
    map_id=50,
    variant='plain',
)

flavour_npc_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m050e012_flavour_npc',
    group='m050e012_flavour_npc',
    approach_prefer='south',
    event_id=12,
    map_constant='MAP_MOKI_TOWN_PROFESSOR_LAB',
    map_id=50,
    variant='plain',
)

flavour_npc_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m050e010_flavour_npc',
    group='m050e010_flavour_npc',
    approach_prefer='north',
    event_id=10,
    map_constant='MAP_MOKI_TOWN_PROFESSOR_LAB',
    map_id=50,
    variant='plain',
)

flavour_npc_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m050e011_flavour_npc',
    group='m050e011_flavour_npc',
    approach_prefer='north',
    event_id=11,
    map_constant='MAP_MOKI_TOWN_PROFESSOR_LAB',
    map_id=50,
    variant='plain',
)

flavour_npc_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m050e008_flavour_npc',
    group='m050e008_flavour_npc',
    approach_prefer='south',
    event_id=8,
    map_constant='MAP_MOKI_TOWN_PROFESSOR_LAB',
    map_id=50,
    variant='plain',
)

generic_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m050e026p0_face_north_east_west',
    group='m050e026p0_face_north_east_west',
    rows=('map050/ev026/p0/b1',),
    approach_prefer='north',
)

generic_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m050e026p0',
    group='m050e026p0',
    rows=('map050/ev026/p0',),
    approach_prefer='north',
)

flavour_npc_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m050e004p0_flavour_npc',
    group='m050e004p0_flavour_npc',
    approach_prefer='south',
    event_id=4,
    map_constant='MAP_MOKI_TOWN_PROFESSOR_LAB',
    map_id=50,
    variant='plain',
)

flavour_npc_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m050e009_flavour_npc',
    group='m050e009_flavour_npc',
    approach_prefer='south',
    event_id=9,
    map_constant='MAP_MOKI_TOWN_PROFESSOR_LAB',
    map_id=50,
    variant='plain',
)

flavour_npc_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m050e021_flavour_npc',
    group='m050e021_flavour_npc',
    approach_prefer='west',
    event_id=21,
    map_constant='MAP_MOKI_TOWN_PROFESSOR_LAB',
    map_id=50,
    variant='plain',
)

generic_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m050e019p0',
    group='m050e019p0',
    rows=('map050/ev019/p0', 'map050/ev019/p0/b7', 'map050/ev019/p0/b8'),
    approach_prefer='east',
    gift_ceremonies=(9,),
)

whiteout_fork_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m049_whiteout',
    group='m050e019p0',
    rows=('map049/ev022/p0',),
    heal_location_id='HEAL_LOCATION_URANIUM_START',
)

generic_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m050e019p1',
    group='m050e019p1',
    rows=('map050/ev019/p1',),
    approach_prefer='east',
)

generic_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m050e009p1_c2a0',
    group='m050e009p1',
    rows=('map050/ev009/p1/b0',),
    approach_prefer='west',
    choice_answers=((2, 0),),
    walk_rows=('map050/ev009/p1',),
)

generic_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m050e009p1',
    group='m050e009p1',
    rows=('map050/ev009/p1', 'map050/ev009/p1/b1'),
    approach_prefer='west',
    choice_answers=((2, 1),),
)

generic_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m050e021p1_c2a0',
    group='m050e021p1',
    rows=('map050/ev021/p1/b0',),
    approach_prefer='west',
    choice_answers=((2, 0),),
    walk_rows=('map050/ev021/p1',),
)

generic_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m050e021p1',
    group='m050e021p1',
    rows=('map050/ev021/p1', 'map050/ev021/p1/b1'),
    approach_prefer='west',
    choice_answers=((2, 1),),
)

generic_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m050e020p1',
    group='m050e020p1',
    rows=('map050/ev020/p1',),
    approach_prefer='east',
)

flavour_npc_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m050e004p1_flavour_npc',
    group='m050e004p1_flavour_npc',
    approach_prefer='west',
    event_id=4,
    map_constant='MAP_MOKI_TOWN_PROFESSOR_LAB',
    map_id=50,
    page_idx=1,
    variant='plain',
)

generic_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m050e002p1',
    group='m050e002p1',
    rows=('map050/ev002/p1',),
    approach_prefer='east',
)

flavour_npc_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m050e013_flavour_npc',
    group='m050e013_flavour_npc',
    approach_prefer='east',
    event_id=13,
    map_constant='MAP_MOKI_TOWN_PROFESSOR_LAB',
    map_id=50,
    variant='plain',
)

warp_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m050e001_warp',
    group='m050e001_warp',
    dest_map_constant='MAP_MOKI_TOWN',
    direction='DOWN',
    end_side='origin',
    event_id=1,
    map_constant='MAP_MOKI_TOWN_PROFESSOR_LAB',
    map_id=50,
    mechanism='threshold',
    page_idx=1,
    return_direction='UP',
    start_side='origin',
)

generic_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m050e026p0_face_south',
    group='m050e026p0_face_south',
    rows=('map050/ev026/p0/b0',),
    approach_prefer='south',
)

flavour_npc_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m050e003_flavour_npc',
    group='m050e003_flavour_npc',
    approach_prefer='west',
    event_id=3,
    map_constant='MAP_MOKI_TOWN_PROFESSOR_LAB',
    map_id=50,
    variant='plain',
)

transit_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m032e003_arrival_nudge_transit',
    group='m032e003_arrival_nudge',
    hops=(('MAP_MOKI_TOWN_PROFESSOR_LAB', 14, 18, 'DOWN', 'MAP_MOKI_TOWN'),),
)

arrival_nudge_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m032e003_arrival_nudge',
    group='m032e003_arrival_nudge',
    event_id=3,
    from_event_id=1,
    from_map_constant='MAP_MOKI_TOWN_PROFESSOR_LAB',
    map_constant='MAP_MOKI_TOWN',
    map_id=32,
)

generic_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m032e003_arrival_nudge_arms',
    group='m032e003_arrival_nudge',
    rows=('map032/ev003/p1/b0',),
    skip_claimed=True,
)

generic_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m032e074p2',
    group='m032e074p2',
    rows=('map032/ev074/p2',),
    approach_prefer='south',
)

transit_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m049e001p2_transit',
    group='m049e001p2',
    hops=(('MAP_MOKI_TOWN', 28, 32, 'UP', 'MAP_MOKI_TOWN_PLAYERS_HOUSE_1F'),),
)

generic_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m049e001p2',
    group='m049e001p2',
    rows=('map049/ev001/p2',),
    approach_prefer='south',
)

transit_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m032e009p1_transit',
    group='m032e009p1',
    hops=(('MAP_MOKI_TOWN_PLAYERS_HOUSE_1F', 10, 10, 'DOWN', 'MAP_MOKI_TOWN'),),
)

generic_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m032e009p1',
    group='m032e009p1',
    rows=('map032/ev009/p1', 'map032/ev009/p1/b1'),
    approach_prefer='south',
)

transit_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m172e004p0_transit',
    group='m172e004p0',
    hops=(('MAP_MOKI_TOWN', 56, 43, 'UP', 'MAP_MOKI_TOWN_THEOS_HOUSE_1F'),),
)

generic_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m172e004p0',
    group='m172e004p0',
    rows=('map172/ev004/p0', 'map172/ev004/p0/b3', 'map172/ev004/p0/b5'),
    approach_prefer='arrive@(10,10)',
    choice_answers=((16, 1),),
)

generic_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m172e004p1',
    group='m172e004p1',
    rows=('map172/ev004/p1',),
    approach_prefer='south',
)

flavour_npc_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m172e001p1_flavour_npc',
    group='m172e001p1_flavour_npc',
    approach_prefer='south',
    event_id=1,
    map_constant='MAP_MOKI_TOWN_THEOS_HOUSE_1F',
    map_id=172,
    moved_by=('map172/ev004/p0', 'map172/ev004/p2'),
    page_idx=1,
    variant='plain',
)

transit_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m032e009p2_transit',
    group='m032e009p2',
    hops=(('MAP_MOKI_TOWN_THEOS_HOUSE_1F', 10, 10, 'DOWN', 'MAP_MOKI_TOWN'),),
)

generic_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m032e009p2',
    group='m032e009p2',
    rows=('map032/ev009/p2', 'map032/ev009/p2/b1', 'map032/ev009/p2/b2', 'map032/ev009/p2/b4', 'map032/ev009/p2/b5', 'map032/ev009/p2/b6', 'map032/ev009/p2/b7', 'map032/ev009/p2/b8', 'map032/ev009/p2/b9', 'map032/ev009/p2/b10', 'map032/ev009/p2/b11', 'map032/ev009/p2/b12', 'map032/ev009/p2/b13', 'map032/ev009/p2/b14', 'map032/ev009/p2/b15', 'map032/ev009/p2/b16'),
    approach_prefer='south',
    random_arms=(('map032/ev009/p2/b10', ((1, '==', 0),)), ('map032/ev009/p2/b11', ((1, '!=', 0),)), ('map032/ev009/p2/b12', ((1, '==', 1),)), ('map032/ev009/p2/b13', ((1, '!=', 1),)), ('map032/ev009/p2/b14', ((1, '==', 2),)), ('map032/ev009/p2/b15', ((1, '!=', 2),)), ('map032/ev009/p2/b4', ((1, '==', 0),)), ('map032/ev009/p2/b5', ((1, '!=', 0),)), ('map032/ev009/p2/b6', ((1, '==', 1),)), ('map032/ev009/p2/b7', ((1, '!=', 1),)), ('map032/ev009/p2/b8', ((1, '==', 2),)), ('map032/ev009/p2/b9', ((1, '!=', 2),))),
)

flavour_npc_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m032e009_flavour_npc',
    group='m032e009_flavour_npc',
    approach_prefer='south',
    event_id=9,
    map_constant='MAP_MOKI_TOWN',
    map_id=32,
    page_idx=3,
    variant='plain',
)

transit_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m049e001p3_transit',
    group='m049e001p3',
    hops=(('MAP_MOKI_TOWN', 28, 32, 'UP', 'MAP_MOKI_TOWN_PLAYERS_HOUSE_1F'),),
)

generic_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m049e001p3',
    group='m049e001p3',
    rows=('map049/ev001/p3', 'map049/ev001/p3/b0', 'map049/ev001/p3/b1', 'map049/ev001/p3/b2', 'map049/ev001/p3/b3', 'map049/ev001/p3/b4', 'map049/ev001/p3/b5', 'map049/ev001/p3/b6', 'map049/ev001/p3/b7', 'map049/ev001/p3/b8', 'map049/ev001/p3/b9', 'map049/ev001/p3/b10', 'map049/ev001/p3/b11', 'map049/ev001/p3/b12', 'map049/ev001/p3/b13', 'map049/ev001/p3/b14', 'map049/ev001/p3/b15', 'map049/ev001/p3/b16', 'map049/ev001/p3/b17', 'map049/ev001/p3/b18', 'map049/ev001/p3/b19', 'map049/ev001/p3/b20', 'map049/ev001/p3/b21', 'map049/ev001/p3/b22', 'map049/ev001/p3/b23', 'map049/ev001/p3/b24', 'map049/ev001/p3/b25'),
    approach_prefer='south',
    random_arms=(('map049/ev001/p3/b0', ((102, '==', 0),)), ('map049/ev001/p3/b1', ((102, '!=', 0),)), ('map049/ev001/p3/b10', ((102, '==', 5),)), ('map049/ev001/p3/b11', ((102, '!=', 5),)), ('map049/ev001/p3/b12', ((102, '==', 6),)), ('map049/ev001/p3/b13', ((102, '!=', 6),)), ('map049/ev001/p3/b14', ((102, '==', 7),)), ('map049/ev001/p3/b15', ((102, '!=', 7),)), ('map049/ev001/p3/b16', ((102, '==', 8),)), ('map049/ev001/p3/b17', ((102, '!=', 8),)), ('map049/ev001/p3/b18', ((102, '==', 9),)), ('map049/ev001/p3/b19', ((102, '!=', 9),)), ('map049/ev001/p3/b2', ((102, '==', 1),)), ('map049/ev001/p3/b20', ((102, '==', 10),)), ('map049/ev001/p3/b21', ((102, '!=', 10),)), ('map049/ev001/p3/b22', ((102, '==', 11),)), ('map049/ev001/p3/b23', ((102, '!=', 11),)), ('map049/ev001/p3/b24', ((102, '==', 12),)), ('map049/ev001/p3/b25', ((102, '!=', 12),)), ('map049/ev001/p3/b3', ((102, '!=', 1),)), ('map049/ev001/p3/b4', ((102, '==', 2),)), ('map049/ev001/p3/b5', ((102, '!=', 2),)), ('map049/ev001/p3/b6', ((102, '==', 3),)), ('map049/ev001/p3/b7', ((102, '!=', 3),)), ('map049/ev001/p3/b8', ((102, '==', 4),)), ('map049/ev001/p3/b9', ((102, '!=', 4),))),
)

transit_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m050e019p2_transit',
    group='m050e019p2',
    hops=(('MAP_MOKI_TOWN_PLAYERS_HOUSE_1F', 10, 10, 'DOWN', 'MAP_MOKI_TOWN'), ('MAP_MOKI_TOWN', 17, 12, 'UP', 'MAP_MOKI_TOWN_PROFESSOR_LAB')),
)

generic_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m050e019p2',
    group='m050e019p2',
    rows=('map050/ev019/p2',),
    approach_prefer='east',
)

transit_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m032e023_warp_transit',
    group='m032e023_warp',
    hops=(('MAP_MOKI_TOWN_PROFESSOR_LAB', 14, 18, 'DOWN', 'MAP_MOKI_TOWN'),),
)

warp_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m032e023_warp',
    group='m032e023_warp',
    boundary=True,
    dest_map_constant='MAP_ROUTE_01',
    direction='LEFT',
    event_id=23,
    map_constant='MAP_MOKI_TOWN',
    map_id=32,
    mechanism='threshold',
)

warp_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m032e036_warp',
    group='m032e023_warp',
    boundary=True,
    dest_map_constant='MAP_ROUTE_01',
    direction='LEFT',
    event_id=36,
    map_constant='MAP_MOKI_TOWN',
    map_id=32,
    mechanism='threshold',
)

warp_beat(
    ch01,
    chapter_id='CH01',
    beat_name='m032e037_warp',
    group='m032e023_warp',
    boundary=True,
    dest_map_constant='MAP_ROUTE_01',
    direction='LEFT',
    event_id=37,
    map_constant='MAP_MOKI_TOWN',
    map_id=32,
    mechanism='threshold',
)

NEVER_FIRES: dict[str, str] = {
    'map050/ev001/p0': "map050/ev001/p0 fires only on (14, 19); while it is the live page the walk can't step on them: arrival (14, 18) -> start (14, 8) (scene map050/ev005/p0); arrival (14, 7) -> start (14, 4) (scene map050/ev005/p0); arrival (14, 7) -> start (14, 7) (scene map050/ev005/p0); ev002 pushes the player off row y=16 (x=11..20, 8 cells); over 4 story state(s) the reachable region (100 cells) touches none of them and has no way out of the map; map050/ev001/p1 supersedes it once variable 101 >= 1",
    'map050/ev005/p3': "map050/ev005/p3 (needs var 101 >= 1) is not its event's live page at this route position: var 101 >= 1 fails: var 101 is [0] (seed state), never written on the route; the rows that could write it none are not walked before it; live page: map050/ev005/p1 (needs self switch C == True)",
    'map050/ev005/p4': "map050/ev005/p4 (needs var 101 >= 2) is not its event's live page at this route position: var 101 >= 2 fails: var 101 is [0] (seed state), never written on the route; the rows that could write it none are not walked before it; live page: map050/ev005/p1 (needs self switch C == True)",
}

EMPTY_PAGES: dict[str, str] = {
    'map032/ev002/p0': 'every page of the event is empty; nothing to check on the ROM',
    'map032/ev002/p1': 'every page of the event is empty; nothing to check on the ROM',
    'map032/ev016/p0': 'every page of the event is empty; nothing to check on the ROM',
    'map032/ev016/p1': 'every page of the event is empty; nothing to check on the ROM',
    'map032/ev018/p0': 'every page of the event is empty; nothing to check on the ROM',
    'map032/ev020/p0': 'every page of the event is empty; nothing to check on the ROM',
    'map032/ev022/p0': 'every page of the event is empty; nothing to check on the ROM',
    'map032/ev075/p0': 'every page of the event is empty; nothing to check on the ROM',
    'map032/ev075/p1': 'every page of the event is empty; nothing to check on the ROM',
    'map032/ev075/p2': 'every page of the event is empty; nothing to check on the ROM',
    'map032/ev076/p0': 'every page of the event is empty; nothing to check on the ROM',
    'map032/ev076/p1': 'every page of the event is empty; nothing to check on the ROM',
    'map032/ev077/p0': 'every page of the event is empty; nothing to check on the ROM',
    'map032/ev077/p1': 'every page of the event is empty; nothing to check on the ROM',
    'map032/ev079/p0': 'every page of the event is empty; nothing to check on the ROM',
    'map032/ev079/p1': 'every page of the event is empty; nothing to check on the ROM',
    'map032/ev081/p0': 'every page of the event is empty; nothing to check on the ROM',
    'map032/ev081/p1': 'every page of the event is empty; nothing to check on the ROM',
    'map049/ev019/p0': 'every page of the event is empty; nothing to check on the ROM',
    'map049/ev019/p1': 'every page of the event is empty; nothing to check on the ROM',
    'map050/ev017/p0': 'every page of the event is empty; nothing to check on the ROM',
    'map050/ev018/p0': 'every page of the event is empty; nothing to check on the ROM',
    'map050/ev023/p0': 'every page of the event is empty; nothing to check on the ROM',
}

WALK_CHECKED: dict[str, str] = {
    'map032/ev009/p2/b10': 'arm on a rolled or computed value (var 1 == 0); the walk checks whichever fires',
    'map032/ev009/p2/b11': 'arm on a rolled or computed value (var 1 != 0); the walk checks whichever fires',
    'map032/ev009/p2/b12': 'arm on a rolled or computed value (var 1 == 1); the walk checks whichever fires',
    'map032/ev009/p2/b13': 'arm on a rolled or computed value (var 1 != 1); the walk checks whichever fires',
    'map032/ev009/p2/b14': 'arm on a rolled or computed value (var 1 == 2); the walk checks whichever fires',
    'map032/ev009/p2/b15': 'arm on a rolled or computed value (var 1 != 2); the walk checks whichever fires',
    'map032/ev009/p2/b4': 'arm on a rolled or computed value (var 1 == 0); the walk checks whichever fires',
    'map032/ev009/p2/b5': 'arm on a rolled or computed value (var 1 != 0); the walk checks whichever fires',
    'map032/ev009/p2/b6': 'arm on a rolled or computed value (var 1 == 1); the walk checks whichever fires',
    'map032/ev009/p2/b7': 'arm on a rolled or computed value (var 1 != 1); the walk checks whichever fires',
    'map032/ev009/p2/b8': 'arm on a rolled or computed value (var 1 == 2); the walk checks whichever fires',
    'map032/ev009/p2/b9': 'arm on a rolled or computed value (var 1 != 2); the walk checks whichever fires',
    'map032/ev012/p0/b0': 'arm on a rolled or computed value (var 102 == 0); the walk checks whichever fires',
    'map032/ev012/p0/b1': 'arm on a rolled or computed value (var 102 != 0); the walk checks whichever fires',
    'map032/ev012/p0/b2': 'arm on a rolled or computed value (var 102 == 1); the walk checks whichever fires',
    'map032/ev012/p0/b3': 'arm on a rolled or computed value (var 102 != 1); the walk checks whichever fires',
    'map032/ev012/p0/b4': 'arm on a rolled or computed value (var 102 == 2); the walk checks whichever fires',
    'map032/ev012/p0/b5': 'arm on a rolled or computed value (var 102 != 2); the walk checks whichever fires',
    'map032/ev013/p0/b0': 'arm on a rolled or computed value (var 102 == 0); the walk checks whichever fires',
    'map032/ev013/p0/b1': 'arm on a rolled or computed value (var 102 != 0); the walk checks whichever fires',
    'map032/ev013/p0/b2': 'arm on a rolled or computed value (var 102 == 1); the walk checks whichever fires',
    'map032/ev013/p0/b3': 'arm on a rolled or computed value (var 102 != 1); the walk checks whichever fires',
    'map048/ev011/p0/b0': 'arm on a rolled or computed value (var 1 == 0); the walk checks whichever fires',
    'map048/ev011/p0/b1': 'arm on a rolled or computed value (var 1 != 0); the walk checks whichever fires',
    'map048/ev011/p0/b2': 'arm on a rolled or computed value (var 1 == 1); the walk checks whichever fires',
    'map048/ev011/p0/b3': 'arm on a rolled or computed value (var 1 != 1); the walk checks whichever fires',
    'map048/ev011/p0/b4': 'arm on a rolled or computed value (var 1 == 2); the walk checks whichever fires',
    'map048/ev011/p0/b5': 'arm on a rolled or computed value (var 1 != 2); the walk checks whichever fires',
    'map049/ev001/p3/b0': 'arm on a rolled or computed value (var 102 == 0); the walk checks whichever fires',
    'map049/ev001/p3/b1': 'arm on a rolled or computed value (var 102 != 0); the walk checks whichever fires',
    'map049/ev001/p3/b10': 'arm on a rolled or computed value (var 102 == 5); the walk checks whichever fires',
    'map049/ev001/p3/b11': 'arm on a rolled or computed value (var 102 != 5); the walk checks whichever fires',
    'map049/ev001/p3/b12': 'arm on a rolled or computed value (var 102 == 6); the walk checks whichever fires',
    'map049/ev001/p3/b13': 'arm on a rolled or computed value (var 102 != 6); the walk checks whichever fires',
    'map049/ev001/p3/b14': 'arm on a rolled or computed value (var 102 == 7); the walk checks whichever fires',
    'map049/ev001/p3/b15': 'arm on a rolled or computed value (var 102 != 7); the walk checks whichever fires',
    'map049/ev001/p3/b16': 'arm on a rolled or computed value (var 102 == 8); the walk checks whichever fires',
    'map049/ev001/p3/b17': 'arm on a rolled or computed value (var 102 != 8); the walk checks whichever fires',
    'map049/ev001/p3/b18': 'arm on a rolled or computed value (var 102 == 9); the walk checks whichever fires',
    'map049/ev001/p3/b19': 'arm on a rolled or computed value (var 102 != 9); the walk checks whichever fires',
    'map049/ev001/p3/b2': 'arm on a rolled or computed value (var 102 == 1); the walk checks whichever fires',
    'map049/ev001/p3/b20': 'arm on a rolled or computed value (var 102 == 10); the walk checks whichever fires',
    'map049/ev001/p3/b21': 'arm on a rolled or computed value (var 102 != 10); the walk checks whichever fires',
    'map049/ev001/p3/b22': 'arm on a rolled or computed value (var 102 == 11); the walk checks whichever fires',
    'map049/ev001/p3/b23': 'arm on a rolled or computed value (var 102 != 11); the walk checks whichever fires',
    'map049/ev001/p3/b24': 'arm on a rolled or computed value (var 102 == 12); the walk checks whichever fires',
    'map049/ev001/p3/b25': 'arm on a rolled or computed value (var 102 != 12); the walk checks whichever fires',
    'map049/ev001/p3/b3': 'arm on a rolled or computed value (var 102 != 1); the walk checks whichever fires',
    'map049/ev001/p3/b4': 'arm on a rolled or computed value (var 102 == 2); the walk checks whichever fires',
    'map049/ev001/p3/b5': 'arm on a rolled or computed value (var 102 != 2); the walk checks whichever fires',
    'map049/ev001/p3/b6': 'arm on a rolled or computed value (var 102 == 3); the walk checks whichever fires',
    'map049/ev001/p3/b7': 'arm on a rolled or computed value (var 102 != 3); the walk checks whichever fires',
    'map049/ev001/p3/b8': 'arm on a rolled or computed value (var 102 == 4); the walk checks whichever fires',
    'map049/ev001/p3/b9': 'arm on a rolled or computed value (var 102 != 4); the walk checks whichever fires',
}

CHAPTER = ch01.build()
