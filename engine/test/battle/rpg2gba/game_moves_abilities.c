#include "global.h"
#include "test/battle.h"

// BEGIN RPG2GBA GAME PROFILE — the converted game's own moves and abilities
// (rpg2gba battle_converter, reference/battle_rulings.json). They exist only
// when the pipeline has installed the generated headers, so every test is
// compiled under the presence macro of what it exercises.

// --- moves -------------------------------------------------------------------

#ifdef RPG2GBA_HAS_MOVE_LASER_PULSE
SINGLE_BATTLE_TEST("Laser Pulse rolls Fire, Electric or Ice each use")
{
    u32 type;
    PARAMETRIZE { type = TYPE_FIRE; }
    PARAMETRIZE { type = TYPE_ELECTRIC; }
    PARAMETRIZE { type = TYPE_ICE; }
    GIVEN {
        ASSUME(GetMoveEffect(MOVE_LASER_PULSE) == EFFECT_RPG2GBA_TRI_TYPE);
        PLAYER(SPECIES_WOBBUFFET);
        OPPONENT(SPECIES_GIBLE); // Dragon/Ground: Fire 0.5x, Electric 0x, Ice 4x
    } WHEN {
        TURN { MOVE(player, MOVE_LASER_PULSE, WITH_RNG(RNG_RPG2GBA_TRI_TYPE, type)); }
    } SCENE {
        if (type == TYPE_FIRE)
            MESSAGE("It's not very effective…");
        else if (type == TYPE_ELECTRIC)
            MESSAGE("It doesn't affect the opposing Gible…");
        else
            MESSAGE("It's super effective!");
    }
}
#endif

#ifdef RPG2GBA_HAS_MOVE_GET_LUCKY
SINGLE_BATTLE_TEST("Get Lucky pumps the user up after it hits")
{
    GIVEN {
        PLAYER(SPECIES_WOBBUFFET);
        OPPONENT(SPECIES_WOBBUFFET);
    } WHEN {
        TURN { MOVE(player, MOVE_GET_LUCKY); }
    } SCENE {
        ANIMATION(ANIM_TYPE_MOVE, MOVE_GET_LUCKY, player);
        HP_BAR(opponent);
        MESSAGE("Wobbuffet is getting pumped!");
    } THEN {
        EXPECT(player->volatiles.focusEnergy || player->volatiles.dragonCheer);
    }
}
#endif

#ifdef RPG2GBA_HAS_MOVE_SUBDUCTION
SINGLE_BATTLE_TEST("Subduction sharply lowers the target's Speed and confuses the user")
{
    GIVEN {
        PLAYER(SPECIES_WOBBUFFET);
        OPPONENT(SPECIES_WOBBUFFET);
    } WHEN {
        TURN { MOVE(player, MOVE_SUBDUCTION); }
    } SCENE {
        HP_BAR(opponent);
        MESSAGE("The opposing Wobbuffet's Speed harshly fell!");
        MESSAGE("Wobbuffet became confused!");
    } THEN {
        EXPECT_EQ(opponent->statStages[STAT_SPEED], DEFAULT_STAT_STAGE - 2);
        EXPECT(player->volatiles.confusionTurns != 0);
    }
}
#endif

#ifdef RPG2GBA_HAS_MOVE_CAUSTIC_BREATH
SINGLE_BATTLE_TEST("Caustic Breath lowers Defense and Sp. Def")
{
    GIVEN {
        PLAYER(SPECIES_WOBBUFFET);
        OPPONENT(SPECIES_WOBBUFFET);
    } WHEN {
        TURN { MOVE(player, MOVE_CAUSTIC_BREATH); }
    } THEN {
        EXPECT_EQ(opponent->statStages[STAT_DEF], DEFAULT_STAT_STAGE - 1);
        EXPECT_EQ(opponent->statStages[STAT_SPDEF], DEFAULT_STAT_STAGE - 1);
    }
}
#endif

#ifdef RPG2GBA_HAS_MOVE_INFERNAL_BLADE
SINGLE_BATTLE_TEST("Infernal Blade is super effective against Fairy types")
{
    GIVEN {
        PLAYER(SPECIES_WOBBUFFET);
        OPPONENT(SPECIES_CLEFAIRY);
    } WHEN {
        TURN { MOVE(player, MOVE_INFERNAL_BLADE); }
    } SCENE {
        MESSAGE("It's super effective!");
    }
}
#endif

