#include "global.h"
#include "config/rpg2gba.h"
#include "uranium_map_walker.h"
#include "uranium_embedded_save.h"
#include "new_game.h"
#include "random.h"
#include "pokemon.h"
#include "roamer.h"
#include "pokemon_size_record.h"
#include "script.h"
#include "lottery_corner.h"
#include "play_time.h"
#include "mauville_old_man.h"
#include "match_call.h"
#include "lilycove_lady.h"
#include "load_save.h"
#include "pokeblock.h"
#include "dewford_trend.h"
#include "berry.h"
#include "rtc.h"
#include "easy_chat.h"
#include "event_data.h"
#include "event_object_movement.h"
#include "money.h"
#include "trainer_hill.h"
#include "trainer_tower.h"
#include "tv.h"
#include "coins.h"
#include "text.h"
#include "overworld.h"
#include "mail.h"
#include "battle_records.h"
#include "item.h"
#include "pokedex.h"
#include "apprentice.h"
#include "frontier_util.h"
#include "pokedex.h"
#include "save.h"
#include "link_rfu.h"
#include "main.h"
#include "contest.h"
#include "item_menu.h"
#include "pokemon_storage_system.h"
#include "pokemon_jump.h"
#include "decoration_inventory.h"
#include "secret_base.h"
#include "string_util.h"
#include "player_pc.h"
#include "field_specials.h"
#include "berry_powder.h"
#include "mystery_gift.h"
#include "union_room_chat.h"
#include "constants/map_groups.h"
#include "constants/items.h"
#include "difficulty.h"
#include "follower_npc.h"
// BEGIN URANIUM PATHFINDER SLICE — test-harness includes (rock-smash boot party)
#include "script_pokemon_util.h"
#include "constants/species.h"
#include "constants/moves.h"
// END URANIUM PATHFINDER SLICE

extern const u8 EventScript_ResetAllMapFlags[];
extern const u8 EventScript_ResetAllMapFlagsFrlg[];

static void ClearFrontierRecord(void);
static void WarpToTruck(void);
static void ResetMiniGamesRecords(void);
static void ResetItemFlags(void);
static void ResetDexNav(void);

EWRAM_DATA bool8 gDifferentSaveFile = FALSE;
EWRAM_DATA bool8 gEnableContestDebugging = FALSE;

static const struct ContestWinner sContestWinnerPicDummy =
{
    .monName = _(""),
    .trainerName = _("")
};

void SetTrainerId(u32 trainerId, u8 *dst)
{
    dst[0] = trainerId;
    dst[1] = trainerId >> 8;
    dst[2] = trainerId >> 16;
    dst[3] = trainerId >> 24;
}

u32 GetTrainerId(u8 *trainerId)
{
    return (trainerId[3] << 24) | (trainerId[2] << 16) | (trainerId[1] << 8) | (trainerId[0]);
}

void CopyTrainerId(u8 *dst, u8 *src)
{
    s32 i;
    for (i = 0; i < TRAINER_ID_LENGTH; i++)
        dst[i] = src[i];
}

static void InitPlayerTrainerId(void)
{
    u32 trainerId = (Random() << 16) | GetGeneratedTrainerIdLower();
    SetTrainerId(trainerId, gSaveBlock2Ptr->playerTrainerId);
}

// L=A isnt set here for some reason.
static void SetDefaultOptions(void)
{
    // BEGIN URANIUM PATHFINDER SLICE — default text speed (config/rpg2gba.h).
#if RPG2GBA_FAST_TEXT_DEFAULT == TRUE
    gSaveBlock2Ptr->optionsTextSpeed = OPTIONS_TEXT_SPEED_FAST;
#else
    gSaveBlock2Ptr->optionsTextSpeed = OPTIONS_TEXT_SPEED_MID;
#endif
    // END URANIUM PATHFINDER SLICE
    gSaveBlock2Ptr->optionsWindowFrameType = 0;
    gSaveBlock2Ptr->optionsSound = OPTIONS_SOUND_MONO;
    gSaveBlock2Ptr->optionsBattleStyle = OPTIONS_BATTLE_STYLE_SHIFT;
    gSaveBlock2Ptr->optionsBattleSceneOff = FALSE;
    gSaveBlock2Ptr->regionMapZoom = FALSE;
}

