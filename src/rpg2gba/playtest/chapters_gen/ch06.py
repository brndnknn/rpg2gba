"""GENERATED -- do not edit.

Chapter CH06. Regenerate with `python -m rpg2gba.beat_gen generate --chapter CH06`.
"""

from __future__ import annotations

from rpg2gba.playtest.archetypes.arrival_nudge import arrival_nudge_beat
from rpg2gba.playtest.archetypes.flavour_npc import flavour_npc_beat
from rpg2gba.playtest.archetypes.generic import generic_beat, seam_beat, stair_beat, transit_beat
from rpg2gba.playtest.archetypes.item_ball import item_ball_beats
from rpg2gba.playtest.archetypes.trainer import trainer_beats
from rpg2gba.playtest.archetypes.warp import warp_beat
from rpg2gba.playtest.chapter import ChapterBuilder
from rpg2gba.playtest.whiteout import whiteout_fork_beat

ch06 = ChapterBuilder('CH06', doc='beat_gen-generated module for CH06', predecessor='CH05', suite='gen')

warp_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m037e002_warp',
    group='m037e002_warp',
    dest_map_constant='MAP_NOWTOCH_CITY',
    direction='UP',
    end_side='dest',
    event_id=2,
    manifest_chapter_id='CH05',
    map_constant='MAP_PASSAGE_CAVE_2F',
    map_id=37,
    mechanism='threshold',
    start_side='origin',
)

arrival_nudge_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e019_arrival_nudge',
    group='m040e019_arrival_nudge',
    event_id=19,
    from_event_id=2,
    from_map_constant='MAP_PASSAGE_CAVE_2F',
    map_constant='MAP_NOWTOCH_CITY',
    map_id=40,
)

generic_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e019_arrival_nudge_arms',
    group='m040e019_arrival_nudge',
    rows=('map040/ev019/p3/b0',),
    skip_claimed=True,
)

warp_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e019p0_warp',
    group='m040e019p0_warp',
    dest_map_constant='MAP_PASSAGE_CAVE_2F',
    direction='UP',
    end_side='origin',
    event_id=19,
    map_constant='MAP_NOWTOCH_CITY',
    map_id=40,
    mechanism='threshold',
    page_idx=0,
    return_direction='UP',
    start_side='origin',
)

stair_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040stair57x43',
    group='m040stair57x43',
    rows=('map040/terrain/stairs/57,43', 'map040/terrain/stairs/57,44', 'map040/terrain/stairs/58,45', 'map040/terrain/stairs/58,46'),
    approach_prefer='east',
)

flavour_npc_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e025p0_flavour_npc',
    group='m040e025p0_flavour_npc',
    approach_prefer='south',
    event_id=25,
    map_constant='MAP_NOWTOCH_CITY',
    map_id=40,
    toggled_page_idx=None,
    variant='toggling',
)

flavour_npc_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e025p1_flavour_npc',
    group='m040e025p1_flavour_npc',
    approach_prefer='south',
    event_id=25,
    map_constant='MAP_NOWTOCH_CITY',
    map_id=40,
    page_idx=1,
    variant='plain',
)

flavour_npc_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e001_flavour_npc',
    group='m040e001_flavour_npc',
    approach_prefer='east',
    event_id=1,
    map_constant='MAP_NOWTOCH_CITY',
    map_id=40,
    variant='plain',
)

flavour_npc_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e003_flavour_npc',
    group='m040e003_flavour_npc',
    approach_prefer='south',
    event_id=3,
    map_constant='MAP_NOWTOCH_CITY',
    map_id=40,
    variant='plain',
)

flavour_npc_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e051_flavour_npc',
    group='m040e051_flavour_npc',
    approach_prefer='west',
    event_id=51,
    map_constant='MAP_NOWTOCH_CITY',
    map_id=40,
    variant='plain',
)

flavour_npc_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e012_flavour_npc',
    group='m040e012_flavour_npc',
    approach_prefer='north',
    event_id=12,
    map_constant='MAP_NOWTOCH_CITY',
    map_id=40,
    variant='plain',
)

warp_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e027_warp',
    group='m040e027_warp',
    dest_map_constant='MAP_NOWTOCH_CITY_INTERIORS_1',
    direction='UP',
    end_side='dest',
    event_id=27,
    map_constant='MAP_NOWTOCH_CITY',
    map_id=40,
    mechanism='threshold',
    start_side='origin',
)

generic_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m046e017p0',
    group='m046e017p0',
    rows=('map046/ev017/p0',),
    approach_prefer='east',
)

flavour_npc_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m046e017_flavour_npc',
    group='m046e017_flavour_npc',
    approach_prefer='east',
    event_id=17,
    map_constant='MAP_NOWTOCH_CITY_INTERIORS_1',
    map_id=46,
    page_idx=1,
    variant='plain',
)

flavour_npc_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m046e015_flavour_npc',
    group='m046e015_flavour_npc',
    approach_prefer='south',
    event_id=15,
    map_constant='MAP_NOWTOCH_CITY_INTERIORS_1',
    map_id=46,
    variant='plain',
)

flavour_npc_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m046e019p0_flavour_npc',
    group='m046e019p0_flavour_npc',
    approach_prefer='north',
    event_id=19,
    map_constant='MAP_NOWTOCH_CITY_INTERIORS_1',
    map_id=46,
    toggled_page_idx=None,
    variant='toggling',
)

flavour_npc_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m046e019p1_flavour_npc',
    group='m046e019p1_flavour_npc',
    approach_prefer='north',
    event_id=19,
    map_constant='MAP_NOWTOCH_CITY_INTERIORS_1',
    map_id=46,
    page_idx=1,
    toggled_page_idx=None,
    variant='toggling',
)

flavour_npc_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m046e032_flavour_npc',
    group='m046e032_flavour_npc',
    approach_prefer='south',
    event_id=32,
    map_constant='MAP_NOWTOCH_CITY_INTERIORS_1',
    map_id=46,
    variant='plain',
)

flavour_npc_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m046e033_flavour_npc',
    group='m046e033_flavour_npc',
    approach_prefer='south',
    event_id=33,
    map_constant='MAP_NOWTOCH_CITY_INTERIORS_1',
    map_id=46,
    variant='plain',
)

warp_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m046e021_warp',
    group='m046e021_warp',
    dest_map_constant='MAP_NOWTOCH_CITY_INTERIORS_1',
    direction='LEFT',
    end_side='dest',
    event_id=21,
    map_constant='MAP_NOWTOCH_CITY_INTERIORS_1',
    map_id=46,
    mechanism='threshold',
    start_side='origin',
)

flavour_npc_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m046e035_flavour_npc',
    group='m046e035_flavour_npc',
    approach_prefer='south',
    event_id=35,
    map_constant='MAP_NOWTOCH_CITY_INTERIORS_1',
    map_id=46,
    variant='plain',
)

flavour_npc_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m046e034_flavour_npc',
    group='m046e034_flavour_npc',
    approach_prefer='south',
    event_id=34,
    map_constant='MAP_NOWTOCH_CITY_INTERIORS_1',
    map_id=46,
    variant='plain',
)

generic_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m046e020p0',
    group='m046e020p0',
    rows=('map046/ev020/p0',),
    approach_prefer='north',
)

flavour_npc_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m046e020_flavour_npc',
    group='m046e020_flavour_npc',
    approach_prefer='north',
    event_id=20,
    map_constant='MAP_NOWTOCH_CITY_INTERIORS_1',
    map_id=46,
    page_idx=1,
    variant='plain',
)

warp_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m046e022_warp',
    group='m046e022_warp',
    dest_map_constant='MAP_NOWTOCH_CITY_INTERIORS_1',
    direction='RIGHT',
    end_side='dest',
    event_id=22,
    map_constant='MAP_NOWTOCH_CITY_INTERIORS_1',
    map_id=46,
    mechanism='threshold',
    start_side='origin',
)

warp_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m046e018_warp',
    group='m046e018_warp',
    dest_map_constant='MAP_NOWTOCH_CITY',
    direction='DOWN',
    end_side='dest',
    event_id=18,
    map_constant='MAP_NOWTOCH_CITY_INTERIORS_1',
    map_id=46,
    mechanism='threshold',
    start_side='origin',
)

