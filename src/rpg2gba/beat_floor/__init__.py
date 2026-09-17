"""The generic per-row floor (REDERIVATION_PLAN.md §16.3 C4, R11).

R11: "A generic page template from the source command list is the floor
for every row; archetypes are layered on top, not a fallback." This
package derives that floor directly from RMXP source -- one extractor per
plain command code (`walk.py`), per script-call head (`script.py`), per
code-111 type-12 condition family (`condition.py`), and for code 209 move
routes (`move_route.py`) -- with expected values always read from the RMXP
source, never from converted Poryscript (the proxy-oracle rule).

`assertion.py` is the shared contract every extractor module here returns
through (`FloorAssertion`/`FloorRefusal`/`RowFloor`); `walk.py` is the
per-row walker and entry point (`floor_for_map`/`floor_for_chapter`). C5's
archetype templates and C6's generator/checker consume this package's
output; neither `playtest` nor `chapter_manifest` is imported the wrong
way round (REDERIVATION_PLAN.md §16.3 C4 design).
"""
