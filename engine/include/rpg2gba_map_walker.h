#ifndef GUARD_RPG2GBA_MAP_WALKER_H
#define GUARD_RPG2GBA_MAP_WALKER_H

#include "config/rpg2gba_harness.h"

#if RPG2GBA_MAP_WALKER == TRUE

void Rpg2gbaWalker_Begin(void);          // set active before map load (boot path)
void Rpg2gbaWalker_FieldCB_MapLoad(void);
bool8 Rpg2gbaWalker_IsActive(void);

#endif // RPG2GBA_MAP_WALKER == TRUE

#endif // GUARD_RPG2GBA_MAP_WALKER_H
