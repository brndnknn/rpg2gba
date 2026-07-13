# Novel-cluster review — round 1 (2026-06-12)

Build-agent review of the triage NOVEL residue (FABLES_DECISIONS #3, runbook item 2.4).
Input: `scripts/run_stats.py --novel` over the live queue (214 entries; 87 novel across
29 clusters, from CommonEvents + maps 1–8 — map 8 entries come from its interrupted
partial conversion and will re-log when the bulk run redoes it).

Spoiler policy: all content described mechanically; no plot.

**Method note:** judged from the queue descriptions + prior session source knowledge;
the planned Haiku source-snippet fan-out was skipped — descriptions were sufficient
for every cluster this round.

## Conclusions by cluster family

| Family (entries) | Conclusion |
|---|---|
| `111:cond6` player-facing checks (14) | **Translatable candidate.** pokeemerald reads player facing natively (`specialvar VAR_RESULT, GetPlayerFacingDirection` + compare). Most uses gate stair/counter nudge logic. Candidate deterministic translation rule — needs a recorded decision before promotion. |
| `102` Show Choices >2 options (13) | **Needs-engine (small).** pokeemerald `multichoice` + `gMultichoiceLists` entries; ties to the G1 finding of agent-invented `MULTI_*` ids (the agent already emits `multichoice(MULTI_X)` + switch scaffolding). Phase 5/6: define the lists, resolve the ids. |
| `111:cond12:get_character(0).onEvent?` (9) | **Phase 5.** "Player standing on this event" — equivalent to a player-position == event-position check; positions are known at Phase 5 wiring. |
| CE4/5/6 online-lobby clusters: `$lobbyreset`, `GTS.open`, `PVP.open`, `pbSave`, `system(browser)`, `202` (≈10) | **Superseded once `strip_list.json` lands** (runbook Phase 3). Today's rule 3 is inactive only because the file doesn't exist yet. |
| Phone/rematch family: `655:pbSet` CE35, `111:cond12:pbPhoneBattleCount`, `355:trainer`/`655:result` (≈9) | **Needs-engine.** Phone registration/rematch (already in the UNHANDLED table family) + Custom Trainers runtime builder (`createPhoneTrainer`/`customTrainerBattle`, script 216 — recorded Medium/Phase-4 ADAPT). Signatures belong in the `uranium_script_calls.md` queue-it table, **but that file is prompt-borne (frozen until run end)** — add `pbPhoneBattleCount`, `createPhoneTrainer`, `customTrainerBattle`, `jvNextRewardPhone` then. |
| RACING minigame: `111:cond11` input polling, `122` coords, `203` scroll, `232`/`235` pictures (≈9, CE10/11) | **§10 user call.** Real-time button-polled racing minigame with picture-based HUD; no GBA field-script analogue — needs an engine minigame (ADAPT) or an outcome substitute (STRIP/stub). Recommendation: stub now, list for Phase 8 ADAPT (consistent with the Custom Mode precedent). |
| Dream/vision sequence: CE86/87 `102` choices, `122` save-coords, `355` bag-disable + party swap, `207` anim (≈7) | **§10 user call.** A replay/vision feature: stashes party + disables bag, warps to a scene, restores after. Needs engine state (party stash). Recommendation: ADAPT in Phase 6/8 (appears wired into progression via its guide CE); stub meanwhile. |
| `207` Show Animation (5) | **Phase 8 polish.** Cosmetic emotes/flourishes; the exclaim case maps to pokeemerald field effects (`FLDEFF_EXCLAMATION_MARK_ICON`) — partial deterministic map possible later. |
| `111:cond12:$PokemonBag.pbQuantity` (3) | **Translatable candidate.** Direct `checkitem(ITEM_*, qty)` → VAR_RESULT equivalent; blocked only on the item-constant mapping (same drift family as the G1 ITEM finding). |
| `111:cond12:$game_map.map_id == N` (2, CE12) | **Phase 5.** Shared CE branching on current map id; specialize at map wiring (map constants land in Phase 5). |
| VS-intro cutscene: `231` pictures + `241` custom BGM (2, CE76) | **Drop to standard battle intro** (cosmetic; pokeemerald `trainerbattle` has its own intro). Phase 8 polish candidate if custom VS screens are ever wanted. |
| `111:cond12:Time.now.hour` (1) | **Needs-engine (small).** Day/night check; the expansion has RTC time-of-day — map at Phase 6. |
| `111:cond12:Kernel.pbPokerus?` (1) | **Needs-engine review.** Pokérus exists in pokeemerald internals; verify a field-script accessor before mapping. |
| `111:cond12:pbNextMysteryGiftID` (1) | **Needs-engine.** Mystery-gift family (table already queues `pbReceiveMysteryGift`). |
| `355:pbPushThisBoulder` (1) | **Phase 5.** Strength boulder push is native pokeemerald (pushable boulder objects + flags); wire at object placement. |

## §10 calls — RESOLVED (user, 2026-06-12)

1. **Racing minigame (CE10/11):** **STUB now → Phase 8 ADAPT.** Strip to a simple
   outcome substitute for the bulk run; list the engine minigame as a Phase 8 ADAPT
   item (consistent with the Custom Mode precedent).
2. **Dream/vision sequence (CE86/87):** **STUB now → ADAPT Phase 6/8.** Strip-stub
   meanwhile; build the party-stash engine state in Phase 6/8.
3. **Custom VS-intro (CE76):** **Accept the loss — standard battle intro.** No custom
   VS screen; pokeemerald `trainerbattle`'s own intro is the substitute. (Not even a
   Phase 8 polish item unless revisited.)

## Rule promotions (deferred, with reasons)

- Facing-check and checkitem translations are deterministic-rule candidates but are
  NEW decisions, not recorded ones — the triage rule table only encodes recorded
  decisions, so they wait for a decision-log entry.
- Phone-family signature additions wait for the `uranium_script_calls.md` unfreeze
  (post-run; the file is in the frozen static context).