arrival_nudge_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e027_arrival_nudge',
    group='m040e027_arrival_nudge',
    event_id=27,
    from_event_id=18,
    from_map_constant='MAP_NOWTOCH_CITY_INTERIORS_1',
    map_constant='MAP_NOWTOCH_CITY',
    map_id=40,
)

generic_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e027_arrival_nudge_arms',
    group='m040e027_arrival_nudge',
    rows=('map040/ev027/p1/b0',),
    skip_claimed=True,
)

warp_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e055_warp',
    group='m040e055_warp',
    dest_map_constant='MAP_NOWTOCH_CITY_INTERIORS_1',
    direction='UP',
    end_side='origin',
    event_id=55,
    map_constant='MAP_NOWTOCH_CITY',
    map_id=40,
    mechanism='threshold',
    return_direction='DOWN',
    start_side='origin',
)

flavour_npc_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e009_flavour_npc',
    group='m040e009_flavour_npc',
    approach_prefer='south',
    event_id=9,
    map_constant='MAP_NOWTOCH_CITY',
    map_id=40,
    variant='plain',
)

flavour_npc_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e007_flavour_npc',
    group='m040e007_flavour_npc',
    approach_prefer='east',
    event_id=7,
    map_constant='MAP_NOWTOCH_CITY',
    map_id=40,
    variant='plain',
)

flavour_npc_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e008_flavour_npc',
    group='m040e008_flavour_npc',
    approach_prefer='south',
    event_id=8,
    map_constant='MAP_NOWTOCH_CITY',
    map_id=40,
    variant='plain',
)

flavour_npc_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e006_flavour_npc',
    group='m040e006_flavour_npc',
    approach_prefer='west',
    event_id=6,
    map_constant='MAP_NOWTOCH_CITY',
    map_id=40,
    variant='plain',
)

flavour_npc_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e026_flavour_npc',
    group='m040e026_flavour_npc',
    approach_prefer='south',
    event_id=26,
    map_constant='MAP_NOWTOCH_CITY',
    map_id=40,
    variant='plain',
)

item_ball_beats(
    ch06,
    chapter_id='CH06',
    beat_prefix='m040e060_item_ball',
    group='m040e060_item_ball',
    approach_prefer='south',
    event_id=60,
    item='ITEM_X_ATTACK',
    map_constant='MAP_NOWTOCH_CITY',
    map_id=40,
    negative_beat=True,
)

generic_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e060_item_ball_arms',
    group='m040e060_item_ball',
    rows=('map040/ev060/p0/b0',),
    approach_prefer='south',
    skip_claimed=True,
)

flavour_npc_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e050_flavour_npc',
    group='m040e050_flavour_npc',
    approach_prefer='south',
    event_id=50,
    map_constant='MAP_NOWTOCH_CITY',
    map_id=40,
    variant='plain',
)

flavour_npc_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e023_flavour_npc',
    group='m040e023_flavour_npc',
    approach_prefer='north',
    event_id=23,
    map_constant='MAP_NOWTOCH_CITY',
    map_id=40,
    variant='plain',
)

flavour_npc_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e063p0_flavour_npc',
    group='m040e063p0_flavour_npc',
    approach_prefer='north',
    event_id=63,
    map_constant='MAP_NOWTOCH_CITY',
    map_id=40,
    toggled_page_idx=None,
    variant='toggling',
)

flavour_npc_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e063p1_flavour_npc',
    group='m040e063p1_flavour_npc',
    approach_prefer='north',
    event_id=63,
    map_constant='MAP_NOWTOCH_CITY',
    map_id=40,
    page_idx=1,
    toggled_page_idx=None,
    variant='toggling',
)

flavour_npc_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e061_flavour_npc',
    group='m040e061_flavour_npc',
    approach_prefer='west',
    event_id=61,
    map_constant='MAP_NOWTOCH_CITY',
    map_id=40,
    variant='plain',
)

flavour_npc_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e062_flavour_npc',
    group='m040e062_flavour_npc',
    approach_prefer='north',
    event_id=62,
    map_constant='MAP_NOWTOCH_CITY',
    map_id=40,
    variant='plain',
)

flavour_npc_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e139_flavour_npc',
    group='m040e139_flavour_npc',
    approach_prefer='east',
    event_id=139,
    map_constant='MAP_NOWTOCH_CITY',
    map_id=40,
    variant='plain',
)

flavour_npc_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e022_flavour_npc',
    group='m040e022_flavour_npc',
    approach_prefer='north',
    event_id=22,
    map_constant='MAP_NOWTOCH_CITY',
    map_id=40,
    variant='plain',
)

warp_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e013_warp',
    group='m040e013_warp',
    dest_map_constant='MAP_NOWTOCH_CITY_POKEMON_CENTER',
    direction='UP',
    end_side='dest',
    event_id=13,
    map_constant='MAP_NOWTOCH_CITY',
    map_id=40,
    mechanism='threshold',
    start_side='origin',
)

generic_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m043e007p0',
    group='m043e007p0',
    rows=('map043/ev007/p0', 'map043/ev007/p0/b0', 'map043/ev007/p0/b1', 'map043/ev007/p0/b2', 'map043/ev007/p0/b3'),
    approach_prefer='west',
    random_arms=(('map043/ev007/p0/b0', ((102, '==', 2),)), ('map043/ev007/p0/b1', ((102, '!=', 2),)), ('map043/ev007/p0/b2', ((102, '!=', 2), (102, '==', 1))), ('map043/ev007/p0/b3', ((102, '!=', 2), (102, '!=', 1)))),
)

generic_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m043e003p0',
    group='m043e003p0',
    rows=('map043/ev003/p0',),
    approach_prefer='south',
)

generic_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m043e001p0_c5a0',
    group='m043e001p0',
    rows=('map043/ev001/p0/b0', 'map043/ev001/p0/b2'),
    approach_prefer='south',
    choice_answers=((5, 0),),
    walk_rows=('map043/ev001/p0',),
)

generic_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m043e001p0',
    group='m043e001p0',
    rows=('map043/ev001/p0', 'map043/ev001/p0/b3'),
    approach_prefer='south',
    choice_answers=((5, 1),),
)

generic_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m043e012p0',
    group='m043e012p0',
    rows=('map043/ev012/p0',),
    approach_prefer='south',
)

generic_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m043e008p0',
    group='m043e008p0',
    rows=('map043/ev008/p0', 'map043/ev008/p0/b0', 'map043/ev008/p0/b1', 'map043/ev008/p0/b2', 'map043/ev008/p0/b3'),
    approach_prefer='south',
    random_arms=(('map043/ev008/p0/b0', ((102, '==', 2),)), ('map043/ev008/p0/b1', ((102, '!=', 2),)), ('map043/ev008/p0/b2', ((102, '!=', 2), (102, '==', 1))), ('map043/ev008/p0/b3', ((102, '!=', 2), (102, '!=', 1)))),
)

generic_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m043e013p0',
    group='m043e013p0',
    rows=('map043/ev013/p0',),
    approach_prefer='south',
)

generic_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m043e010p0',
    group='m043e010p0',
    rows=('map043/ev010/p0',),
    approach_prefer='south',
)

generic_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m043e011p0',
    group='m043e011p0',
    rows=('map043/ev011/p0',),
    approach_prefer='south',
)

generic_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m043e004p0',
    group='m043e004p0',
    rows=('map043/ev004/p0', 'map043/ev004/p0/b0', 'map043/ev004/p0/b1', 'map043/ev004/p0/b2', 'map043/ev004/p0/b3'),
    approach_prefer='north',
    random_arms=(('map043/ev004/p0/b0', ((102, '==', 2),)), ('map043/ev004/p0/b1', ((102, '!=', 2),)), ('map043/ev004/p0/b2', ((102, '!=', 2), (102, '==', 1))), ('map043/ev004/p0/b3', ((102, '!=', 2), (102, '!=', 1)))),
)

