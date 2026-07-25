# Text corpus scan — 2026-07-24

Static scan of the emitted `.pory` corpus under `output/uranium-build/` using
the new validator (`src/rpg2gba/text_validator/`), run via:

```
python -m rpg2gba.text_validator scan --output output/uranium-build --engine engine
```

**978 string literals scanned** across `scripts/*.pory`, `staging/scripts/*.pory`,
and `porymap/dispatch/*.pory`. **45 raw issues**, all in two rules
(`TEXT_HTML_TAG`, `TEXT_LINE_WIDTH`) — collapsing duplicate stage-copies of the
same source line (the corpus intentionally scans `scripts/` and
`staging/scripts/`, which both carry near-identical copies of most maps), this
is **7 distinct dialogue strings**, all in `Map050` (the professor's Pokémon
Trainer Aptitude Test / starter-choice scene). `TEXT_MARKUP` and `TEXT_CHARMAP`
found **zero** issues in the current corpus.

## The `<br>...</br>` question — verdict

**`<br>` is real, documented Essentials markup — but it is not what's reaching
the ROM right now. A sibling tag from the same family is.**

`<br>` belongs to Essentials' **DrawTextEx** rich-text tag system, documented
in `reference/scripts_dump/058_DrawText.rb:385-417`:

```
<b> ... </b>       - Formats the text in bold.
<i> ... </i>       - Formats the text in italics.
...
<br>               - Causes a line break.
<c=X> ... </c>     - Color specification. ...
<c2=X> ... </c2>   - Color specification where the first half is the base color...
...
<fs=X> ... </fs>   - Changes the font size to X.
```

This is a **different subsystem** than the ordinary dialogue window's
backslash escape codes (`\c[n]`, `\v[n]`, `\wt[n]`, `\PN`, ...) — DrawTextEx is
Essentials' generic rich-text renderer, used by its own hardcoded UI screens.
No Essentials tag in this family (`<br>` included) ever pairs with a closing
`</br>` — `<br>` is self-closing/void, like HTML's own `<br>`; the closing-tag
forms that exist are for the *paired* tags (`</b>`, `</c2>`, `</fs>`, ...).
**`</br>` does not appear anywhere in the Uranium source tree or in the
current output corpus** — I grepped both exhaustively (raw `.rxdata`,
`messages.dat`, and the decompressed `reference/scripts_dump/*.rb` Ruby
scripts). The user's description was evidently an approximate paraphrase of
this tag family, not a literal transcription.

### Where `<br>` itself actually lives

Searching `messages.dat` (Essentials' `MessageTypes` UI-string store,
`RPG2GBA_URANIUM_SRC/Data/messages.dat`) across **all 22 message types**, `<br>`
appears in **11 of 3,463 entries**, exclusively under **type 22
(`script_texts`)** — e.g.:

```
"{1:s}PP: ---<br>TYPE/{2:s}"                          (battle scene PP/type readout)
"Registered<br>"                                        (phone contact list)
"Player<r><c3={1}>{2}</c3><br>"                          (save screen)
"Name<r>{1}<br>"  / "IDNo.<r>{1}<br>" / "Time<r>...<br>" (Hall of Fame)
```

Cross-referenced against the decompressed script sources, these are Essentials'
own hardcoded engine UI screens: `090__PokeBattle_Scene.rb`,
`148_PScreen_HallOfFame.rb`, `138__PScreen_Save.rb`, `133_PScreen_Phone.rb`.
**No converter or pbs_converter module currently reads `messages.dat` type 22**
(`dump_messages.rb` dumps it to `script_texts.json`, but nothing consumes that
file — only `phone_messages.json` type 21 has an actual reference sidecar
committed). pokeemerald has its own native implementations of all of these
screens (battle HUD, save menu, Hall of Fame, PC/phone equivalents), so this
text was never going to be literally transplanted — **`<br>` does not reach
the ROM today because nothing in the pipeline ingests it, not because
anything strips it.**

### Where the *live* bug actually is

Searching `Map*.rxdata` directly (the source of ordinary Show-Text dialogue,
which the transpiler *does* convert) turned up **zero** `<br>` occurrences —
but the validator's `TEXT_HTML_TAG` rule found `<b>`, `</b>`, `<c2=X>`, and
`</c2>` **live in the actual emitted corpus**, in `Map050`'s Aptitude Test
dialogue. Confirmed against the raw Uranium source
(`RPG2GBA_URANIUM_SRC/Data/Map050.rxdata`):

```
"...both will take the <b>Pokémon Trainer Aptitude Test</b>."
"\PN, are you ready to take the <b>Trainer Aptitude Test</b>?"
"\ch[2,0,<c2=043c3aff>Attack it right away!,\c[4]Wait and see what it does.,<c2=65467b14>Throw a Pokéball...]"
```

