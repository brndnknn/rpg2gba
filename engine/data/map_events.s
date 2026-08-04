#include "constants/global.h"
#include "constants/event_bg.h"
#include "constants/event_object_movement.h"
#include "constants/event_objects.h"
#include "constants/flags.h"
#include "constants/items.h"
#include "constants/map_scripts.h"
#include "constants/maps.h"
#include "constants/secret_bases.h"
#include "constants/vars.h"
#include "constants/weather.h"
#include "constants/trainer_hill.h"
#include "constants/trainer_types.h"
#include "constants/berry.h"
#include "constants/species.h"
#include "constants/apricorn_tree.h"
	.include "asm/macros.inc"
	.include "constants/constants.inc"

@ BEGIN URANIUM PATHFINDER SLICE — engine include-hook (rpg2gba; see engine/RPG2GBA_VENDOR.md).
@ Object-event templates in the generated data/maps/*/events.inc carry per-event visibility
@ flags, and the terminal-hide ones are minted by the flag registry (FLAG_HIDE_*), not by
@ constants/flags.h. This translation unit assembles those templates, so it needs the
@ generated header too — the copy in data/event_scripts.s only covers the SCRIPT path, and
@ without this the flags link-fail as undefined .rodata references. The referenced file is
@ pipeline-GENERATED + gitignored; a pristine vanilla build must revert this block.
	#include "data/scripts/uranium_flags.h"
@ END URANIUM PATHFINDER SLICE

	.section .rodata

	.include "data/maps/events.inc"