warp_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m043e002_warp',
    group='m043e002_warp',
    dest_map_constant='MAP_NOWTOCH_CITY',
    direction='DOWN',
    end_side='origin',
    event_id=2,
    map_constant='MAP_NOWTOCH_CITY_POKEMON_CENTER',
    map_id=43,
    mechanism='threshold',
    return_direction='UP',
    start_side='origin',
)

warp_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m043e009_warp',
    group='m043e009_warp',
    dest_map_constant='MAP_NOWTOCH_CITY',
    direction='DOWN',
    end_side='dest',
    event_id=9,
    map_constant='MAP_NOWTOCH_CITY_POKEMON_CENTER',
    map_id=43,
    mechanism='threshold',
    start_side='origin',
)

transit_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e013_arrival_nudge_transit',
    group='m040e013_arrival_nudge',
    hops=(('MAP_NOWTOCH_CITY', 24, 56, 'UP', 'MAP_NOWTOCH_CITY_POKEMON_CENTER'), ('MAP_NOWTOCH_CITY_POKEMON_CENTER', 7, 18, 'DOWN', 'MAP_NOWTOCH_CITY')),
)

arrival_nudge_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e013_arrival_nudge',
    group='m040e013_arrival_nudge',
    event_id=13,
    from_event_id=2,
    from_map_constant='MAP_NOWTOCH_CITY_POKEMON_CENTER',
    map_constant='MAP_NOWTOCH_CITY',
    map_id=40,
)

generic_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e013_arrival_nudge_arms',
    group='m040e013_arrival_nudge',
    rows=('map040/ev013/p1/b0',),
    skip_claimed=True,
)

warp_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e066_warp',
    group='m040e066_warp',
    dest_map_constant='MAP_NOWTOCH_CITY_LEADER_HOUSE',
    direction='UP',
    end_side='dest',
    event_id=66,
    map_constant='MAP_NOWTOCH_CITY',
    map_id=40,
    mechanism='threshold',
    start_side='origin',
)

generic_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m047e005p0',
    group='m047e005p0',
    rows=('map047/ev005/p0',),
    approach_prefer='east',
)

flavour_npc_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m047e011p0_flavour_npc',
    group='m047e011p0_flavour_npc',
    approach_prefer='north',
    event_id=11,
    map_constant='MAP_NOWTOCH_CITY_LEADER_HOUSE',
    map_id=47,
    toggled_page_idx=None,
    variant='toggling',
)

flavour_npc_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m047e011p1_flavour_npc',
    group='m047e011p1_flavour_npc',
    approach_prefer='north',
    event_id=11,
    map_constant='MAP_NOWTOCH_CITY_LEADER_HOUSE',
    map_id=47,
    page_idx=1,
    toggled_page_idx=None,
    variant='toggling',
)

flavour_npc_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m047e017_flavour_npc',
    group='m047e017_flavour_npc',
    approach_prefer='south',
    event_id=17,
    map_constant='MAP_NOWTOCH_CITY_LEADER_HOUSE',
    map_id=47,
    variant='plain',
)

flavour_npc_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m047e015_flavour_npc',
    group='m047e015_flavour_npc',
    approach_prefer='south',
    event_id=15,
    map_constant='MAP_NOWTOCH_CITY_LEADER_HOUSE',
    map_id=47,
    variant='plain',
)

flavour_npc_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m047e014_flavour_npc',
    group='m047e014_flavour_npc',
    approach_prefer='south',
    event_id=14,
    map_constant='MAP_NOWTOCH_CITY_LEADER_HOUSE',
    map_id=47,
    variant='plain',
)

flavour_npc_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m047e018_flavour_npc',
    group='m047e018_flavour_npc',
    approach_prefer='south',
    event_id=18,
    map_constant='MAP_NOWTOCH_CITY_LEADER_HOUSE',
    map_id=47,
    variant='plain',
)

flavour_npc_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m047e016_flavour_npc',
    group='m047e016_flavour_npc',
    approach_prefer='south',
    event_id=16,
    map_constant='MAP_NOWTOCH_CITY_LEADER_HOUSE',
    map_id=47,
    variant='plain',
)

warp_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m047e003_warp',
    group='m047e003_warp',
    dest_map_constant='MAP_NOWTOCH_CITY',
    direction='DOWN',
    end_side='dest',
    event_id=3,
    map_constant='MAP_NOWTOCH_CITY_LEADER_HOUSE',
    map_id=47,
    mechanism='threshold',
    start_side='origin',
)

arrival_nudge_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e066_arrival_nudge',
    group='m040e066_arrival_nudge',
    event_id=66,
    from_event_id=3,
    from_map_constant='MAP_NOWTOCH_CITY_LEADER_HOUSE',
    map_constant='MAP_NOWTOCH_CITY',
    map_id=40,
)

generic_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e066_arrival_nudge_arms',
    group='m040e066_arrival_nudge',
    rows=('map040/ev066/p1/b0',),
    skip_claimed=True,
)

generic_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e011p0',
    group='m040e011p0',
    rows=('map040/ev011/p0', 'map040/ev011/p0/b0', 'map040/ev011/p0/b1'),
    approach_prefer='north',
    random_arms=(('map040/ev011/p0/b0', ((102, '==', 1),)), ('map040/ev011/p0/b1', ((102, '!=', 1),))),
)

warp_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e015_warp',
    group='m040e015_warp',
    dest_map_constant='MAP_NOWTOCH_CITY_POKEMART',
    direction='UP',
    end_side='dest',
    event_id=15,
    map_constant='MAP_NOWTOCH_CITY',
    map_id=40,
    mechanism='threshold',
    start_side='origin',
)

generic_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m041e002p0',
    group='m041e002p0',
    rows=('map041/ev002/p0',),
    approach_prefer='south',
)

generic_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m041e004p0',
    group='m041e004p0',
    rows=('map041/ev004/p0',),
    approach_prefer='east',
)

warp_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m041e001_warp',
    group='m041e001_warp',
    dest_map_constant='MAP_NOWTOCH_CITY',
    direction='DOWN',
    end_side='dest',
    event_id=1,
    map_constant='MAP_NOWTOCH_CITY_POKEMART',
    map_id=41,
    mechanism='threshold',
    start_side='origin',
)

arrival_nudge_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e015_arrival_nudge',
    group='m040e015_arrival_nudge',
    event_id=15,
    from_event_id=1,
    from_map_constant='MAP_NOWTOCH_CITY_POKEMART',
    map_constant='MAP_NOWTOCH_CITY',
    map_id=40,
)

generic_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e015_arrival_nudge_arms',
    group='m040e015_arrival_nudge',
    rows=('map040/ev015/p1/b0',),
    skip_claimed=True,
)

warp_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e065_warp',
    group='m040e065_warp',
    dest_map_constant='MAP_NOWTOCH_CITY_INTERIORS_1',
    direction='UP',
    end_side='dest',
    event_id=65,
    map_constant='MAP_NOWTOCH_CITY',
    map_id=40,
    mechanism='threshold',
    start_side='origin',
)

generic_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m046e024p0',
    group='m046e024p0',
    rows=('map046/ev024/p0',),
    approach_prefer='west',
)

flavour_npc_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m046e024_flavour_npc',
    group='m046e024_flavour_npc',
    approach_prefer='west',
    event_id=24,
    map_constant='MAP_NOWTOCH_CITY_INTERIORS_1',
    map_id=46,
    page_idx=1,
    variant='plain',
)

flavour_npc_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m046e036_flavour_npc',
    group='m046e036_flavour_npc',
    approach_prefer='south',
    event_id=36,
    map_constant='MAP_NOWTOCH_CITY_INTERIORS_1',
    map_id=46,
    variant='plain',
)

warp_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m046e025_warp',
    group='m046e025_warp',
    dest_map_constant='MAP_NOWTOCH_CITY_INTERIORS_1',
    direction='RIGHT',
    end_side='dest',
    event_id=25,
    map_constant='MAP_NOWTOCH_CITY_INTERIORS_1',
    map_id=46,
    mechanism='threshold',
    start_side='origin',
)

