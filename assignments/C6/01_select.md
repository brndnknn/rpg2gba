# Task 1 — Select: which rows does this chapter walk? (20 points)

## Goal

Implement `beat_gen/select.py`. Each manifest row goes into exactly one bucket:

- **owned**: the generator will produce a beat for it
- **refused**: a `Refusal` with a named upstream blocker. The chapter stays red until the
  blocker is fixed (R7; C6 plan B2's answer: "an honest refusal counts as done").
- **elsewhere**: an `Elsewhere`: another chapter owns it (`later`), no chapter does
  (`unreachable`), or it sits behind a field-move obstacle this chapter can't pass (`blocked`)

## Learning objectives

- Turn three independently produced data sources into one decision without letting any of
  them silently win
- Keep a **closed vocabulary** (blockers) closed: an unknown reason is a crash, not a default
- Recognise when two models disagree (story says live, capability says blocked) and encode
  which one governs

## Inputs

| Input | Where from | Keyed by |
|---|---|---|
| `rows` | `playtest.archetypes.load_chapter_rows(ch)` | manifest order |
| `verdicts` | `story_state.model.build_chapter_stories([...chain up to ch])[ch].rows` | row id |
| `floors` | `beat_floor.walk.floor_for_chapter(ch, build_dir=Path("output/uranium-build"))` | row id |

`build_chapter_stories` takes the **whole chain** up to and including the chapter. CH05's story
comes from `["CH01", …, "CH05"]`, not `["CH05"]`, because the seed is the predecessor's end
state.

## The rule table

Apply these in this order; the first rule that matches decides:

1. No floor for the row → **raise** `ValueError`. (Every manifest row has a floor by
   construction; a missing one is an upstream bug.)
2. `page`/`branch` row, no story verdict → refused, `story-state`, `no_story_verdict`.
   Seam and terrain rows skip the story rules entirely.
3. Status `refused` → refused, `blocker_for(head)`, `reason=head`, `detail=` the whole string.
4. Status `undetermined` → refused, `story-state`, `undetermined`.
5. Status `later` / `unreachable` → elsewhere, carrying `owner` for `later`.
6. `row.requires` non-empty **and** the row is not itself an obstacle → elsewhere, `blocked`.
7. Floor refused → refused, `blocker_for(first floor refusal's reason)`.
8. Otherwise → owned.

Keep manifest order inside every bucket.

## Hints

- **`blocker_for` is a table, not an if-chain.** A `dict[str, Blocker]` is the whole
  function plus one `KeyError` → `ValueError` conversion. Collect the vocabulary by measuring
  it, not by guessing: iterate CH01–CH05, count first floor reasons and story-refusal heads,
  and write down what you see. (There are five floor reasons and four story heads today, plus
  the stair and obstacle reasons from C5 and C7.)
- **Rule 6 is the interesting one.** Read C7 Task 3's "trap" again. `row.requires` includes
  *reachability-derived* capabilities: an item ball across water "requires" surf without
  containing a single surf command. The question "is this row the obstacle itself?" has
  exactly one source of truth since C7 Task 3: does its floor carry `blocked_obstacle`?
- **Why does rule 3 beat rule 7?** And why does rule 6 beat rule 7? Answer before you code;
  the tests pin both, and Q2 asks.
- A story-refusal string is `"head"` or `"head:detail"`. `str.partition(":")` returns the
  head in both cases.

## Tests

`tests/test_beat_gen_select.py`: 10 blocker-table cases, the rule table one rule at a time,
precedence (story > blocked > floor), manifest order, and two real-data tests. CH05 has 35
owned, 8 blocked (the surf items) and 0 refused. On CH01, every row lands in exactly one
bucket and there are refusals.

## Questions (commit message)

1. The story model and the capability model disagree about CH05's `map036/ev008`. Which one is
   right, and why is it correct for `select` to side with the capability model rather than to
   "fix" `story_state`?
2. Justify the precedence *refused > blocked > floor-refused* in one or two sentences each.
3. How many CH01 rows did you refuse per blocker? Does that agree with C6 plan B2's
   measurement (29 text / 13 non-literal args / 7 script head / …)? If not, why not? (Hint: B2
   counted floor refusals only.)