static void ClearPokedexFlags(void)
{
    gUnusedPokedexU8 = 0;
    memset(&gSaveBlock1Ptr->dexCaught, 0, sizeof(gSaveBlock1Ptr->dexCaught));
    memset(&gSaveBlock1Ptr->dexSeen, 0, sizeof(gSaveBlock1Ptr->dexSeen));
}

void ClearAllContestWinnerPics(void)
{
    s32 i;

    ClearContestWinnerPicsInContestHall();

    // Clear Museum paintings
    for (i = MUSEUM_CONTEST_WINNERS_START; i < NUM_CONTEST_WINNERS; i++)
        gSaveBlock1Ptr->contestWinners[i] = sContestWinnerPicDummy;
}

static void ClearFrontierRecord(void)
{
    CpuFill32(0, &gSaveBlock2Ptr->frontier, sizeof(gSaveBlock2Ptr->frontier));

    gSaveBlock2Ptr->frontier.opponentNames[0][0] = EOS;
    gSaveBlock2Ptr->frontier.opponentNames[1][0] = EOS;
}

static void WarpToTruck(void)
{
    // BEGIN URANIUM PATHFINDER SLICE — new-game spawn override (S8.4).
    // Redirect the new-game start to the Uranium player's-house ground floor
    // (Map049 @ 7,7, URANIUM_START_MAP) so the slice is reachable on boot.
    // Revert this block to restore vanilla new-game behavior.
    //
    // CAPTURE-TUTORIAL HARNESS — 2026-08-02: the
    // destination MUST be set here, before DoMapLoadLoop() runs (called from
    // CB2_NewGame(), which calls NewGameInitData(), which calls this
    // function) — a second SetWarpDestination+WarpIntoMap() call AFTER
    // CB2_NewGame() returns only patches gMapHeader/location, it does not
    // redo the field task/camera/OAM setup DoMapLoadLoop already ran for the
    // FIRST destination, so the player visually stays on the old map with
    // mismatched collision data and locks up. To go back to the normal
    // player's-house spawn, swap this back to the MOKI_TOWN_PLAYERS_HOUSE_1F
    // call below (kept commented, not deleted).
    // SetWarpDestination(MAP_GROUP(MAP_MOKI_TOWN_PLAYERS_HOUSE_1F), MAP_NUM(MAP_MOKI_TOWN_PLAYERS_HOUSE_1F), WARP_ID_NONE, 7, 7);
    //
    // Previous POST-QUIZ spawn, kept for the starter-grant repro: the lab at
    // (14,8). (14,18) — just inside the entrance rug — crosses a row of "Hey,
    // where are you going?" barrier triggers at y=16 (coord_events gated on
    // VAR_TEMP_F==0, the fresh-boot default) that shove the player back south;
    // (14,8) spawns past them, level with Theo (13,8), two rows below the
    // professor's row (6).
    // SetWarpDestination(MAP_GROUP(MAP_MOKI_TOWN_PROFESSOR_LAB), MAP_NUM(MAP_MOKI_TOWN_PROFESSOR_LAB), WARP_ID_NONE, 14, 8);
    //
    // Moki Town (20,44), four tiles east of the capture tutorial's coord_event
    // column. The tutorial fires from (16,43)/(16,44)/(16,45) — do NOT spawn on
    // those. It must be approached HORIZONTALLY: x=16 is solid at y=40/41/42
    // (verified by decoding the collision bits of data/layouts/MokiTown/map.bin,
    // 72x64), so the "spawn north of the trigger in the same column" idea walks
    // you into a wall. Row y=44 is passable clear across x=11..22, and (20,44)
    // is clear of every object event on that row (Bambo 15,44 / Chyinmunk 12,44
    // / Orchynx 13,44 / Theo 16,45). Walk west to fire.
    SetWarpDestination(MAP_GROUP(MAP_MOKI_TOWN), MAP_NUM(MAP_MOKI_TOWN), WARP_ID_NONE, 20, 44);
    // END URANIUM PATHFINDER SLICE
    WarpIntoMap();
}