flavour_npc_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m046e031p0_flavour_npc',
    group='m046e031p0_flavour_npc',
    approach_prefer='north',
    event_id=31,
    map_constant='MAP_NOWTOCH_CITY_INTERIORS_1',
    map_id=46,
    toggled_page_idx=None,
    variant='toggling',
)

flavour_npc_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m046e031p1_flavour_npc',
    group='m046e031p1_flavour_npc',
    approach_prefer='north',
    event_id=31,
    map_constant='MAP_NOWTOCH_CITY_INTERIORS_1',
    map_id=46,
    page_idx=1,
    toggled_page_idx=None,
    variant='toggling',
)

warp_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m046e026_warp',
    group='m046e026_warp',
    dest_map_constant='MAP_NOWTOCH_CITY_INTERIORS_1',
    direction='RIGHT',
    end_side='dest',
    event_id=26,
    map_constant='MAP_NOWTOCH_CITY_INTERIORS_1',
    map_id=46,
    mechanism='threshold',
    start_side='origin',
)

flavour_npc_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m046e030_flavour_npc',
    group='m046e030_flavour_npc',
    approach_prefer='north',
    event_id=30,
    map_constant='MAP_NOWTOCH_CITY_INTERIORS_1',
    map_id=46,
    variant='plain',
)

flavour_npc_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m046e038_flavour_npc',
    group='m046e038_flavour_npc',
    approach_prefer='south',
    event_id=38,
    map_constant='MAP_NOWTOCH_CITY_INTERIORS_1',
    map_id=46,
    variant='plain',
)

flavour_npc_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m046e037_flavour_npc',
    group='m046e037_flavour_npc',
    approach_prefer='south',
    event_id=37,
    map_constant='MAP_NOWTOCH_CITY_INTERIORS_1',
    map_id=46,
    variant='plain',
)

flavour_npc_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m046e029_flavour_npc',
    group='m046e029_flavour_npc',
    approach_prefer='north',
    event_id=29,
    map_constant='MAP_NOWTOCH_CITY_INTERIORS_1',
    map_id=46,
    variant='plain',
)

flavour_npc_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m046e039_flavour_npc',
    group='m046e039_flavour_npc',
    approach_prefer='south',
    event_id=39,
    map_constant='MAP_NOWTOCH_CITY_INTERIORS_1',
    map_id=46,
    variant='plain',
)

warp_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m046e028_warp',
    group='m046e028_warp',
    dest_map_constant='MAP_NOWTOCH_CITY_INTERIORS_1',
    direction='LEFT',
    end_side='dest',
    event_id=28,
    map_constant='MAP_NOWTOCH_CITY_INTERIORS_1',
    map_id=46,
    mechanism='threshold',
    start_side='origin',
)

warp_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m046e027_warp',
    group='m046e027_warp',
    dest_map_constant='MAP_NOWTOCH_CITY_INTERIORS_1',
    direction='LEFT',
    end_side='dest',
    event_id=27,
    map_constant='MAP_NOWTOCH_CITY_INTERIORS_1',
    map_id=46,
    mechanism='threshold',
    start_side='origin',
)

warp_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m046e023_warp',
    group='m046e023_warp',
    dest_map_constant='MAP_NOWTOCH_CITY',
    direction='DOWN',
    end_side='dest',
    event_id=23,
    map_constant='MAP_NOWTOCH_CITY_INTERIORS_1',
    map_id=46,
    mechanism='threshold',
    start_side='origin',
)

arrival_nudge_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e065_arrival_nudge',
    group='m040e065_arrival_nudge',
    event_id=65,
    from_event_id=23,
    from_map_constant='MAP_NOWTOCH_CITY_INTERIORS_1',
    map_constant='MAP_NOWTOCH_CITY',
    map_id=40,
)

generic_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e065_arrival_nudge_arms',
    group='m040e065_arrival_nudge',
    rows=('map040/ev065/p1/b0',),
    skip_claimed=True,
)

warp_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e016_warp',
    group='m040e016_warp',
    dest_map_constant='MAP_NOWTOCH_CITY_INTERIORS_1',
    direction='UP',
    end_side='dest',
    event_id=16,
    map_constant='MAP_NOWTOCH_CITY',
    map_id=40,
    mechanism='threshold',
    start_side='origin',
)

warp_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m046e010_warp',
    group='m046e010_warp',
    dest_map_constant='MAP_NOWTOCH_CITY_INTERIORS_1',
    direction='RIGHT',
    end_side='dest',
    event_id=10,
    map_constant='MAP_NOWTOCH_CITY_INTERIORS_1',
    map_id=46,
    mechanism='threshold',
    start_side='origin',
)

generic_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m046e006p0',
    group='m046e006p0',
    rows=('map046/ev006/p0', 'map046/ev006/p0/b0', 'map046/ev006/p0/b1'),
    approach_prefer='west',
    archetype=(('map046/ev006/p0', 'flavour_npc'),),
    random_arms=(('map046/ev006/p0/b0', ((102, '==', 1),)), ('map046/ev006/p0/b1', ((102, '!=', 1),))),
)

flavour_npc_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m046e007_flavour_npc',
    group='m046e007_flavour_npc',
    approach_prefer='north',
    event_id=7,
    map_constant='MAP_NOWTOCH_CITY_INTERIORS_1',
    map_id=46,
    variant='plain',
)

generic_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m046e008p0',
    group='m046e008p0',
    rows=('map046/ev008/p0', 'map046/ev008/p0/b0', 'map046/ev008/p0/b1'),
    approach_prefer='south',
    archetype=(('map046/ev008/p0', 'flavour_npc'),),
    random_arms=(('map046/ev008/p0/b0', ((102, '==', 1),)), ('map046/ev008/p0/b1', ((102, '!=', 1),))),
)

flavour_npc_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m046e005_flavour_npc',
    group='m046e005_flavour_npc',
    approach_prefer='north',
    event_id=5,
    map_constant='MAP_NOWTOCH_CITY_INTERIORS_1',
    map_id=46,
    variant='plain',
)

warp_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m046e012_warp',
    group='m046e012_warp',
    dest_map_constant='MAP_NOWTOCH_CITY_INTERIORS_1',
    direction='RIGHT',
    end_side='dest',
    event_id=12,
    map_constant='MAP_NOWTOCH_CITY_INTERIORS_1',
    map_id=46,
    mechanism='threshold',
    start_side='origin',
)

flavour_npc_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m046e011_flavour_npc',
    group='m046e011_flavour_npc',
    approach_prefer='south',
    event_id=11,
    map_constant='MAP_NOWTOCH_CITY_INTERIORS_1',
    map_id=46,
    variant='plain',
)

generic_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m046e014p0',
    group='m046e014p0',
    rows=('map046/ev014/p0', 'map046/ev014/p0/b5'),
    approach_prefer='north',
    choice_answers=((2, 1),),
)

warp_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m046e013_warp',
    group='m046e013_warp',
    dest_map_constant='MAP_NOWTOCH_CITY_INTERIORS_1',
    direction='LEFT',
    end_side='dest',
    event_id=13,
    map_constant='MAP_NOWTOCH_CITY_INTERIORS_1',
    map_id=46,
    mechanism='threshold',
    start_side='origin',
)

warp_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m046e009_warp',
    group='m046e009_warp',
    dest_map_constant='MAP_NOWTOCH_CITY_INTERIORS_1',
    direction='LEFT',
    end_side='dest',
    event_id=9,
    map_constant='MAP_NOWTOCH_CITY_INTERIORS_1',
    map_id=46,
    mechanism='threshold',
    start_side='origin',
)

warp_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m046e001_warp',
    group='m046e001_warp',
    dest_map_constant='MAP_NOWTOCH_CITY',
    direction='DOWN',
    end_side='dest',
    event_id=1,
    map_constant='MAP_NOWTOCH_CITY_INTERIORS_1',
    map_id=46,
    mechanism='threshold',
    start_side='origin',
)

arrival_nudge_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e016_arrival_nudge',
    group='m040e016_arrival_nudge',
    event_id=16,
    from_event_id=1,
    from_map_constant='MAP_NOWTOCH_CITY_INTERIORS_1',
    map_constant='MAP_NOWTOCH_CITY',
    map_id=40,
)