This is a Uranium author using DrawTextEx tags *inline in ordinary dialogue*
(not just in engine UI screens) — and unlike `\c[n]`/`\PN`, the transpiler has
no handling for the DrawTextEx `<...>` family at all, so these pass straight
through `translate_text_codes`'s scan (which only checks for backslash escapes
and braces, `deterministic.py:111`) into the emitted `.pory` string untouched.
**7 distinct dialogue strings, all in `Map050`, currently carry this and will
render as literal `<b>`/`<c2=...>` characters in the ROM.** This is exactly
the class of bug the user's boot-walk report was flagging — same tag family,
different specific tags, genuinely live rather than latent.

Full list (7 unique strings, `Map050_EV004_Page1` / `Map050_EV005_Page1` /
`Map050_EV005_Page3` / `Map050_EV005_TestBody`):

```
"The <b>Pokémon Trainer Aptitude Test</b> sorts Trainers into three basic
types: Defensive, <c2=043c3aff>Offensive</c2>, and<c2=65467b14> Balanced."

"<c2=043c3aff>Offensive</c2> trainers receive the Fire Pokémon
<c2=043c3aff>Raptorch</c2>. It's strong and speedy, but can be hard to control."

"<c2=65467b14>Balanced</c2> trainers receive the Water Pokémon
<c2=65467b14>Eletux</c2>. Its calm, collected nature allows it to adapt to
any situation."

"Before you get your starters, though, you both will take the
<b>Pokémon Trainer Aptitude Test</b>."

"{PLAYER}, are you ready to take the <b>Trainer Aptitude Test</b>?"
   (appears at both Map050_EV005_Page1 and _Page3)

"Haha... I dig your spirit, kid! Well, that's it for the
<b>Trainer Aptitude test</b>."
```

**Recommendation (not implemented — out of scope for this validator):** the
transpiler needs a DrawTextEx-tag handling rule alongside its existing
backslash-code table — most likely strip `<b>`/`</b>`/`<c2=X>`/`</c2>` and keep
the wrapped text (pokeemerald has no bold/color-run rendering in ordinary
msgbox text, so these are DROP candidates, same shape as the existing `\c[n]`
color-code and `<fs=n>` font-size handling in `deterministic.py`). That
decision belongs to whoever owns `conversion_agent/deterministic.py`, not to
this validator.

## TEXT_LINE_WIDTH — the 3 findings

All 3 are the same string, duplicated across `CommonEvents.pory`'s three
network-unavailable stubs (`CommonEvent_004`/`005`/`006`):

```
msgbox("The Tandor Network is currently unavailable.")
```