#ifdef RPG2GBA_HAS_MOVE_GOLDEN_FIST
SINGLE_BATTLE_TEST("Golden Fist scatters coins")
{
    GIVEN {
        PLAYER(SPECIES_WOBBUFFET);
        OPPONENT(SPECIES_WOBBUFFET);
    } WHEN {
        TURN { MOVE(player, MOVE_GOLDEN_FIST); }
    } SCENE {
        HP_BAR(opponent);
        MESSAGE("Coins were scattered everywhere!");
    }
}
#endif

#ifdef RPG2GBA_HAS_MOVE_SHUFFLE
SINGLE_BATTLE_TEST("Shuffle heals the user by half and deals no damage")
{
    GIVEN {
        PLAYER(SPECIES_WOBBUFFET) { HP(1); MaxHP(100); }
        OPPONENT(SPECIES_WOBBUFFET);
    } WHEN {
        TURN { MOVE(player, MOVE_SHUFFLE); }
    } SCENE {
        HP_BAR(player, damage: -50);
        NOT HP_BAR(opponent);
    }
}
#endif

#ifdef RPG2GBA_HAS_MOVE_FLAME_IMPACT
SINGLE_BATTLE_TEST("Flame Impact goes first")
{
    GIVEN {
        ASSUME(GetMovePriority(MOVE_FLAME_IMPACT) == 2);
        PLAYER(SPECIES_WOBBUFFET) { Speed(1); }
        OPPONENT(SPECIES_WOBBUFFET) { Speed(100); }
    } WHEN {
        TURN { MOVE(player, MOVE_FLAME_IMPACT); MOVE(opponent, MOVE_CELEBRATE); }
    } SCENE {
        ANIMATION(ANIM_TYPE_MOVE, MOVE_FLAME_IMPACT, player);
        ANIMATION(ANIM_TYPE_MOVE, MOVE_CELEBRATE, opponent);
    }
}
#endif

// --- abilities ---------------------------------------------------------------

#ifdef RPG2GBA_HAS_ABILITY_ENERGIZATE
SINGLE_BATTLE_TEST("Energizate turns a Normal move into Electric")
{
    GIVEN {
        PLAYER(SPECIES_KRABBY);
        OPPONENT(SPECIES_WOBBUFFET) { Ability(ABILITY_ENERGIZATE); }
    } WHEN {
        TURN { MOVE(opponent, MOVE_SCRATCH); }
    } SCENE {
        ANIMATION(ANIM_TYPE_MOVE, MOVE_SCRATCH, opponent);
        MESSAGE("It's super effective!");
    }
}
#endif

#ifdef RPG2GBA_HAS_ABILITY_ELEMENTALIST
SINGLE_BATTLE_TEST("Elementalist gives Fire, Electric and Water moves STAB", s16 damage)
{
    enum Ability ability;
    enum Move move;
    PARAMETRIZE { ability = ABILITY_TELEPATHY;    move = MOVE_EMBER; }
    PARAMETRIZE { ability = ABILITY_ELEMENTALIST; move = MOVE_EMBER; }
    PARAMETRIZE { ability = ABILITY_TELEPATHY;    move = MOVE_SCRATCH; }
    PARAMETRIZE { ability = ABILITY_ELEMENTALIST; move = MOVE_SCRATCH; }
    GIVEN {
        PLAYER(SPECIES_WOBBUFFET) { Ability(ability); }
        OPPONENT(SPECIES_WOBBUFFET);
    } WHEN {
        TURN { MOVE(player, move); }
    } SCENE {
        HP_BAR(opponent, captureDamage: &results[i].damage);
    } FINALLY {
        EXPECT_MUL_EQ(results[0].damage, Q_4_12(1.5), results[1].damage);
        EXPECT_EQ(results[2].damage, results[3].damage);
    }
}
#endif

#ifdef RPG2GBA_HAS_ABILITY_SHARP_CORAL
SINGLE_BATTLE_TEST("Sharp Coral doubles the holder's attacks and the attacks it takes", s16 damage)
{
    enum Ability atk, def;
    PARAMETRIZE { atk = ABILITY_TELEPATHY;   def = ABILITY_TELEPATHY; }
    PARAMETRIZE { atk = ABILITY_SHARP_CORAL; def = ABILITY_TELEPATHY; }
    PARAMETRIZE { atk = ABILITY_TELEPATHY;   def = ABILITY_SHARP_CORAL; }
    GIVEN {
        PLAYER(SPECIES_WOBBUFFET) { Ability(atk); }
        OPPONENT(SPECIES_WOBBUFFET) { Ability(def); }
    } WHEN {
        TURN { MOVE(player, MOVE_SCRATCH); }
    } SCENE {
        HP_BAR(opponent, captureDamage: &results[i].damage);
    } FINALLY {
        EXPECT_MUL_EQ(results[0].damage, Q_4_12(2.0), results[1].damage);
        EXPECT_MUL_EQ(results[0].damage, Q_4_12(2.0), results[2].damage);
    }
}
#endif