generic_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e016_arrival_nudge_arms',
    group='m040e016_arrival_nudge',
    rows=('map040/ev016/p1/b0',),
    skip_claimed=True,
)

warp_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e064_warp',
    group='m040e064_warp',
    dest_map_constant='MAP_NOWTOCH_CITY_INTERIORS_1',
    direction='UP',
    end_side='dest',
    event_id=64,
    map_constant='MAP_NOWTOCH_CITY',
    map_id=40,
    mechanism='threshold',
    start_side='origin',
)

flavour_npc_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m046e003_flavour_npc',
    group='m046e003_flavour_npc',
    approach_prefer='west',
    event_id=3,
    map_constant='MAP_NOWTOCH_CITY_INTERIORS_1',
    map_id=46,
    variant='plain',
)

flavour_npc_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m046e040_flavour_npc',
    group='m046e040_flavour_npc',
    approach_prefer='south',
    event_id=40,
    map_constant='MAP_NOWTOCH_CITY_INTERIORS_1',
    map_id=46,
    variant='plain',
)

warp_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m046e004_warp',
    group='m046e004_warp',
    dest_map_constant='MAP_NOWTOCH_CITY',
    direction='DOWN',
    end_side='dest',
    event_id=4,
    map_constant='MAP_NOWTOCH_CITY_INTERIORS_1',
    map_id=46,
    mechanism='threshold',
    start_side='origin',
)

arrival_nudge_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e064_arrival_nudge',
    group='m040e064_arrival_nudge',
    event_id=64,
    from_event_id=4,
    from_map_constant='MAP_NOWTOCH_CITY_INTERIORS_1',
    map_constant='MAP_NOWTOCH_CITY',
    map_id=40,
)

generic_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e064_arrival_nudge_arms',
    group='m040e064_arrival_nudge',
    rows=('map040/ev064/p1/b0',),
    skip_claimed=True,
)

generic_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e018p0',
    group='m040e018p0',
    rows=('map040/ev018/p0', 'map040/ev018/p0/b0'),
    approach_prefer='south',
)

flavour_npc_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e018_flavour_npc',
    group='m040e018_flavour_npc',
    approach_prefer='south',
    event_id=18,
    map_constant='MAP_NOWTOCH_CITY',
    map_id=40,
    moved_by=('map040/ev141/p0',),
    page_idx=1,
    variant='plain',
)

warp_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e017p0_warp',
    group='m040e017p0_warp',
    dest_map_constant='MAP_NOWTOCH_CITY_LEADER_HOUSE',
    direction='UP',
    end_side='origin',
    event_id=17,
    map_constant='MAP_NOWTOCH_CITY',
    map_id=40,
    mechanism='threshold',
    page_idx=0,
    return_direction='DOWN',
    start_side='origin',
)

generic_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e017p0_warp_arms',
    group='m040e017p0_warp',
    rows=('map040/ev017/p0/b0',),
    approach_prefer='south',
    skip_claimed=True,
)

transit_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m047e013p0_transit',
    group='m047e013p0',
    hops=(('MAP_NOWTOCH_CITY', 47, 62, 'UP', 'MAP_NOWTOCH_CITY_LEADER_HOUSE'),),
)

generic_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m047e013p0',
    group='m047e013p0',
    rows=('map047/ev013/p0',),
    approach_prefer='arrive@(5,9)',
)

generic_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m047e013p1',
    group='m047e013p1',
    rows=('map047/ev013/p1',),
    approach_prefer='north',
)

flavour_npc_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m047e008_flavour_npc',
    group='m047e008_flavour_npc',
    approach_prefer='south',
    event_id=8,
    map_constant='MAP_NOWTOCH_CITY_LEADER_HOUSE',
    map_id=47,
    variant='plain',
)

flavour_npc_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m047e007_flavour_npc',
    group='m047e007_flavour_npc',
    approach_prefer='south',
    event_id=7,
    map_constant='MAP_NOWTOCH_CITY_LEADER_HOUSE',
    map_id=47,
    variant='plain',
)

flavour_npc_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m047e006_flavour_npc',
    group='m047e006_flavour_npc',
    approach_prefer='south',
    event_id=6,
    map_constant='MAP_NOWTOCH_CITY_LEADER_HOUSE',
    map_id=47,
    variant='plain',
)

warp_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m047e001_warp',
    group='m047e001_warp',
    dest_map_constant='MAP_NOWTOCH_CITY',
    direction='DOWN',
    end_side='dest',
    event_id=1,
    map_constant='MAP_NOWTOCH_CITY_LEADER_HOUSE',
    map_id=47,
    mechanism='threshold',
    start_side='origin',
)

arrival_nudge_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e017_arrival_nudge',
    group='m040e017_arrival_nudge',
    event_id=17,
    from_event_id=1,
    from_map_constant='MAP_NOWTOCH_CITY_LEADER_HOUSE',
    map_constant='MAP_NOWTOCH_CITY',
    map_id=40,
)

generic_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e017_arrival_nudge_arms',
    group='m040e017_arrival_nudge',
    rows=('map040/ev017/p2/b0',),
    skip_claimed=True,
)

warp_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e017p1_warp',
    group='m040e017p1_warp',
    dest_map_constant='MAP_NOWTOCH_CITY_LEADER_HOUSE',
    direction='UP',
    end_side='origin',
    event_id=17,
    map_constant='MAP_NOWTOCH_CITY',
    map_id=40,
    mechanism='threshold',
    page_idx=1,
    return_direction='DOWN',
    start_side='origin',
)

generic_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e141p0',
    group='m040e141p0',
    rows=('map040/ev141/p0', 'map040/ev141/p0/b0', 'map040/ev141/p0/b1', 'map040/ev141/p0/b2'),
    approach_prefer='east',
)

generic_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e141p1',
    group='m040e141p1',
    rows=('map040/ev141/p1',),
    approach_prefer='east',
)

generic_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e018p2',
    group='m040e018p2',
    rows=('map040/ev018/p2',),
    approach_prefer='south',
)

warp_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e014_warp',
    group='m040e014_warp',
    dest_map_constant='MAP_NOWTOCH_CITY_GYM',
    direction='UP',
    end_side='dest',
    event_id=14,
    map_constant='MAP_NOWTOCH_CITY',
    map_id=40,
    mechanism='threshold',
    page_idx=1,
    start_side='origin',
)

generic_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m042e004p0',
    group='m042e004p0',
    rows=('map042/ev004/p0', 'map042/ev004/p0/b0'),
    approach_prefer='east',
)

flavour_npc_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m042e004p1_flavour_npc',
    group='m042e004p1_flavour_npc',
    approach_prefer='east',
    event_id=4,
    map_constant='MAP_NOWTOCH_CITY_GYM',
    map_id=42,
    page_idx=1,
    variant='plain',
)

trainer_beats(
    ch06,
    chapter_id='CH06',
    beat_prefix='m042e002_trainer',
    group='m042e002_trainer',
    approach_prefer='west',
    defeat_flag='TRAINER_FLAGS_START + TRAINER_JACK_8',
    deferred_retalks=('map042/ev002/p2',),
    double=False,
    event_id=2,
    map_constant='MAP_NOWTOCH_CITY_GYM',
    map_id=42,
    phone=False,
    retalk_pages=2,
    rider=False,
    trainer_const='TRAINER_JACK_8',
    trigger='event_touch',
)

generic_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m042e002_trainer_arms',
    group='m042e002_trainer',
    rows=('map042/ev002/p0/b0',),
    approach_prefer='west',
    skip_claimed=True,
)

trainer_beats(
    ch06,
    chapter_id='CH06',
    beat_prefix='m042e001_trainer',
    group='m042e001_trainer',
    approach_prefer='east',
    defeat_flag='TRAINER_FLAGS_START + TRAINER_MYLA_7',
    deferred_retalks=('map042/ev001/p2',),
    double=False,
    event_id=1,
    map_constant='MAP_NOWTOCH_CITY_GYM',
    map_id=42,
    phone=False,
    retalk_pages=2,
    rider=False,
    trainer_const='TRAINER_MYLA_7',
    trigger='event_touch',
)

