# S6 Aptitude Test — Answer Key for Each Starter

Source: `src/rpg2gba/conversion_agent/hand_conversions/Map050_EV005.pory`
(TestBody + Tally scripts). Verified against the actual scoring logic, not memory.

## TL;DR — pick the same column every time

The test has 4 questions, each with 3 answers (top/middle/bottom in the list).
Each answer feeds a tally bucket. The bucket with the most points wins. Picking
the **same position every time** guarantees a clean win with no tie ambiguity.

| Pick this answer position all 4 times | You get |
|---|---|
| **1st option** every time | **Raptorch** (Fire/Ground) → evolves Archilles |
| **2nd option** every time | **Orchynx** (Grass/Steel) → evolves Metalynx |
| **3rd option** every time | **Eletux** (Water/Electric) → evolves Electruxo |

## The 4 questions, answer-by-answer

| # | Question | 1st option → Raptorch | 2nd option → Orchynx | 3rd option → Eletux |
|---|---|---|---|---|
| 1 | "When you encounter a new kind of Pokémon in the wild, what is your first reaction?" | Attack it right away! | Wait and see what it does. | Throw a Poké Ball at it! |
| 2 | "Which of these TMs would you prefer to teach to your Pokémon?" | Hyper Beam | Protect | Hidden Power |
| 3 | "Which of the following Pokémon would win in an all-out battle?" | Gyarados | Gliscor | Ampharos |
| 4 | "What is your motivation for becoming a Pokémon Trainer?" | Becoming the very best | Exploring the region | Making new friends |

## If you want to mix answers

The scoring: each answer's column gets +1 in its own bucket (T3/T4/T5 for
col 1/2/3). After all 4 questions, the winner is decided by this exact order
of comparisons (mirrors the original RMXP argmax + 0↔1 swap):

1. Default winner = **col 3 (Eletux)**.
2. If **col 2 ≥ col 3**, winner becomes **col 2 (Orchynx)**.
3. If **col 1 ≥ col 2 AND col 1 ≥ col 3**, winner becomes **col 1 (Raptorch)** — this check runs last, so col 1 wins any tie it's part of.

Practical effect of ties:
- col1 vs col2 tie (col3 lower) → **Raptorch**
- col2 vs col3 tie (col1 lower) → **Orchynx**
- col1 vs col3 tie (col2 lower) → **Raptorch**
- All three tied (1-1-1-1 split across 4 answers isn't possible with only 4
  questions, but a 2-way split leaving one at 0 follows the rules above)

Safest bet: just pick the same column 4 times.

## After the quiz — don't forget the grant step

Per the hand-conversion (Uranium-faithful two-step, not a bug): finishing the
quiz only **announces** the result — it does **not** hand you the Pokémon.
After Bamb'o's "go ahead and take it" line, you must:

1. Walk to the **Poké Ball machine** in the lab (blue machine, red ball top,
   roughly the east side of the room).
2. Press **A** on it to actually receive the starter (`FLAG_SYS_POKEMON_GET`
   now gets set on this step too, so it should show up correctly in the
   START menu's POKÉMON list — this was the W9 fix, ROM `e20f2158`+).

If you decline the first offer, then come back and retake it (say yes the
second time), that retake-after-decline path was also fixed (W8, stale
ON_FRAME latch) — should no longer soft-lock Bamb'o.
