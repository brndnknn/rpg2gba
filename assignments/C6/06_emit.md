# Task 6 — Emit: Python source, byte-identical (20 points)

## Goal

Implement `beat_gen/emit.py`: `ChapterPlan` → the text of `chNN.generated.py`. This is the
first code in the repo that writes Python source (C6 plan §1: "zero hits for `ast.unparse`,
`codegen`…").

## The layout

```python
"""GENERATED -- do not edit.

<a few lines: which chapter, which command regenerates it>
"""
from __future__ import annotations

from rpg2gba.playtest.archetypes.generic import generic_beat, stair_beat
from rpg2gba.playtest.archetypes.trainer import trainer_beats
from rpg2gba.playtest.chapter import ChapterBuilder

ch05 = ChapterBuilder('CH05', doc='...', predecessor='CH04')

trainer_beats(
    ch05,
    chapter_id='CH05',
    beat_prefix='m036e004_trainer',
    group='m036e004_trainer',
    event_id=4,
    map_id=36,
    rider=False,
)

generic_beat(
    ch05,
    ...
)

CHAPTER = ch05.build()
```

The keyword order inside a call is `chapter_id`, the name keyword (`TEMPLATE_CALLS[...][2]`),
`group`, `rows` (only for non-archetype templates, which can't derive rows themselves), then
`beat.kwargs` in their (already sorted) order. `test_render_call_exact_layout` pins one call
byte for byte.

## Decision: string templates, not `ast.unparse`

You could build an `ast.Module` and call `ast.unparse`. Don't. Its formatting is
version-dependent (it changed between 3.9 and 3.12), so a Python upgrade would diff every
generated module. Plain string assembly with a fixed layout is boring and stable. The
flip side is that **you** own escaping, which is why `render_value` exists and refuses
everything it can't render stably.

## Hints

- `render_value`: `repr()` is stable for `None`, `bool`, `int` and `str`. Tuples you build
  yourself, recursively; remember the one-element tuple's trailing comma
  (`test_render_value` has the case). Check `bool` before `int`, because `True` is an `int`.
  A `float` is refused on purpose: its repr is stable, but a float in a template kwarg is
  almost certainly a bug upstream.
- Imports: collect `(module, name)` from `TEMPLATE_CALLS` for the templates **used**, group
  by module, and sort both levels. Always add `ChapterBuilder`.
- Build the module as a list of chunks, then `"\n".join(...)`, and finish with exactly one
  trailing newline. A test checks that there isn't a second one.
- `ast.literal_eval(render_value(v)) == v` is a round-trip property the tests use. It's a
  good self-check for any value renderer.

## Tests

`tests/test_beat_gen_emit.py`: `render_value` accept/reject/round-trip, the exact call layout,
`rows` only where it belongs, reserved-kwarg rejection, header and tail, `compile()`,
minimal sorted imports, call order, the builder line, no `predecessor=None`, byte-identity,
empty-plan rejection.

## Questions (commit message)

1. Name two ways this emitter could produce different bytes for the same plan if you weren't
   careful, and how your code rules each out.
2. Why pass `rows=` to `generic_beat` but not to `trainer_beats`?
