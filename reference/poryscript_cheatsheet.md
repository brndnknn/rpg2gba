# Poryscript cheatsheet (conversion-agent reference)

> Stable prompt chunk injected into every conversion-agent call (Phase 4 §4.4).
> A compact reference for the Poryscript constructs the agent is allowed to emit.
> Authoritative grammar: huderlem/poryscript README. Keep this terse and correct.

## Script blocks

```poryscript
script MyMap_OldManScript {
    lock
    faceplayer
    msgbox("Hello, {PLAYER}!")
    release
    end
}
```

- `lock` / `release` bracket an NPC interaction; `faceplayer` turns the NPC.
- `end` terminates a script; `return` hands back to a caller; `goto Label` jumps.

## Dialogue

- `msgbox("text")` — standard message box. Use this for all dialogue (never a raw
  `message` macro).
- `msgbox("text", MSGBOX_YESNO)` then branch on `var(VAR_RESULT)` for yes/no.
- Multi-line: embed `\n` (line) and `\p` (scroll/new page) inside the string.
- Placeholders: `{PLAYER}`, `{RIVAL}`, `{STR_VAR_1}`.

## Items, Pokémon, money

- `giveitem(ITEM_POTION, 1)` — grant items (fanfare is automatic).
- `givemon(SPECIES_PIKACHU, 5)` — grant a Pokémon at a level.
- `checkitemspace` / `removeitem(ITEM_X, n)` / `additem`.
- `givemoney(100, 0)` / `removemoney(50, 0)`.

## Trainer battles

```poryscript
trainerbattle_single(TRAINER_YOUNGSTER_BEN, "Before text", "Defeat text")
```

Use the `TRAINER_*` constant from the provided data; double battles use the
`_double` variants.

## Flags and variables

- `setflag(FLAG_X)` / `clearflag(FLAG_X)` / `if (flag(FLAG_X))`.
- `setvar(VAR_X, 3)` / `addvar(VAR_X, 1)` / `if (var(VAR_X) == 3)`.
- Use only named constants from the flag registry — never raw numeric IDs.

## Control flow

```poryscript
if (flag(FLAG_RECEIVED_STARTER)) {
    msgbox("You already have a partner.")
} elif (var(VAR_STORY) > 2) {
    msgbox("...")
} else {
    msgbox("...")
}
```

- Loops: express RPG Maker loop/break (codes 112/113) with a labeled `goto`
  anchor and a guarding `if`.

## Movement

```poryscript
applymovement(2, MyMap_Movement_Walk)
waitmovement(0)

movement MyMap_Movement_Walk {
    walk_left
    walk_left
    face_down
}
```

## Warps

- `warp(MAP_LITTLEROOT_TOWN, 5, 8)` — transfer the player (RPG Maker code 201).

## Self-switches

RPG Maker self-switches (A–D) become per-event flags using the deterministic
pattern `FLAG_MAP{MAP_ID}_EVENT{EVENT_ID}_SS{LETTER}` (e.g.
`FLAG_MAP042_EVENT003_SSA`). Do not vary this format.
