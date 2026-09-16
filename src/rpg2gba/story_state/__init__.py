"""Per-row story-state extraction (REDERIVATION_PLAN.md §16.3 C2a).

C2a's job: for every manifest row (page trunk or branch arm), derive what
game state it READS (page conditions, arm guards) and WRITES (switch/
variable/self-switch commands, recognized script idioms, inlined common
events), plus a per-condition-family outcome table classifying how a code-111
arm becomes live (player input, random, evaluable state, an engine fork, a
harness primitive, a capability, or not yet modelled).

C2b (liveness, saturation, ordering, chapter chaining) is built on top of this
package's output and is out of scope here -- `state.py`'s dataclasses are its
contract, so they are kept small, frozen, and exact.
"""