generic_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m042e001_trainer_arms',
    group='m042e001_trainer',
    rows=('map042/ev001/p0/b0',),
    approach_prefer='east',
    skip_claimed=True,
)

generic_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m042e003p0',
    group='m042e003p0',
    rows=('map042/ev003/p0', 'map042/ev003/p0/b0', 'map042/ev003/p0/b1'),
    approach_prefer='south',
    archetype=(('map042/ev003/p0', 'trainer'),),
)

whiteout_fork_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m043_whiteout',
    group='m042e003p0',
    rows=('map043/ev001/p1',),
    heal_location_id='HEAL_LOCATION_NOWTOCH_CITY_POKEMON_CENTER',
)

generic_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m042e003p1',
    group='m042e003p1',
    rows=('map042/ev003/p1',),
    approach_prefer='south',
    archetype=(('map042/ev003/p1', 'trainer'),),
)

generic_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m042e001p2',
    group='m042e001p2',
    rows=('map042/ev001/p2',),
    approach_prefer='east',
    archetype=(('map042/ev001/p2', 'trainer'),),
)

generic_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m042e002p2',
    group='m042e002p2',
    rows=('map042/ev002/p2',),
    approach_prefer='west',
    archetype=(('map042/ev002/p2', 'trainer'),),
)

warp_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m042e005_warp',
    group='m042e005_warp',
    dest_map_constant='MAP_NOWTOCH_CITY',
    direction='DOWN',
    end_side='dest',
    event_id=5,
    map_constant='MAP_NOWTOCH_CITY_GYM',
    map_id=42,
    mechanism='threshold',
    start_side='origin',
)

arrival_nudge_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e014_arrival_nudge',
    group='m040e014_arrival_nudge',
    event_id=14,
    from_event_id=5,
    from_map_constant='MAP_NOWTOCH_CITY_GYM',
    map_constant='MAP_NOWTOCH_CITY',
    map_id=40,
)

generic_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e014_arrival_nudge_arms',
    group='m040e014_arrival_nudge',
    rows=('map040/ev014/p2/b0',),
    skip_claimed=True,
)

generic_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e018p3',
    group='m040e018p3',
    rows=('map040/ev018/p3',),
    approach_prefer='south',
)

generic_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e141p2',
    group='m040e141p2',
    rows=('map040/ev141/p2',),
    approach_prefer='east',
)

generic_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e019p1',
    group='m040e019p1',
    rows=('map040/ev019/p1',),
    approach_prefer='south',
)

generic_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e079p0',
    group='m040e079p0',
    rows=('map040/ev079/p0', 'map040/ev079/p0/b0', 'map040/ev079/p0/b1', 'map040/ev079/p0/b2', 'map040/ev079/p0/b4', 'map040/ev079/p0/b6'),
    approach_prefer='east',
    archetype=(('map040/ev079/p0', 'trainer'),),
)

warp_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e019p2_warp',
    group='m040e019p2_warp',
    dest_map_constant='MAP_PASSAGE_CAVE_2F',
    direction='UP',
    end_side='dest',
    event_id=19,
    map_constant='MAP_NOWTOCH_CITY',
    map_id=40,
    mechanism='threshold',
    page_idx=2,
    start_side='origin',
)

transit_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m046e002p0_transit',
    group='m046e002p0',
    hops=(('MAP_PASSAGE_CAVE_2F', 16, 6, 'UP', 'MAP_NOWTOCH_CITY'), ('MAP_NOWTOCH_CITY', 14, 36, 'UP', 'MAP_NOWTOCH_CITY_INTERIORS_1')),
)

generic_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m046e002p0',
    group='m046e002p0',
    rows=('map046/ev002/p0', 'map046/ev002/p0/b11'),
    approach_prefer='south',
    choice_answers=((4, 1),),
)

transit_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e079p1_transit',
    group='m040e079p1',
    hops=(('MAP_NOWTOCH_CITY_INTERIORS_1', 6, 7, 'DOWN', 'MAP_NOWTOCH_CITY'),),
)

generic_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040e079p1',
    group='m040e079p1',
    rows=('map040/ev079/p1',),
    approach_prefer='east',
    archetype=(('map040/ev079/p1', 'trainer'),),
)

seam_beat(
    ch06,
    chapter_id='CH06',
    beat_name='m040seamS035',
    group='m040seamS035',
    rows=('map040/seam/S/map035',),
    approach_prefer='DOWN@(32,73)',
)

NEVER_FIRES: dict[str, str] = {
    'map040/ev014/p0': "map040/ev014/p0 is worked only from a clearing actor's tile, and the route could not put it after any of its clearing writers ['map040/ev141/p0', 'map042/ev003/p0/b1'] -- its page is dead by then; it never fires",
    'map040/ev055/p1': "archetype_kwargs: map040/ev055/p1: no warp lands on this arrival autorun's cell (62,23) on map 40 -- it never fires",
    'map040/ev055/p1/b0': "archetype_kwargs: map040/ev055/p1: no warp lands on this arrival autorun's cell (62,23) on map 40 -- it never fires",
    'map040/ev055/p1/b1': "archetype_kwargs: map040/ev055/p1: no warp lands on this arrival autorun's cell (62,23) on map 40 -- it never fires",
    'map041/ev003/p0': 'map041/ev003/p0: its event on counter cell (10, 8) is no object event, and pokeemerald reaches across the counter to an object first from every side (south (10, 9) -> object at (10, 7)) -- it never fires on the ROM',
    'map043/ev012/p1': "archetype_kwargs: map043/ev012/p1: no warp lands on this arrival autorun's cell (7,12) on map 43 -- it never fires",
    'map043/ev012/p1/b0': "archetype_kwargs: map043/ev012/p1: no warp lands on this arrival autorun's cell (7,12) on map 43 -- it never fires",
    'map043/ev012/p1/b1': "archetype_kwargs: map043/ev012/p1: no warp lands on this arrival autorun's cell (7,12) on map 43 -- it never fires",
    'map046/ev014/p1': "map046/ev014/p1 (needs self switch A == True) is not its event's live page at this route position: self switch A == True fails: self switch A is [False] (seed state), never written on the route; the rows that could write it none are not walked before it; live page: map046/ev014/p0 (needs no condition)",
    'map046/ev016/p0': 'map046/ev016/p0: its event on counter cell (30, 17) is no object event, and pokeemerald reaches across the counter to an object first from every side (south (30, 18) -> object at (30, 16)) -- it never fires on the ROM',
}

EMPTY_PAGES: dict[str, str] = {
    'map040/ev004/p0': 'every page of the event is empty; nothing to check on the ROM',
    'map040/ev004/p1': 'every page of the event is empty; nothing to check on the ROM',
    'map040/ev005/p0': 'every page of the event is empty; nothing to check on the ROM',
    'map040/ev005/p1': 'every page of the event is empty; nothing to check on the ROM',
    'map040/ev077/p0': 'every page of the event is empty; nothing to check on the ROM',
    'map040/ev078/p0': 'every page of the event is empty; nothing to check on the ROM',
    'map040/ev078/p1': 'every page of the event is empty; nothing to check on the ROM',
    'map040/ev135/p0': 'every page of the event is empty; nothing to check on the ROM',
    'map040/ev140/p0': 'every page of the event is empty; nothing to check on the ROM',
    'map040/ev140/p1': 'every page of the event is empty; nothing to check on the ROM',
    'map040/ev140/p2': 'every page of the event is empty; nothing to check on the ROM',
    'map043/ev005/p0': 'every page of the event is empty; nothing to check on the ROM',
    'map043/ev005/p1': 'every page of the event is empty; nothing to check on the ROM',
    'map043/ev005/p2': 'every page of the event is empty; nothing to check on the ROM',
    'map043/ev005/p3': 'every page of the event is empty; nothing to check on the ROM',
    'map043/ev005/p4': 'every page of the event is empty; nothing to check on the ROM',
    'map043/ev005/p5': 'every page of the event is empty; nothing to check on the ROM',
    'map043/ev005/p6': 'every page of the event is empty; nothing to check on the ROM',
    'map043/ev006/p0': 'every page of the event is empty; nothing to check on the ROM',
    'map043/ev006/p1': 'every page of the event is empty; nothing to check on the ROM',
    'map043/ev006/p2': 'every page of the event is empty; nothing to check on the ROM',
    'map043/ev006/p3': 'every page of the event is empty; nothing to check on the ROM',
    'map043/ev006/p4': 'every page of the event is empty; nothing to check on the ROM',
    'map043/ev006/p5': 'every page of the event is empty; nothing to check on the ROM',
    'map043/ev006/p6': 'every page of the event is empty; nothing to check on the ROM',
    'map047/ev002/p0': 'every page of the event is empty; nothing to check on the ROM',
    'map047/ev002/p1': 'every page of the event is empty; nothing to check on the ROM',
    'map047/ev009/p0': 'every page of the event is empty; nothing to check on the ROM',
}

