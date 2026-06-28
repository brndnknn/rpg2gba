#ifndef GUARD_URANIUM_MAP_WALKER_H
#define GUARD_URANIUM_MAP_WALKER_H

#include "config/uranium_walker.h"

#if URANIUM_MAP_WALKER == TRUE

void UraniumWalker_Begin(void);          // set active before map load (boot path)
void UraniumWalker_FieldCB_MapLoad(void);
bool8 UraniumWalker_IsActive(void);

#endif // URANIUM_MAP_WALKER == TRUE

#endif // GUARD_URANIUM_MAP_WALKER_H