This is **not** wrapped in `format(...)` (a hand-authored fallback message,
not transpiler output) — 46 characters, measured at **232px** against the
**216px** message-box budget (see "How line width was measured" below). It
renders exactly as written with no re-wrap, so this is a real overflow: on
real hardware/mGBA this line will run past the message box's right edge or
get truncated depending on how `msgbox` handles an unbroken excess line.
Fix is a one-line edit wherever `CommonEvents.pory`'s network-stub text is
authored (outside this validator's ownership — not touched here).

## How line width was measured, and what it approximates

Grounded in the vendored engine (`engine/`, pinned per
`engine/RPG2GBA_VENDOR.md`), not assumed:

- **Message-box usable width: 216px** (27 tiles × 8px/tile). Source:
  `sStandardTextBox_WindowTemplates[0]` (`engine/src/menu.c`), `.width = 27`;
  `AddTextPrinterForMessage` prints into this window at `x = 0` with no extra
  margin subtracted (the frame is drawn outside the window's own bounds).
- **Font: `FONT_NORMAL`**, the font `AddTextPrinterForMessage` actually uses
  for field message boxes (`engine/src/menu.c`). Letter spacing 0
  (`sFontInfos[FONT_NORMAL]`, `engine/src/text.c`).
- **Per-glyph widths**: `gFontNormalLatinGlyphWidths[]` (`engine/src/fonts.c`),
  indexed by the literal charmap byte value (0x00–0xFF; the table's second
  256 entries, 0x100–0x1FF, are an icon/extra-symbol glyph page dialogue text
  never reaches — `CHAR_EXTRA_SYMBOL`, `engine/src/text.c` — and are
  correctly out of scope). Transcribed verbatim into
  `src/rpg2gba/text_validator/engine_metrics.py`.
- **Control codes contribute 0px**: matches `GetStringWidth`'s explicit skip
  of `EXT_CTRL_CODE_BEGIN` (`{PAUSE ...}`, `{COLOR ...}`, etc.) operand bytes
  (`engine/src/text.c`).

Where this is a genuine **approximation**, documented in
`engine_metrics.py`'s `measure_line_width_px` docstring:

1. **`{PLAYER}` / `{STR_VAR_n}` / name placeholders**: the engine measures the
   *real* runtime buffer's glyphs; this validator has no runtime, so it
   charges a fixed **42px** (7 chars × the font's modal 6px glyph width — 7 is
   pokeemerald's `PLAYER_NAME_LENGTH`). A very long nickname could still
   overflow a line this reports as fitting; a short one leaves slack this
   reports as tighter than reality.
2. **A character present in source text but absent from `charmap.txt`**:
   charged the widest known glyph (10px) as a conservative stand-in — but this
   case is already reported independently by `TEXT_CHARMAP`, so it never
   surfaces as a *silent* wrong width; both issues fire together.
3. **Scope split for `format(...)`-wrapped strings** (the majority of the
   corpus — `format_pory_dialogue` in `deterministic.py` wraps almost every
   transpiler-emitted `msgbox`): poryscript re-wraps these to the box width at
   *compile* time using its own algorithm, which this validator cannot see
   from source text (the transpiler also pre-flattens all `\n` breaks to
   spaces before wrapping, so there are no explicit line boundaries left to
   check in the source). Checking whole-segment width on a `format()`-wrapped
   string would false-positive on nearly the entire corpus (most dialogue
   lines are 60-90+ source characters by design, meant to be wrapped).
   Instead, for `format()`-wrapped strings this validator checks only the
   **longest single whitespace-delimited token** — the one thing poryscript's
   wrap algorithm cannot fix (no space to break on). For strings *not* wrapped
   in `format(...)` (rare — 3 of 978 in the current corpus, all the
   `CommonEvents.pory` network stubs above), the validator checks the whole
   line directly, since it renders exactly as written.

## TEXT_MARKUP and TEXT_CHARMAP — zero findings, and why that's expected

Neither rule found anything in the current corpus. This is the expected
"clean" result, not a validator gap:

- `TEXT_MARKUP` (unconverted `\c[n]`/`\v[n]`/`\wt[n]`/etc.): the raw codes
  *are* present in the corpus, but only inside `# UNHANDLED code 101: ...`
  comment lines the transpiler emits when `translate_text_codes` bails
  (`deterministic.py`) — e.g. 11 occurrences of `\wt[`, `\c[`, `\v[` combined
  across `CommonEvents.pory` and `Map050.pory`. Comments never reach the ROM
  (poryscript strips them), so the extractor deliberately skips comment lines
  — this is the transpiler's own fail-loud queueing mechanism doing its job,
  cross-referenced against `output/uranium-build/transpile_unhandled.jsonl`
  (111 entries, none text-markup related in what reached string literals).
- `TEXT_CHARMAP`: the corpus's one prior charmap-legality mechanism
  (`tileset_converter.assembly.normalize_pory`, run at real assemble time in
  `scripts/assemble_pathfinder.py`) already keeps the corpus clean by
  substituting `*`→`~`, `[`→`(`, `]`→`)`, and toggling `\"` to typographic
  quotes before anything would fail. This validator's `TEXT_CHARMAP` rule
  reuses that exact function (rather than reimplementing charmap-legality
  decisions — CLAUDE.md §4.3 spirit: one owner per concept) as an earlier,
  pre-assemble copy of the same fail-loud gate, so an all-clear here means
  the real assemble step would also pass.

## Open questions / gaps

- **`Scripts.rxdata` was not searched.** Map dialogue (`Show Text` event
  commands) lives in plain `Map*.rxdata`, which I grepped directly and
  exhaustively. But some Uranium dialogue is issued from Ruby *script* code
  (`pbMessage(...)` calls inside `Scripts.rxdata`, which is zlib-deflated) —
  I did not decompress and search that. The `reference/scripts_dump/*.rb`
  files already checked into the repo are (per their header) hand-dumped
  decompressions of a subset of scripts, not exhaustive — the `<b>`/`<c2=X>`
  finding above came from event-command dialogue (`Map050.rxdata` directly),
  not from scanning `Scripts.rxdata`. If any hand-invoked LLM-tail conversion
  ever starts pulling raw strings out of `Scripts.rxdata`, this validator
  would still catch DrawTextEx tags in whatever it emits as `.pory` — but a
  census of what's *in* `Scripts.rxdata` today would need a decompression
  pass this task didn't do.
- **No golden coverage yet for a real `<b>`/`<c2=X>` corpus string** — the
  test suite's `TEXT_HTML_TAG` cases use synthetic `<br>` and a
  hand-transcribed `<b>...<c2=X>...` example modeled on the real Map050 text,
  not the literal Map050 string, to keep the test file independent of corpus
  content that could change.
- **The `PLACEHOLDER_WIDTH_PX = 42` constant is a documented guess**, not a
  measurement — see "How line width was measured" above. If the transpiler's
  {PLAYER}-adjacent name budget policy is ever formalized elsewhere, this
  constant should be reconciled against it rather than kept as an independent
  assumption.
- **Wiring into the pipeline as a fail-loud gate was not done** — see the
  companion report to the lead agent for the exact one-line change and why it
  wasn't made directly (touches `scripts/assemble_pathfinder.py`, outside this
  task's file-ownership list).