WALK_CHECKED: dict[str, str] = {
    'map040/ev011/p0/b0': 'arm on a rolled or computed value (var 102 == 1); the walk checks whichever fires',
    'map040/ev011/p0/b1': 'arm on a rolled or computed value (var 102 != 1); the walk checks whichever fires',
    'map043/ev004/p0/b0': 'arm on a rolled or computed value (var 102 == 2); the walk checks whichever fires',
    'map043/ev004/p0/b1': 'arm on a rolled or computed value (var 102 != 2); the walk checks whichever fires',
    'map043/ev004/p0/b2': 'arm on a rolled or computed value (var 102 != 2 and var 102 == 1); the walk checks whichever fires',
    'map043/ev004/p0/b3': 'arm on a rolled or computed value (var 102 != 2 and var 102 != 1); the walk checks whichever fires',
    'map043/ev007/p0/b0': 'arm on a rolled or computed value (var 102 == 2); the walk checks whichever fires',
    'map043/ev007/p0/b1': 'arm on a rolled or computed value (var 102 != 2); the walk checks whichever fires',
    'map043/ev007/p0/b2': 'arm on a rolled or computed value (var 102 != 2 and var 102 == 1); the walk checks whichever fires',
    'map043/ev007/p0/b3': 'arm on a rolled or computed value (var 102 != 2 and var 102 != 1); the walk checks whichever fires',
    'map043/ev008/p0/b0': 'arm on a rolled or computed value (var 102 == 2); the walk checks whichever fires',
    'map043/ev008/p0/b1': 'arm on a rolled or computed value (var 102 != 2); the walk checks whichever fires',
    'map043/ev008/p0/b2': 'arm on a rolled or computed value (var 102 != 2 and var 102 == 1); the walk checks whichever fires',
    'map043/ev008/p0/b3': 'arm on a rolled or computed value (var 102 != 2 and var 102 != 1); the walk checks whichever fires',
    'map046/ev006/p0/b0': 'arm on a rolled or computed value (var 102 == 1); the walk checks whichever fires',
    'map046/ev006/p0/b1': 'arm on a rolled or computed value (var 102 != 1); the walk checks whichever fires',
    'map046/ev008/p0/b0': 'arm on a rolled or computed value (var 102 == 1); the walk checks whichever fires',
    'map046/ev008/p0/b1': 'arm on a rolled or computed value (var 102 != 1); the walk checks whichever fires',
}

ELSEWHERE: dict[str, str] = {
    'map040/ev006/p1': 'unreachable',
    'map040/ev007/p1': 'unreachable',
    'map040/ev008/p1': 'unreachable',
    'map040/ev009/p1': 'unreachable',
    'map040/ev013/p1/b1': 'unselected_arm: not taken on the walk: else of `get_character(0).onEvent?` from cell (24, 55) (event at (24, 55)) (ruling 19)',
    'map040/ev014/p2/b1': 'unselected_arm: not taken on the walk: else of `get_character(0).onEvent?` from cell (49, 14) (event at (49, 14)) (ruling 19)',
    'map040/ev015/p1/b1': 'unselected_arm: not taken on the walk: else of `get_character(0).onEvent?` from cell (23, 33) (event at (23, 33)) (ruling 19)',
    'map040/ev016/p1/b1': 'unselected_arm: not taken on the walk: else of `get_character(0).onEvent?` from cell (14, 35) (event at (14, 35)) (ruling 19)',
    'map040/ev017/p0/b1': "unselected_arm: not taken on the walk: needs BagHas(item='MARIAKEY') == False, and here BagHas(item='MARIAKEY') is [True] (ruling 19)",
    'map040/ev017/p2/b1': 'unselected_arm: not taken on the walk: else of `get_character(0).onEvent?` from cell (47, 61) (event at (47, 61)) (ruling 19)',
    'map040/ev018/p0/b1': 'unselected_arm: blocked by harness:full_bag; the walk takes the sibling arm (ruling 19)',
    'map040/ev019/p3/b1': 'unselected_arm: not taken on the walk: else of `get_character(0).onEvent?` from cell (68, 43) (event at (68, 43)) (ruling 19)',
    'map040/ev024/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev026/p1': 'unreachable',
    'map040/ev027/p1/b1': 'unselected_arm: not taken on the walk: else of `get_character(0).onEvent?` from cell (61, 23) (event at (61, 23)) (ruling 19)',
    'map040/ev028/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev029/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev030/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev031/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev032/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev033/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev034/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev035/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev036/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev037/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev038/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev039/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev040/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev041/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev042/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev043/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev044/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev045/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev046/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev047/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev048/p0': 'stripped: strip_list.json map_events (EV048)',
    'map040/ev049/p0': 'stripped: strip_list.json map_events (EV049)',
    'map040/ev052/p0': 'later',
    'map040/ev052/p1': "later: CH07: its event crosses out of the chapter's map chain (to map(s) [44]); the rest of the event belongs to the chapter that builds the far side",
    'map040/ev052/p1/b0': "later: CH07: its event crosses out of the chapter's map chain (to map(s) [44]); the rest of the event belongs to the chapter that builds the far side",
    'map040/ev052/p1/b1': "later: CH07: its event crosses out of the chapter's map chain (to map(s) [44]); the rest of the event belongs to the chapter that builds the far side",
    'map040/ev053/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev054/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev056/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev057/p0': 'later',
    'map040/ev057/p1': "later: CH07: its event crosses out of the chapter's map chain (to map(s) [44]); the rest of the event belongs to the chapter that builds the far side",
    'map040/ev057/p1/b0': "later: CH07: its event crosses out of the chapter's map chain (to map(s) [44]); the rest of the event belongs to the chapter that builds the far side",
    'map040/ev057/p1/b1': "later: CH07: its event crosses out of the chapter's map chain (to map(s) [44]); the rest of the event belongs to the chapter that builds the far side",
    'map040/ev058/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev059/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev060/p0/b1': 'unselected_arm: blocked by harness:full_bag; the walk takes the sibling arm (ruling 19)',
    'map040/ev064/p1/b1': 'unselected_arm: not taken on the walk: else of `get_character(0).onEvent?` from cell (42, 61) (event at (42, 61)) (ruling 19)',
    'map040/ev065/p1/b1': 'unselected_arm: not taken on the walk: else of `get_character(0).onEvent?` from cell (19, 35) (event at (19, 35)) (ruling 19)',
    'map040/ev066/p1/b1': 'unselected_arm: not taken on the walk: else of `get_character(0).onEvent?` from cell (19, 55) (event at (19, 55)) (ruling 19)',
    'map040/ev079/p0/b3': 'unselected_arm: not taken on the walk: else of `$game_player.x<=33` from cell (32, 65) (event at (31, 65)) (ruling 19)',
    'map040/ev079/p0/b5': 'unselected_arm: blocked by fork:whiteout; the walk takes the sibling arm (ruling 19)',
    'map040/ev079/p0/b7': 'unselected_arm: blocked by harness:full_bag; the walk takes the sibling arm (ruling 19)',
    'map040/ev081/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev082/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev083/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev084/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev085/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev086/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev087/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev088/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev089/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev090/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev091/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev092/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev093/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev094/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev095/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev096/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev097/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev098/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev099/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev100/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev101/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev102/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev103/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev104/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev105/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev106/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev107/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev108/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev109/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev110/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev111/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev112/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev113/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev114/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev115/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev116/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev117/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev118/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev119/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev120/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev121/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev122/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev123/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev124/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev125/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev126/p0': 'stripped: strip_list.json map_events (Luz)',
    'map040/ev141/p0/b3': 'unselected_arm: not taken on the walk: else of `$game_player.x<=49` from cell (48, 19) (event at (47, 19)) (ruling 19)',
    'map042/ev001/p0/b1': 'unselected_arm: blocked by fork:whiteout; the walk takes the sibling arm (ruling 19)',
    'map042/ev002/p0/b1': 'unselected_arm: blocked by fork:whiteout; the walk takes the sibling arm (ruling 19)',
    'map042/ev003/p0/b2': 'unselected_arm: blocked by harness:full_bag; the walk takes the sibling arm (ruling 19)',
    'map042/ev003/p0/b3': 'unselected_arm: blocked by fork:whiteout; the walk takes the sibling arm (ruling 19)',
    'map042/ev004/p0/b1': 'unselected_arm: blocked by harness:full_bag; the walk takes the sibling arm (ruling 19)',
    'map042/ev004/p2': 'unreachable',
    'map043/ev001/p0/b1': 'unreachable',
    'map046/ev002/p0/b1': "unselected_arm: not taken on the walk: it sits inside map046/ev002/p0/b0, which the walk doesn't take (ruling 19)",
    'map046/ev002/p0/b10': "unselected_arm: not taken on the walk: it sits inside map046/ev002/p0/b0, which the walk doesn't take (ruling 19)",
    'map046/ev002/p0/b2': "unselected_arm: not taken on the walk: it sits inside map046/ev002/p0/b0, which the walk doesn't take (ruling 19)",
    'map046/ev003/p1': 'unreachable',
    'map046/ev003/p1/b0': 'unreachable',
    'map046/ev003/p1/b1': 'unreachable',
    'map046/ev003/p1/b12': 'unreachable',
    'map046/ev003/p1/b13': 'unreachable',
    'map046/ev003/p1/b18': 'unreachable',
    'map046/ev003/p1/b19': 'unreachable',
    'map046/ev003/p1/b24': 'unreachable',
    'map046/ev003/p1/b25': 'unreachable',
    'map046/ev003/p1/b30': 'unreachable',
    'map046/ev003/p1/b31': 'unreachable',
    'map046/ev003/p1/b36': 'unreachable',
    'map046/ev003/p1/b37': 'unreachable',
    'map046/ev003/p1/b42': 'unreachable',
    'map046/ev003/p1/b43': 'unreachable',
    'map046/ev003/p1/b48': 'unreachable',
    'map046/ev003/p1/b49': 'unreachable',
    'map046/ev003/p1/b54': 'unreachable',
    'map046/ev003/p1/b55': 'unreachable',
    'map046/ev003/p1/b6': 'unreachable',
    'map046/ev003/p1/b60': 'unreachable',
    'map046/ev003/p1/b61': 'unreachable',
    'map046/ev003/p1/b66': 'unreachable',
    'map046/ev003/p1/b67': 'unreachable',
    'map046/ev003/p1/b7': 'unreachable',
}

