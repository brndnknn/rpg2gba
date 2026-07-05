# Item constant census — Uranium `items.dat` (607 items) vs pokeemerald-expansion fork

> Run 2026-07-04 (Sonnet sub-agent under /delegate; alias finding spot-verified by
> the lead against `git show HEAD:engine/include/constants/items.h`). Resolves the
> open fidelity question parked in `reference/oracle_harvest_2026-07-02.md` §E.

Method: parsed `reference/item_names.json` + `item_internal_names.json` (607 items,
id 0=NONE excluded → 607 nonzero), ran each through the *actual*
`rpg2gba.pbs_converter._naming.to_constant("ITEM", name)` (imported live, not
reimplemented), and compared against the fork's `ITEM_*` enum pulled from the
**pristine committed engine tree** (`git show HEAD:engine/include/constants/items.h`,
`git show HEAD:engine/src/data/items.h`). Fork display names parsed from
`.name = ITEM_NAME("...")` blocks in `src/data/items.h`. Script:
`/tmp/.../scratchpad/census.py`, raw output: `census_results.json`.

## Counts

| Category | Count |
|---|---|
| 1. Exact constant match | 496 |
| 2. Renamed vanilla item (minted const ≠ any fork const, but is really a vanilla item) | **0** |
| 3. True Uranium originals | 103 |
| 4. Near-miss / uncertain (human review) | 8 |
| **Total** | **607** |

### Category 1 breakdown (informational, not asked for as separate bucket but material to the finding)

Of the 496 exact matches:
- **472** match a fork item's *current* canonical name directly (e.g. `ITEM_POTION`, `ITEM_POKE_BALL`).
- **24** match a fork **backward-compat enum alias** — the fork's `include/constants/items.h`
  already carries `ITEM_OLDNAME = ITEM_NEWNAME, // Pre-Gen VI name`-style aliases for
  most Gen 3–6 item renames. `to_constant()` on Uranium's old-style display name mints
  exactly the alias identifier, which **is** in the fork's `ITEM_*` symbol set (`load_fork_constants`
  just regexes LHS identifiers, alias or not), so these already resolve as "no engine work needed"
  today, with zero code changes:

  | id | Uranium display | minted/matched const | fork alias target |
  |---|---|---|---|
  | 14 | Thunderstone | ITEM_THUNDERSTONE | ITEM_THUNDER_STONE |
  | 29 | TinyMushroom | ITEM_TINYMUSHROOM | ITEM_TINY_MUSHROOM |
  | 46 | Ylw Apricorn | ITEM_YLW_APRICORN | ITEM_YELLOW_APRICORN |
  | 47 | Blu Apricorn | ITEM_BLU_APRICORN | ITEM_BLUE_APRICORN |
  | 48 | Grn Apricorn | ITEM_GRN_APRICORN | ITEM_GREEN_APRICORN |
  | 49 | Pnk Apricorn | ITEM_PNK_APRICORN | ITEM_PINK_APRICORN |
  | 50 | Wht Apricorn | ITEM_WHT_APRICORN | ITEM_WHITE_APRICORN |
  | 51 | Blk Apricorn | ITEM_BLK_APRICORN | ITEM_BLACK_APRICORN |
  | 52 | BrightPowder | ITEM_BRIGHTPOWDER | ITEM_BRIGHT_POWDER |
  | 59 | SilverPowder | ITEM_SILVERPOWDER | ITEM_SILVER_POWDER |
  | 117 | BlackGlasses | ITEM_BLACKGLASSES | ITEM_BLACK_GLASSES |
  | 123 | NeverMeltIce | ITEM_NEVERMELTICE | ITEM_NEVER_MELT_ICE |
  | 125 | TwistedSpoon | ITEM_TWISTEDSPOON | ITEM_TWISTED_SPOON |
  | 150 | Stick | ITEM_STICK | ITEM_LEEK |
  | 152 | DeepSeaTooth | ITEM_DEEPSEATOOTH | ITEM_DEEP_SEA_TOOTH |
  | 153 | DeepSeaScale | ITEM_DEEPSEASCALE | ITEM_DEEP_SEA_SCALE |
  | 157 | Up-Grade | ITEM_UP_GRADE | ITEM_UPGRADE |
  | 180 | Parlyz Heal | ITEM_PARLYZ_HEAL | ITEM_PARALYZE_HEAL |
  | 191 | EnergyPowder | ITEM_ENERGYPOWDER | ITEM_ENERGY_POWDER |
  | 410 | X Defend | ITEM_X_DEFEND | ITEM_X_DEFENSE |
  | 411 | X Special | ITEM_X_SPECIAL | ITEM_X_SP_ATK |
  | 426 | Dowsing MCHN | ITEM_DOWSING_MCHN | ITEM_DOWSING_MACHINE |
  | 483 | RageCandyBar | ITEM_RAGECANDYBAR | ITEM_RAGE_CANDY_BAR |
  | 606 | Exp. All | ITEM_EXP_ALL | ITEM_EXP_SHARE |

