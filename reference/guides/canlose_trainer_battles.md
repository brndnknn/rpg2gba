# Can-lose trainer battles (Essentials `canlose` → pokeemerald)

> Reference + design input for converting Uranium story battles the player is
> allowed to lose without a game-over. Written 2026-07-21 from the Moki lab
> rival battle (Map050 EV019 = the first Theo fight); verified against the
> vendored engine at `engine/`.

## The Essentials pattern

RMXP/Essentials story battles use `pbTrainerBattle(...)` inside a **code-111
conditional branch** and read its return value:

```
pbTrainerBattle(PBTrainers::RIVAL, "Theo", _I("<lose speech>"), doublebattle,
                party_id, canlose, ...)
```

- Returns **true** if the player won, **false** if they lost.
- When `canlose` is true, a loss does **not** white out — the function returns
  and the script runs the else branch (loss aftermath), then the two branches
  usually reconverge to shared "after the battle" choreography.
- `party_id` may be an expression (`pbGet(151)+18`), i.e. the opponent's party
  is chosen at runtime from a game variable.

Example outcome semantics from the Theo fight:

| Player result | RMXP branch | switch 35 (= `FLAG_LOST_FIRST_BATTLE`) |
|---|---|---|
| Won  | `then` (`[111]`) | **OFF** |
| Lost | `else` (`[411]`) | **ON** |

A later scene (Theo's-house EV004, our S7) branches on switch 35 to play the
"you beat him" vs "he beat you" variant. So **the outcome must be recorded**, or
downstream scenes desync.

## The pokeemerald native analog: `TRAINER_BATTLE_EARLY_RIVAL`

pokeemerald has exactly one built-in "lose but continue" battle: the early-rival
mode (`trainerbattle_earlyrival` macro / `TRAINER_BATTLE_EARLY_RIVAL`), used by
the mainline first-rival fights (FRLG Oak's lab, RSE Route 103).

```
trainerbattle_earlyrival TRAINER_X, <flags>, <defeat_text>, <victory_text>
```

- On a loss it does **not** game-over, and it sets **`VAR_RESULT`**
  (`gSpecialVar_Result`): **TRUE = player lost**, FALSE = player won. The field
  script branches on `VAR_RESULT` after the battle — functionally equivalent to
  Essentials' `canlose` return value.
- `defeat_text` = shown when the **trainer** is defeated (player won);
  `victory_text` = shown when the **trainer** wins (player lost). Two slots only.

### The two flag bits — pick carefully (`include/constants/battle.h`)

| Flag | Value | Loss behavior |
|---|---|---|
| `RIVAL_BATTLE_HEAL_AFTER` | 1 | Lose → heal party → **continue**. What we want. |
| *(none)* | 0 | Lose → **white-out**. |
| `RIVAL_BATTLE_TUTORIAL` | 3 (= `HEAL_AFTER \| 2`) | Adds `BATTLE_TYPE_FIRST_BATTLE` (`battle_setup.c:1322`) — the Birch-intro type where the opponent is framed as **wild and FLEES at low HP**, so the player *can't* actually lose. |

**Trap:** `RIVAL_BATTLE_TUTORIAL` is the obvious-looking choice (mainline uses it
for Oak's lab) but it makes the enemy flee — the player can never lose, and the
battle is framed as "wild." For a genuinely losable battle use
`RIVAL_BATTLE_HEAL_AFTER` **alone**.

### Engine bug this exposed (fixed)

Because mainline earlyrival is *always* either `TUTORIAL` (can't lose) or `0`
(white-out), the "player loses **and** we heal-and-continue" path was **dead
code**. It had a real bug: `BattleScript_RivalBattleLost`
(`data/battle_scripts_1.s`) printed the trainer win text then `end2` with **no
`waitmessage`**, so `end2` raced the return-to-field transition and the game
**froze on the victory-text screen**. Fixed by adding `waitmessage
B_WAIT_TIME_LONG` before `end2` (URANIUM sentinel fence), mirroring the win path.
Any new use of `HEAL_AFTER`-alone depends on this fix.

## Constraints vs. Essentials (what does NOT map cleanly)

1. **Heal-or-whiteout only.** Native earlyrival supports "lose → heal → continue"
   or "lose → white-out." A canlose battle that should continue **without**
   healing has no native mode — it would need a small custom-C battle flag
   (Phase-6 style) or a workaround.
2. **Two text slots.** Rich, branch-specific *field* dialogue (Bamb'o's full
   "I'm surprised you lost… let me heal you" speech) must be converted into the
   post-battle **field script**, branching on `VAR_RESULT` — not the battle.
3. **Party must be staged into the engine.** The opponent (`TRAINER_*`) and its
   party must exist in `engine/src/data/trainers.party` + a constant in
   `include/constants/opponents.h`. The Phase-2 trainer converter emits these to
   `intermediate/trainers.json`, but they are **not yet wired into the slice
   assembly** — the Theo parties were hand-added. Staging converted trainers is a
   pipeline gap (see the pipeline TODO).
4. **Runtime party selection.** `party_id = pbGet(151)+18` becomes a
   `switch (var(VAR_POKEMONTEST))` over the pre-resolved `TRAINER_*` constants.

## Transpiler strategy (for the pipeline fix)

> Full implementation design lives in `canlose_battle_pipeline_plan.md`
> (transpiler + trainer staging, open decisions, test/sequencing plan).

Target shape for a canlose `pbTrainerBattle` in a code-111 branch:

```
[optional switch over the party-selecting var] {
  trainerbattle_earlyrival(TRAINER_..., RIVAL_BATTLE_HEAL_AFTER,
                           <defeat_text>, <victory_text>)
}
if (var(VAR_RESULT) == 1) { <emit RMXP else/loss branch> }
else                      { <emit RMXP then/win branch> }
# reconverged tail follows
```

Detection: a code-111 whose condition string contains `pbTrainerBattle(` with a
truthy `canlose` arg. The then-branch is the win aftermath, the else-branch
(code-411) is the loss aftermath. Record the outcome flag if the RMXP branches
set a switch (map it through the flag registry, don't hardcode).

## Uranium fact worth pinning (corrects an earlier note)

In the first Theo fight the **player always has the type advantage** — Theo's
counter-pick is the starter *weak* to yours (Orchynx>Eletux, Raptorch>Orchynx,
Eletux>Raptorch via the Grass/Fire/Water triangle). So **winning is the expected
outcome**; losing means deliberately throwing the fight (the prof's dialogue even
asks "did you let him win on purpose?"). Any earlier note saying "Theo gets the
type that beats yours" is backwards.
