# Hand conversions

Committed, hand-authored Poryscript for the handful of branch-heavy story
events the deterministic transpiler (`transpiler.py` + the idiom-collapse
layer in `deterministic.py`) can't reasonably reach — irreducible-tail
material per CLAUDE.md §4.1, not a place to park events that are merely
inconvenient. Loaded and spliced in by `hand_overrides.py` /
`transpile_driver.transpile_map`.

## Filename convention

One file per overridden event: `Map{mmm:03d}_EV{eee:03d}.pory`, e.g.
`Map012_EV003.pory` for map 12, event 3. The ids are parsed straight from the
filename — there is no other place they're declared, so a typo'd filename is
a wrong override, not a missing one.

## The complete-event rule

The file is the event's **entire** output. All of the event's pages, all
their script/text/movement/mart blocks — everything the classifier and the
general transpiler would otherwise have produced for this event — live here.
The driver does not merge hand-authored and generated content for one event;
it is all-or-nothing per event. If only one page of an event is the hard
part, the whole event still moves into the override file.

## Canonical-label namespace rule

Every top-level definition in the file (`script NAME { ... }`, `text NAME {
... }`, `movement NAME { ... }`, `mart NAME { ... }`) must be named
`Map{mmm}_EV{eee}` — the file's own ids — optionally followed by a free-form
`_suffix` (`_Page1`, `_Mart`, `_Page2_Move1`, whatever reads clearly). This
matches the canonical label the transpiler emits for generated events
(`Map{m:03d}_EV{e:03d}_Page{n}`, see `transpiler._page_label` /
`metadata_wiring.page_label`), so hand-authored and generated labels never
collide across events on the same map. `load_hand_overrides` enforces this at
load time and fails loud on any definition outside the file's own namespace —
that's the one collision hazard this whole layer exists to prevent, so don't
work around the check by renaming instead of fixing the label.

Hand files are written directly in this canonical scheme, so the driver does
**not** run its name-based-label rewrite (`transpile_driver._canonicalize_labels`,
which only exists to bring the *classifier* layer's name-based labels onto
the id-based scheme) over override text.

## Provenance comment

The first line of every override file is a one-line provenance comment:

```
# hand conversion (2026-07-05): <one-line why this event needed hand authoring>
```

## Still gated

Hand-authored output is not exempt from anything generated output goes
through: it flows into the same per-map fork-index gate
(`fork_index.verify_script`) as the rest of the map's spliced-together
`.pory` text, and the resulting ROM still has to pass `make modern` and the
per-slice boot gate (CLAUDE.md §9). Hand authoring buys you out of the
transpiler, not out of verification.

## Common events

Out of scope for this layer. There is currently no hand-override path for
`CommonEvents.json` entries — only map events. If a common event turns out to
need hand authoring, that's a follow-up design question, not something to
silently bolt onto this filename convention.
