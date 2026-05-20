    [MOVE_TACKLE] =
    {
        .name = COMPOUND_STRING("Tackle"),
        .description = COMPOUND_STRING("A physical attack in which the user charges and slams into the target with its whole body."),
        .effect = EFFECT_PLACEHOLDER,  // TODO Phase 6: Essentials function code 0
        .power = 50,
        .type = TYPE_NORMAL,
        .accuracy = 100,
        .pp = 35,
        .target = TARGET_SELECTED,
        .priority = 0,
        .category = DAMAGE_CATEGORY_PHYSICAL,
        .makesContact = TRUE,
    },
    [MOVE_ATOMIC_PUNCH] =
    {
        .name = COMPOUND_STRING("Atomic Punch"),
        .description = COMPOUND_STRING("A Punch inbued with radiation, capable of infecting the enemy"),
        .effect = EFFECT_PLACEHOLDER,  // TODO Phase 6: Essentials function code 7 (chance 15)
        .power = 80,
        .type = TYPE_NUCLEAR,
        .accuracy = 95,
        .pp = 15,
        .target = TARGET_SELECTED,
        .priority = 0,
        .category = DAMAGE_CATEGORY_PHYSICAL,
        .makesContact = TRUE,
    },