#ifdef RPG2GBA_HAS_ABILITY_ACCELERATION
SINGLE_BATTLE_TEST("Acceleration powers up Quick Attack by 50%", s16 damage)
{
    enum Ability ability;
    PARAMETRIZE { ability = ABILITY_TELEPATHY; }
    PARAMETRIZE { ability = ABILITY_ACCELERATION; }
    GIVEN {
        PLAYER(SPECIES_WOBBUFFET) { Ability(ability); }
        OPPONENT(SPECIES_WOBBUFFET);
    } WHEN {
        TURN { MOVE(player, MOVE_QUICK_ATTACK); }
    } SCENE {
        HP_BAR(opponent, captureDamage: &results[i].damage);
    } FINALLY {
        EXPECT_MUL_EQ(results[0].damage, Q_4_12(1.5), results[1].damage);
    }
}
#endif

#ifdef RPG2GBA_HAS_ABILITY_SOUND_BOOST
SINGLE_BATTLE_TEST("Sound Boost powers up Hyper Voice by 30%", s16 damage)
{
    enum Ability ability;
    PARAMETRIZE { ability = ABILITY_TELEPATHY; }
    PARAMETRIZE { ability = ABILITY_SOUND_BOOST; }
    GIVEN {
        PLAYER(SPECIES_WOBBUFFET) { Ability(ability); }
        OPPONENT(SPECIES_WOBBUFFET);
    } WHEN {
        TURN { MOVE(player, MOVE_HYPER_VOICE); }
    } SCENE {
        HP_BAR(opponent, captureDamage: &results[i].damage);
    } FINALLY {
        EXPECT_MUL_EQ(results[0].damage, Q_4_12(1.3), results[1].damage);
    }
}
#endif

#ifdef RPG2GBA_HAS_ABILITY_INFURIATE
SINGLE_BATTLE_TEST("Infuriate absorbs physical moves and raises Attack")
{
    GIVEN {
        PLAYER(SPECIES_WOBBUFFET) { Ability(ABILITY_INFURIATE); }
        OPPONENT(SPECIES_WOBBUFFET);
    } WHEN {
        TURN { MOVE(opponent, MOVE_SCRATCH); }
    } SCENE {
        ABILITY_POPUP(player, ABILITY_INFURIATE);
        ANIMATION(ANIM_TYPE_GENERAL, B_ANIM_STATS_CHANGE, player);
        NONE_OF { HP_BAR(player); }
    } THEN {
        EXPECT_EQ(player->statStages[STAT_ATK], DEFAULT_STAT_STAGE + 1);
    }
}

SINGLE_BATTLE_TEST("Infuriate does not absorb special moves")
{
    GIVEN {
        PLAYER(SPECIES_WOBBUFFET) { Ability(ABILITY_INFURIATE); }
        OPPONENT(SPECIES_WOBBUFFET);
    } WHEN {
        TURN { MOVE(opponent, MOVE_EMBER); }
    } SCENE {
        HP_BAR(player);
    }
}
#endif

#ifdef RPG2GBA_HAS_ABILITY_DISENCHANT
SINGLE_BATTLE_TEST("Disenchant makes the holder immune to Fairy moves")
{
    GIVEN {
        PLAYER(SPECIES_WOBBUFFET) { Ability(ABILITY_DISENCHANT); }
        OPPONENT(SPECIES_WOBBUFFET);
    } WHEN {
        TURN { MOVE(opponent, MOVE_FAIRY_WIND); }
    } SCENE {
        ABILITY_POPUP(player, ABILITY_DISENCHANT);
        NONE_OF { HP_BAR(player); }
    }
}
#endif