This is why category 2 is empty: every well-known Gen-3-era rename in the curated
list the task specified (Parlyz Heal, X Defend, Elixer-family, Thunderstone,
Itemfinder, X Special, Direhit, TinyMushroom, BalmMushroom*, EnergyPowder,
DeepSeaTooth/Scale, TwistedSpoon, SilverPowder, BlackGlasses, NeverMeltIce,
Up-Grade, RageCandyBar) either (a) isn't actually present in Uranium's data under
the old spelling — Uranium already stores the *modern* name ("Stardust", "King's
Rock", "Silk Scarf", "Dire Hit", "Black Belt", "Energy Root", "PP Up"/"PP Max",
"Amulet Coin" are all stored modern and land in the 472), or (b) is present under
the old spelling and the fork already carries the matching alias (the 24 above),
or (c) doesn't exist in Uranium's item list at all (checked: no `BalmMushroom` /
`Balm Mushroom` entry in `item_names.json` or `item_internal_names.json` —
Uranium simply never included that item, so it's a non-issue rather than a
solved one). Net: **no action item exists for category 2 today** — the
fork's own back-compat aliases already absorbed the whole rename problem the task
was worried about. (Caveat: this only holds for names the fork chose to alias.
If Uranium had used a rename the fork did *not* alias, it'd fall in category 2 —
none did, in this corpus.)

### items.py's actual behavior for category 1 (the "collide/redefine/skip/resolve" question)

Two separate outputs, two separate answers:

- **Constant mint** (`_ItemResolver.constant`, `items.py:205-214`): computes
  `needs = bool(self.fork_items) and const not in self.fork_items` — for every
  category-1 item (modern-name or alias-name) `needs=False`, recorded into
  `id_map` as **not needing engine work**. This part **resolves correctly today**,
  no code change needed — matching a fork name (canonical or legacy alias) is
  already recognized.
- **Constant emission** (`emit_constants`, `items.py:270-288`, written
  `items.py:304` to `out_dir/include/constants/items.h`): mints
  `#define {const} {it.id}` using **Uranium's own item ID**, not the fork's real
  enum value, for ALL 607 items including the 496 exact matches. Lands in a
  *separate* generated file with its own include guard
  (`GUARD_URANIUM_CONSTANTS_ITEMS_H`, not the fork's), so there is **no live
  collision today** — but the code's own comment (`items.py:284-286`) flags it as
  an unresolved landmine: *"these are Uranium's own item IDs. They overlap
  vanilla ITEM_* numbering — V6 integration must reconcile them with the fork
  enum."* I.e. today = deferred, not solved.
- **Data table emission** (`emit_items_info`/`_emit_one`, `items.py:238-267`,
  written `items.py:305` to `out_dir/src/data/items.h`): **DOES redefine/collide**
  in the sense that matters — see "Emission strategy" below. Every item, category-1
  included, gets a struct entry with only `.name`/`.price`/`.description`/`.pocket`/
  `.importance` set; every behavior field (hold effect, fling, battle effect,
  TM/HM linkage, etc.) is left at its C default-zero. If this generated file is
  ever used to replace the fork's real `src/data/items.h` (same path, same
  `gItemsInfo[]` symbol, same array indices via matching `ITEM_*` names), **all
  496 exact-match vanilla items — not just the 103 originals — silently lose
  their real behavior data.** This is explicitly acknowledged in the module
  docstring (`items.py:32-38`) and the emitted file's own NOTE comment
  (`items.py:258-263`), but the scope (blast radius = all 607, not just
  originals) is not obviously flagged elsewhere.

## Emission strategy: full replacement, not additions