void Sav2_ClearSetDefault(void)
{
    ClearSav2();
    SetDefaultOptions();
}

void ResetMenuAndMonGlobals(void)
{
    gDifferentSaveFile = FALSE;
    ResetPokedexScrollPositions();
    ZeroPlayerPartyMons();
    ZeroEnemyPartyMons();
    ResetBagScrollPositions();
    ResetPokeblockScrollPositions();
}

void NewGameInitData(void)
{
#if IS_FRLG
    u8 rivalName[PLAYER_NAME_LENGTH + 1];
#endif
    if (gSaveFileStatus == SAVE_STATUS_EMPTY || gSaveFileStatus == SAVE_STATUS_CORRUPT)
        RtcReset();

#if IS_FRLG
    StringCopy(rivalName, gSaveBlock1Ptr->rivalName);
#endif
    gDifferentSaveFile = TRUE;
    gSaveBlock2Ptr->encryptionKey = 0;
    ZeroPlayerPartyMons();
    ZeroEnemyPartyMons();
    ResetPokedex();
    ClearFrontierRecord();
    ClearSav1();
    ClearSav3();
    ClearAllMail();
    gSaveBlock2Ptr->specialSaveWarpFlags = 0;
    gSaveBlock2Ptr->gcnLinkFlags = 0;
    InitPlayerTrainerId();
    PlayTimeCounter_Reset();
    ClearPokedexFlags();
    InitEventData();
    ClearTVShowData();
    ResetGabbyAndTy();
    ClearSecretBases();
    ClearBerryTrees();
    SetMoney(&gSaveBlock1Ptr->money, 3000);
    SetCoins(0);
    ResetLinkContestBoolean();
    ResetGameStats();
    ClearAllContestWinnerPics();
    ClearPlayerLinkBattleRecords();
    InitSeedotSizeRecord();
    InitLotadSizeRecord();
    gPlayerPartyCount = 0;
    ZeroPlayerPartyMons();
    ResetPokemonStorageSystem();
    DeactivateAllRoamers();
    gSaveBlock1Ptr->registeredItem = ITEM_NONE;
    ClearBag();
    NewGameInitPCItems();
    ClearPokeblocks();
    ClearDecorationInventories();
    InitEasyChatPhrases();
    SetMauvilleOldMan();
    InitDewfordTrend();
    ResetFanClub();
    ResetLotteryCorner();
    WarpToTruck();
    if (IS_FRLG)
        RunScriptImmediately(EventScript_ResetAllMapFlagsFrlg);
    else
        RunScriptImmediately(EventScript_ResetAllMapFlags);
#if IS_FRLG
        StringCopy(gSaveBlock1Ptr->rivalName, rivalName);
#endif
    ResetMiniGamesRecords();
    InitUnionRoomChatRegisteredTexts();
    InitLilycoveLady();
    ResetAllApprenticeData();
    ClearRankingHallRecords();
    InitMatchCallCounters();
    ClearMysteryGift();
    WipeTrainerNameRecords();
    ResetTrainerHillResults();
    ResetTrainerTowerResults();
    ResetContestLinkResults();
    SetCurrentDifficultyLevel(DIFFICULTY_NORMAL);
    ResetItemFlags();
    ResetDexNav();
    ClearFollowerNPCData();
}

// BEGIN URANIUM PATHFINDER SLICE — boot straight into a new game (S8 boot gate).
// Invoked from intro.c right after the copyright screen (save-block pointers + heap
// are already up). Skips the Rayquaza intro, title screen, and Birch speech: stamps
// a default identity (the Birch speech is the only thing that normally sets name +
// gender), then runs the stock new-game init + warp (CB2_NewGame -> NewGameInitData ->
// WarpToTruck, itself redirected to the Uranium spawn).
//
// The moving-truck cutscene CB2_NewGame would normally arm (ExecuteTruckSequence:
// shaking room + locked controls) is suppressed inside CB2_NewGame itself (overworld.c,
// same sentinel). It MUST be swapped there, not here: CB2_NewGame's DoMapLoadLoop()
// consumes the field callback synchronously before returning, so the previous
// `gFieldCallback = NULL` on this side was always a no-op (it ran after the truck task
// had already been created). Revert this function + the intro.c call site +
// the overworld.c block to restore vanilla boot.
static const u8 sUraniumDefaultName[] = _("RED");