#ifdef RPG2GBA_HAS_ABILITY_QUICK_CHARGE
SINGLE_BATTLE_TEST("Quick Charge moves first on the turn after it enters, not later")
{
    GIVEN {
        PLAYER(SPECIES_WOBBUFFET) { Ability(ABILITY_QUICK_CHARGE); Speed(1); }
        OPPONENT(SPECIES_WOBBUFFET) { Speed(100); }
    } WHEN {
        TURN { MOVE(player, MOVE_CELEBRATE); MOVE(opponent, MOVE_CELEBRATE); }
        TURN { MOVE(player, MOVE_CELEBRATE); MOVE(opponent, MOVE_CELEBRATE); }
    } SCENE {
        ANIMATION(ANIM_TYPE_MOVE, MOVE_CELEBRATE, player);
        ANIMATION(ANIM_TYPE_MOVE, MOVE_CELEBRATE, opponent);
        ANIMATION(ANIM_TYPE_MOVE, MOVE_CELEBRATE, opponent);
        ANIMATION(ANIM_TYPE_MOVE, MOVE_CELEBRATE, player);
    }
}
#endif

#ifdef RPG2GBA_HAS_ABILITY_LAZY
SINGLE_BATTLE_TEST("Lazy puts the holder to sleep when it enters")
{
    GIVEN {
        PLAYER(SPECIES_WOBBUFFET) { Ability(ABILITY_LAZY); }
        OPPONENT(SPECIES_WOBBUFFET);
    } WHEN {
        TURN { }
    } SCENE {
        ABILITY_POPUP(player, ABILITY_LAZY);
        MESSAGE("Wobbuffet fell asleep!");
        STATUS_ICON(player, sleep: TRUE);
    }
}
#endif

#ifdef RPG2GBA_HAS_ABILITY_PETRIFY
SINGLE_BATTLE_TEST("Petrify lowers the foe's Speed when the holder enters")
{
    GIVEN {
        PLAYER(SPECIES_WOBBUFFET);
        OPPONENT(SPECIES_WOBBUFFET) { Ability(ABILITY_PETRIFY); }
    } WHEN {
        TURN { }
    } SCENE {
        ABILITY_POPUP(opponent, ABILITY_PETRIFY);
        MESSAGE("Wobbuffet's Speed fell!");
    } THEN {
        EXPECT_EQ(player->statStages[STAT_SPEED], DEFAULT_STAT_STAGE - 1);
    }
}
#endif

#ifdef RPG2GBA_HAS_ABILITY_REBUILD
SINGLE_BATTLE_TEST("Rebuild heals 1/8 at the end of a turn no move damaged the holder")
{
    bool32 hit;
    PARAMETRIZE { hit = FALSE; }
    PARAMETRIZE { hit = TRUE; }
    GIVEN {
        PLAYER(SPECIES_WOBBUFFET) { Ability(ABILITY_REBUILD); HP(50); MaxHP(160); }
        OPPONENT(SPECIES_WOBBUFFET);
    } WHEN {
        TURN { MOVE(opponent, hit ? MOVE_SCRATCH : MOVE_CELEBRATE); }
    } SCENE {
        if (hit)
        {
            NONE_OF { ABILITY_POPUP(player, ABILITY_REBUILD); }
        }
        else
        {
            ABILITY_POPUP(player, ABILITY_REBUILD);
            HP_BAR(player, damage: -20);
        }
    }
}
#endif

#ifdef RPG2GBA_HAS_ABILITY_BLOOD_LUST
SINGLE_BATTLE_TEST("Blood Lust heals the holder by 1/6 of the damage it deals")
{
    s16 dealt = 0, healed = 0;
    GIVEN {
        PLAYER(SPECIES_WOBBUFFET) { Ability(ABILITY_BLOOD_LUST); HP(1); }
        OPPONENT(SPECIES_WOBBUFFET);
    } WHEN {
        TURN { MOVE(player, MOVE_SCRATCH); }
    } SCENE {
        HP_BAR(opponent, captureDamage: &dealt);
        ABILITY_POPUP(player, ABILITY_BLOOD_LUST);
        HP_BAR(player, captureDamage: &healed);
    } THEN {
        EXPECT_EQ(-healed, dealt / 6);
    }
}
#endif

#ifdef RPG2GBA_HAS_ABILITY_NIGHT_TERROR
SINGLE_BATTLE_TEST("Night Terror paralyses a foe as it wakes up")
{
    GIVEN {
        PLAYER(SPECIES_WOBBUFFET) { Status1(STATUS1_SLEEP_TURN(1)); }
        OPPONENT(SPECIES_WOBBUFFET) { Ability(ABILITY_NIGHT_TERROR); }
    } WHEN {
        TURN { MOVE(player, MOVE_CELEBRATE); }
    } SCENE {
        MESSAGE("Wobbuffet woke up!");
        ABILITY_POPUP(opponent, ABILITY_NIGHT_TERROR);
        STATUS_ICON(player, paralysis: TRUE);
    }
}
#endif
// END RPG2GBA GAME PROFILE