**`emit_items_info` (`items.py:253-267`) emits a full, complete
`const struct ItemInfo gItemsInfo[] = { ... }` literal covering all 607 Uranium
items — not a sparse/additive patch.** `entries = [_emit_one(it, r) for it in
items]` (`items.py:254`) iterates the *entire* item list with no filter for
"only originals" or "only unmapped." Written to `out_dir / "src" / "data" /
"items.h"` (`items.py:299`, `305`) — the exact same relative path as the fork's
real `engine/src/data/items.h`. If/when this lands in the fork tree as a
replacement (which is the evident intent — same path, same top-level symbol),
it **clobbers the fork's entire vanilla item behavior table**, category-1 items
included, reducing every vanilla item (Potions, Poké Balls, held items, berries,
TMs) to a name/price/pocket-only stub. This is the single biggest blast-radius
finding: the risk isn't scoped to the 103 true-Uranium-original items, it's
scoped to all 607.

`emit_constants` (`items.py:270-288`, guard `GUARD_URANIUM_CONSTANTS_ITEMS_H`)
is a separate, independently-guarded header — additive/parallel today, not a
replacement of the fork's real `include/constants/items.h`, but its own comment
flags the ID-numbering reconciliation as unresolved (see above).

## Category 3: true Uranium originals (103 total, 10-example sanity sample)

No fork counterpart under exact, normalized, or curated-rename matching — mostly
Gen 4+ evolution items, key items, mega stones (Uranium-original megas), and
Uranium-specific plot items:

| id | display | minted const |
|---|---|---|
| 432 | Explorer Kit | ITEM_EXPLORER_KIT |
| 434 | Rule Book | ITEM_RULE_BOOK |
| 440 | Pal Pad | ITEM_PAL_PAD |
| 462 | Vs. Recorder | ITEM_VS_RECORDER |
| 504 | Hair Fossil | ITEM_HAIR_FOSSIL |
| 505 | Tusk Fossil | ITEM_TUSK_FOSSIL |
| 510 | Metalynxite (Uranium mega stone) | ITEM_METALYNXITE |
| 576 | Nuclear Ball (Uranium-original ball) | ITEM_NUCLEAR_BALL |
| 585 | Uranium Core | ITEM_URANIUM_CORE |
| 600-605 | Map Scrap 1-6 (internal `EMPERORSMAP*`) | ITEM_MAP_SCRAP_1..6 |

Full 103-item list in `census_results.json` → `original`. Spot-checked several
(Hair/Tusk/Gold Fossil, Surfboard, Scuba Gear) against the fork header directly —
confirmed genuinely absent (fork stops at pre-existing HGSS/Platinum-era items it
chose to include; these later additions and all Uranium-specific items are not
there).

## Category 4: near-miss / uncertain (8, full list — needs human judgement)

Fuzzy/substring name match found a fork item with a similar name, but it's very
likely a *different* item, not a rename of the same one:

| id | Uranium display | minted const | fork near-match | verdict (my read, not authoritative) |
|---|---|---|---|---|
| 448 | Oak's Letter | ITEM_OAKS_LETTER | ITEM_LETTER ("Letter") | different item (character-specific plot letter vs generic Letter) |
| 460 | SecretPotion | ITEM_SECRETPOTION | ITEM_POTION ("Potion") | different item (HGSS Apricorn-tree item, not a Potion variant) |
| 466 | Berry Pots | ITEM_BERRY_POTS | ITEM_BERRY_POUCH ("Berry Pouch") | different item (Gen 4 key item vs Gen 6+ pouch) |
| 473 | Red Scale | ITEM_RED_SCALE | ITEM_RED_SCARF ("Red Scarf") | different item (key item vs contest scarf) |
| 475 | Pass | ITEM_PASS | ITEM_CONTEST_PASS / ITEM_PASSHO_BERRY / ITEM_RAINBOW_PASS / ITEM_TRI_PASS | different item (generic Uranium "Pass", 4-way name collision risk with fork's own "Pass"-suffixed items — same substring, not same item) |
| 523 | Bike Wheel | ITEM_BIKE_WHEEL | ITEM_BICYCLE ("Bike") | different item |
| 550 | Yoshitaka's Letter | ITEM_YOSHITAKAS_LETTER | ITEM_LETTER ("Letter") | different item (plot letter) |
| 572 | Kellyn's Letter | ITEM_KELLYNS_LETTER | ITEM_LETTER ("Letter") | different item (plot letter) |

None of these actually collide in minted constant name (no false merge risk via
`IdMap.add`) — they were flagged purely because of substring/near-length overlap
with a differently-named fork item. Recommend leaving all 8 classified as
Uranium originals; flagging here only in case a human spots one I mis-read.

## Files

The census script, raw classified JSON, and pulled fork headers lived in the
session scratchpad (ephemeral, not preserved). Method is fully described above;
re-derive by re-running `to_constant` over `reference/item_names.json` /
`item_internal_names.json` against the pristine engine headers if the full
103-item originals list is ever needed.