REFUSED: dict[str, str] = {
    'map041/ev004/p1': 'story-state: unmodelled_predicate',
    'map041/ev004/p1/b0': 'story-state: unmodelled_predicate',
    'map041/ev004/p1/b1': 'story-state: unmodelled_predicate',
    'map046/ev002/p0/b0': "story-state: unclassified_condition -- no family matches: 'pbGetPokemon(1).isForeign?($Trainer)'",
    'map046/ev002/p0/b3': 'story-state: unmodelled_outcome:party_slot_egg_state',
    'map046/ev002/p0/b4': 'story-state: unmodelled_outcome:party_slot_egg_state',
    'map046/ev002/p0/b5': 'story-state: unclassified_condition',
    'map046/ev002/p0/b6': 'story-state: unclassified_condition',
    'map046/ev002/p0/b7': 'story-state: party_model',
    'map046/ev002/p0/b8': 'story-state: party_model',
    'map046/ev002/p0/b9': 'story-state: party_model',
    'map046/ev003/p1/b10': 'story-state: unclassified_condition',
    'map046/ev003/p1/b11': 'story-state: unclassified_condition',
    'map046/ev003/p1/b14': 'story-state: unclassified_condition',
    'map046/ev003/p1/b15': 'story-state: unclassified_condition',
    'map046/ev003/p1/b16': 'story-state: unclassified_condition',
    'map046/ev003/p1/b17': 'story-state: unclassified_condition',
    'map046/ev003/p1/b2': 'story-state: unclassified_condition',
    'map046/ev003/p1/b20': 'story-state: unclassified_condition',
    'map046/ev003/p1/b21': 'story-state: unclassified_condition',
    'map046/ev003/p1/b22': 'story-state: unclassified_condition',
    'map046/ev003/p1/b23': 'story-state: unclassified_condition',
    'map046/ev003/p1/b26': 'story-state: unclassified_condition',
    'map046/ev003/p1/b27': 'story-state: unclassified_condition',
    'map046/ev003/p1/b28': 'story-state: unclassified_condition',
    'map046/ev003/p1/b29': 'story-state: unclassified_condition',
    'map046/ev003/p1/b3': 'story-state: unclassified_condition',
    'map046/ev003/p1/b32': 'story-state: unclassified_condition',
    'map046/ev003/p1/b33': 'story-state: unclassified_condition',
    'map046/ev003/p1/b34': 'story-state: unclassified_condition',
    'map046/ev003/p1/b35': 'story-state: unclassified_condition',
    'map046/ev003/p1/b38': 'story-state: unclassified_condition',
    'map046/ev003/p1/b39': 'story-state: unclassified_condition',
    'map046/ev003/p1/b4': 'story-state: unclassified_condition',
    'map046/ev003/p1/b40': 'story-state: unclassified_condition',
    'map046/ev003/p1/b41': 'story-state: unclassified_condition',
    'map046/ev003/p1/b44': 'story-state: unclassified_condition',
    'map046/ev003/p1/b45': 'story-state: unclassified_condition',
    'map046/ev003/p1/b46': 'story-state: unclassified_condition',
    'map046/ev003/p1/b47': 'story-state: unclassified_condition',
    'map046/ev003/p1/b5': 'story-state: unclassified_condition',
    'map046/ev003/p1/b50': 'story-state: unclassified_condition',
    'map046/ev003/p1/b51': 'story-state: unclassified_condition',
    'map046/ev003/p1/b52': 'story-state: unclassified_condition',
    'map046/ev003/p1/b53': 'story-state: unclassified_condition',
    'map046/ev003/p1/b56': 'story-state: unclassified_condition',
    'map046/ev003/p1/b57': 'story-state: unclassified_condition',
    'map046/ev003/p1/b58': 'story-state: unclassified_condition',
    'map046/ev003/p1/b59': 'story-state: unclassified_condition',
    'map046/ev003/p1/b62': 'story-state: unclassified_condition',
    'map046/ev003/p1/b63': 'story-state: unclassified_condition',
    'map046/ev003/p1/b64': 'story-state: unclassified_condition',
    'map046/ev003/p1/b65': 'story-state: unclassified_condition',
    'map046/ev003/p1/b8': 'story-state: unclassified_condition',
    'map046/ev003/p1/b9': 'story-state: unclassified_condition',
    'map046/ev014/p0/b0': "story-state: unclassified_condition -- no family matches: '$Trainer.party.length<=0'",
    'map046/ev014/p0/b1': 'story-state: unclassified_condition',
    'map046/ev014/p0/b2': 'story-state: unclassified_condition',
    'map046/ev014/p0/b3': 'story-state: unclassified_condition',
    'map046/ev014/p0/b4': 'story-state: unclassified_condition',
}

CHAPTER = ch06.build()