void CB2_StartUraniumSlice(void)
{
    // BEGIN URANIUM EMBEDDED SAVE — boot-continue instead of always-new-game.
    // A stamped state blob wins over flash, and the order matters: it used to
    // be the other way round, and any leftover .sav on the test device
    // silently shadowed the stamped state (2026-08-01 boot-walk — the
    // lab-doorstep ROM booted into the player's house from an older build's
    // save, with the player object failing to spawn: no sprite, dead input).
    // A stamped ROM is a review artifact and must reproduce ITS state on every
    // boot, on any device, regardless of save-file residue. TryLoad() returns
    // FALSE untouched when the blob is absent (magic == 0), so a pristine ROM
    // still falls through to the flash save below and a player keeps their
    // in-game saves across launches. Pristine ROM + empty flash falls through
    // to the new-game boot — the regression harness always runs that path.
    // (Consequence, by design: on a stamped ROM an in-game save is inert —
    // the next boot returns to the stamped state, not to where you saved.)
    // CB2_InitCopyrightScreenAfterBootup already ran LoadGameSave(SAVE_NORMAL)
    // before handing control here, so a valid flash save is already sitting in
    // the save blocks; TryLoad() overwrites it in place.
    // Walker builds keep always-new-game: the walker is a boot-chain takeover
    // and a continued save would bypass it.
#if URANIUM_MAP_WALKER == FALSE
    if (UraniumEmbeddedSave_TryLoad() || gSaveFileStatus == SAVE_STATUS_OK)
    {
        SetMainCallback2(CB2_ContinueSavedGame);
        return;
    }
#endif
    // END URANIUM EMBEDDED SAVE
    gSaveBlock2Ptr->playerGender = MALE;
    StringCopy(gSaveBlock2Ptr->playerName, sUraniumDefaultName);
    // BEGIN URANIUM MAP WALKER — mark walker active BEFORE the map load.
    // The actual field callback is armed inside CB2_NewGame (overworld.c), because
    // CB2_NewGame's DoMapLoadLoop() consumes gFieldCallback synchronously — setting it
    // here after CB2_NewGame() returns is a no-op (the truck-suppression comment above
    // documents the same trap). We only flip sWalkerActive here so the runtime gates
    // (NPC spawn suppression, bounds-clamp collision, step-script suppression) are in
    // effect DURING the map load, not just after it.
#if URANIUM_MAP_WALKER == TRUE
    UraniumWalker_Begin();
#endif
    // END URANIUM MAP WALKER
    CB2_NewGame();
    // TEST HARNESS (KEPT indefinitely — user decision 2026-07-13: standing HM/
    // field-move test rig while slices expand, expected to grow per-HM; strip only
    // for a release ROM): make rock smash usable from a fresh boot —
    // EventScript_RockSmash gates on FLAG_BADGE03_GET + a non-egg party mon knowing
    // MOVE_ROCK_SMASH (checkfieldmove, scrcmd.c). Must run AFTER CB2_NewGame():
    // NewGameInitData() zeroes the party inside it. ScriptSetMonMoveSlot also syncs
    // PP; SetBoxMonData handles checksum/encrypt.
    FlagSet(FLAG_BADGE03_GET);
    // TEMPORARILY DISABLED 2026-07-21 to test the S6b rival-battle LOSS route:
    // with only the (type-disadvantaged) starter in the party, losing to Theo
    // is reachable. Restore both lines to bring back the rock-smash harness.
    // ScriptGiveMon(SPECIES_GEODUDE, 5, ITEM_NONE);
    // ScriptSetMonMoveSlot(0, MOVE_ROCK_SMASH, 0);

    // ---- NEXT TEST HARNESS (post-S7 frontier) — DISABLED; uncomment to use ----
    // Skips the whole opening chain: boot already holding Raptorch, having
    // BEATEN Theo (won the S6b battle -> FLAG_LOST_FIRST_BATTLE clear) and
    // finished the PokePod scene at Theo's house (VAR_QUEST_LOG = 2), with
    // running shoes and NO Geodude. Leaves the player at the S8 frontier (the
    // west-exit Pokedex ceremony, gated VAR_QUEST_LOG >= 2). If you enable this,
    // keep the rock-smash rig above disabled — both seed gPlayerParty.
    // Uranium ids mirror data/scripts/uranium_flags.h; the base macros are
    // C-visible via constants/flags.h + constants/vars.h. Offsets: verify
    // against uranium_flags.h if the flag registry is ever renumbered.
    //   VAR_POKEMONTEST (var 151) = the single starter-choice var, read
    //   everywhere downstream (incl. S8); value 2 == Raptorch.
    // ScriptGiveMon(SPECIES_RAPTORCH, 5, ITEM_NONE);
    // FlagSet(FLAG_SYS_POKEMON_GET);                 // party shows in START menu
    // FlagSet(FLAG_SYS_B_DASH);                      // running shoes
    // FlagSet(RPG2GBA_GLOBAL_FLAGS_START + 32);      // FLAG_HAS_RAPTORCH
    // FlagSet(RPG2GBA_GLOBAL_FLAGS_START + 0);       // FLAG_RECEIVED_STARTER
    // FlagClear(RPG2GBA_GLOBAL_FLAGS_START + 10);    // FLAG_LOST_FIRST_BATTLE (won)
    // VarSet(RPG2GBA_VARS_START + 93, 2);            // VAR_POKEMONTEST = Raptorch
    // VarSet(RPG2GBA_VARS_START + 53, 2);            // VAR_QUEST_LOG = 2 (S6b+S7 done)

    // ---- POST-QUIZ HARNESS (starter-grant repro) — DISABLED 2026-08-02 ----
    // Superseded by the capture-tutorial harness below; kept for the next time
    // the lab machine/battle needs a fresh repro. To re-arm: uncomment these
    // two lines plus the TryMoveObjectEventToMapCoords, disable the block
    // below, and point WarpToTruck() back at the lab (14,8).
    //
    // Uses SSC (+19), the quiz-COMPLETE latch set at the very end of
    // Map050_EV005_Page1 (pory line 283) — NOT SSB (+18), which the 2026-07-22
    // version of this harness used by mistake. SSB is only the quiz-ACCEPTED
    // latch, read by Page1's first instruction (`goto_if_set ..._SSB` -> jump
    // straight into the quiz body), so SSB drops you INTO the quiz rather than
    // past it. With SSC set and VAR_QUEST_LOG still 0, Map050_EV005_Dispatch
    // falls through to Page2 (the post-quiz professor idle) and the quiz does
    // not re-run.
    // VarSet(RPG2GBA_VARS_START + 93, 2);           // VAR_POKEMONTEST = Raptorch
    // FlagSet(RPG2GBA_SELFSWITCH_FLAGS_START + 19); // quiz-complete latch (Map050_EV005_SSC)
    // The professor (local id 2) defaults to his quiz-time spot (14,6),
    // directly south of the machine (14,5) — the only tile from which the
    // machine is reachable (map.json collision: the machine alcove is walled
    // at x=13/15, so (14,6) is the sole approach). At the end of the real quiz
    // Map050_EV005_Page1_Move6 walks him one tile right (to 15,6) and faces him
    // left; since we skip straight past the quiz, replicate that step-aside
    // here so the machine isn't blocked.
    // TryMoveObjectEventToMapCoords(2, MAP_NUM(MAP_MOKI_TOWN_PROFESSOR_LAB), MAP_GROUP(MAP_MOKI_TOWN_PROFESSOR_LAB), 15, 6);

    // ---- CAPTURE-TUTORIAL HARNESS — ACTIVE 2026-08-02 ----
    // Lands the player in Moki Town in the state left behind by BOTH the lab
    // rival battle (Map050 EV019) and the PokePod scene at Theo's house
    // (Map172 EV004), so the capture tutorial is the next thing available:
    // walk west onto the coord_event column and it fires.
    //
    // NOTE it defeats the chapter suite's fresh-start guarantee — everything up
    // to and including the PokePod scene is skipped. Comment this block out and
    // revert the WarpToTruck spawn before running the suite.
    //
    // VAR_QUEST_LOG is the whole progression ladder for this slice, and the
    // tutorial's dispatcher reads it as a >= chain:
    //     >= 4  -> end (tutorial already done)
    //     >= 2  -> Page3, the capture tutorial      <- we want exactly this
    //     >= 1  -> Page2, "go fetch Theo" text only
    //     else  -> Page1
    // 0 = fresh boot, 1 = rival battle done (EV019 addvar), 2 = PokePod done
    // (Map172 setvar), 4 = tutorial done (Map032 setvar; 3 is never written).
    // So set exactly 2 — 3 would still work but is not a real value, and 4
    // silently skips the tutorial forever.
    VarSet(RPG2GBA_VARS_START + 53, 2);            // VAR_QUEST_LOG = 2 (post-PokePod)
    // VAR_POKEMONTEST must agree with the party mon and the FLAG_HAS_* below —
    // the tutorial reads it to pick its species text. A mismatch is cosmetic,
    // not a soft-lock, but looks broken. 1=Orchynx, 2=Raptorch, 3=Eletux.
    VarSet(RPG2GBA_VARS_START + 93, 2);            // VAR_POKEMONTEST = Raptorch
    // The starter has to actually exist: FLAG_HAS_* and FLAG_SYS_POKEMON_GET are
    // bookkeeping only, and setting them without a real mon leaves an empty
    // party behind a party-shaped menu. EV019 normally does the givemon.
    ScriptGiveMon(SPECIES_RAPTORCH, 5, ITEM_NONE);
    FlagSet(FLAG_SYS_POKEMON_GET);                 // party shows in the START menu
    FlagSet(FLAG_SYS_B_DASH);                      // running shoes (granted earlier in the chain)
    FlagSet(RPG2GBA_GLOBAL_FLAGS_START + 0);       // FLAG_RECEIVED_STARTER
    FlagSet(RPG2GBA_GLOBAL_FLAGS_START + 32);      // FLAG_HAS_RAPTORCH
    FlagClear(RPG2GBA_GLOBAL_FLAGS_START + 10);    // FLAG_LOST_FIRST_BATTLE (won the rival battle)
    // FLAG_SYS_POKEDEX_GET is deliberately NOT set — the tutorial grants it
    // (along with 5 Poke Balls) as part of what we are here to test.
    //
    // No TryMoveObjectEventToMapCoords needed: Moki Town's ON_TRANSITION script
    // clears FLAG_TEMP_11/FLAG_TEMP_14 while VAR_QUEST_LOG is in [2,4), which
    // un-hides Theo (local 20 @16,45) and Bambo (local 21 @15,44) at their own
    // standing spots. The tutorial addobject's its other actors itself.
}
// END URANIUM PATHFINDER SLICE

static void ResetMiniGamesRecords(void)
{
    CpuFill16(0, &gSaveBlock2Ptr->berryCrush, sizeof(struct BerryCrush));
    SetBerryPowder(&gSaveBlock2Ptr->berryCrush.berryPowderAmount, 0);
    ResetPokemonJumpRecords();
    CpuFill16(0, &gSaveBlock2Ptr->berryPick, sizeof(struct BerryPickingResults));
}

static void ResetItemFlags(void)
{
#if OW_SHOW_ITEM_DESCRIPTIONS == OW_ITEM_DESCRIPTIONS_FIRST_TIME
    memset(&gSaveBlock3Ptr->itemFlags, 0, sizeof(gSaveBlock3Ptr->itemFlags));
#endif
}

static void ResetDexNav(void)
{
#if USE_DEXNAV_SEARCH_LEVELS == TRUE
    memset(gSaveBlock3Ptr->dexNavSearchLevels, 0, sizeof(gSaveBlock3Ptr->dexNavSearchLevels));
#endif
    gSaveBlock3Ptr->dexNavChain = 0;
}
