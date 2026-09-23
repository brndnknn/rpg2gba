# Task 3 — `engine-audit` Checks the `FLAG_SYS_*` Mapping (30 points)

## Goal

Make `python -m rpg2gba.story_state engine-audit` verify that every engine-held unlock attribute
resolves to a `FLAG_SYS_*` constant the fork actually defines — through the fork-capability
index, not an ad-hoc file read.

Operator ruling: `REDERIVATION_PLAN.md` §16.3, "C8 shape" ruling **(b)** — engine-held unlock
attributes become `EngineKey`s mapping to native flags, "asserted by the floor and **checked by
`engine-audit`**". The first half landed; the audit half is this task.

## Learning objectives

- Move a correctness guarantee from a test into the tool that is supposed to own it, and
  understand why that is not redundant
- Use an existing capability index instead of grepping a header (CLAUDE.md §4.7)
- Extend a report object without breaking its `ok` contract

## What exists today, and what is missing

### The mapping exists

`src/rpg2gba/ruby_subset/builtins.py:95`:

```python
ENGINE_ATTRIBUTES: dict[tuple[str, str], EngineAttribute] = {
    ("$PokemonGlobal", "runningShoes"):       EngineAttribute("running_shoes", "FLAG_SYS_B_DASH"),
    ("$Trainer", "pokedex"):                  EngineAttribute("pokedex", "FLAG_SYS_POKEDEX_GET"),
    ("$Trainer", "pokegear"):                 EngineAttribute("pokegear", "FLAG_SYS_POKENAV_GET"),
    ("$PokemonGlobal", "seenStorageCreator"): EngineAttribute("seen_storage_creator", "FLAG_SYS_PC_LANETTE"),
}
```

> **Note the count.** The ruling's prose names **three** attributes. The table has **four** —
> `seenStorageCreator → FLAG_SYS_PC_LANETTE` is real, in use, and absent from the ruling text.
> Your check covers the **table**, not the prose. Q1 asks you to say what you would do if the
> two disagreed in the other direction (prose naming something the table lacks).

### The check exists — in the wrong place

`tests/test_ruby_subset_evaluate.py:426` has:

```python
@pytest.mark.skipif(not ENGINE_FLAGS_PATH.exists(), reason="...")
def test_engine_attribute_flags_exist_in_the_fork():
    text = ENGINE_FLAGS_PATH.read_text(encoding="utf-8")
    for (ns, attr), engine_attr in bi.ENGINE_ATTRIBUTES.items():
        assert f"#define {engine_attr.flag}" in text, (...)
```

Two problems, and they are the whole task:

1. **It is a pytest assertion, not an audit check.** `engine-audit` is the command whose job is
   "tell me what the engine owes"; a developer running it gets a clean bill of health that never
   looked at this. The guarantee is real but invisible to the tool that should report it.
2. **It greps header text.** CLAUDE.md §4.7 says symbol existence goes through the
   fork-capability index. A substring search for `#define FLAG_SYS_B_DASH` also matches a
   commented-out line, a different header, or `#define FLAG_SYS_B_DASH_OLD` — it is the exact
   class of check §4.7 exists to replace.

## The source of truth you must reuse

| Thing | Where | How |
|---|---|---|
| Fork-capability index | `conversion_agent/fork_index.py:356` | `load_or_build() -> ForkIndex`; then `flag in index.constants` |
| The attribute table | `ruby_subset/builtins.py:95` | `ENGINE_ATTRIBUTES` — iterate it, never retype it |

`ForkIndex.constants` is a `set[str]` built from every `#define NAME` in
`engine/include/constants/*.h` plus the asm constants, so all four `FLAG_SYS_*` names land in it.
`load_or_build` is tree-hash-keyed and cached in `output/uranium-build/fork_index.json`, so
calling it from the audit is cheap.

**Do not** re-read `engine/include/constants/flags.h`. **Do not** build your own index.

## Names the tests require

The test file calls this code directly, so these names are part of the contract rather than
your choice. Everything *not* in this table is yours.

| Name | Where | Shape |
|---|---|---|
| `engine_index` | keyword parameter on `audit()` | `ForkIndex \| None = None` |
| `unresolved_engine_flags` | field on `AuditReport` | tuple of findings, `()` when clean; **counts toward `ok`** |
| `engine_flag_check_skipped` | field on `AuditReport` | `None` when the check ran; a truthy marker when it could not; **does not count toward `ok`** |
| `.flag` | attribute on a finding | the `FLAG_SYS_*` name it wanted |

`format_report` must name the section `unresolved_engine_flags`, and must print it **even when
the count is zero** — as `unresolved_engine_flags (0)`, matching the existing sections' style. A
check that only appears in the output when it fails is a check a reader cannot confirm ran.

## Requirements

### R1 — A new audit check

In `src/rpg2gba/story_state/engine_audit.py`, add a check that every
`ENGINE_ATTRIBUTES[...].flag` resolves in the fork index. Follow the module's existing shape:
the audit builds an `AuditReport` whose fields are lists of findings, and
`AuditReport.ok` (line ~122) is `True` iff the *failure* fields are all empty.

- Add the two fields named in the table above to `AuditReport`.
- **Include it in `ok`.** An unresolved flag means the pipeline will emit a symbol the fork does
  not define — that is a hard failure, exactly what §4.7's forward gate is for. Contrast with
  `intro_seed_unread` / `deferred_obligations`, which are informational and deliberately excluded
  from `ok`; Q2 asks you to explain the difference.
- Report it in `format_report` (line ~558) as its own section, matching the existing style.

### R2 — Failure must name the fix

A finding must identify the attribute (`$Trainer.pokedex`), the flag it wanted
(`FLAG_SYS_POKEDEX_GET`), and the fact that it was not found in the index. A developer reading
the audit output should not have to open the source to know what to do.

### R3 — Degrade honestly when the fork is absent

`audit()` is called in tests with synthetic trees, and `load_or_build` needs a real `engine/`.
A check that quietly no-ops when its input is missing is **worse than no check**, because it
reports OK. So a skipped check must say it was skipped.

The seam is specified, because the tests call it:

- `audit()` takes **`engine_index: ForkIndex | None = None`**. Injection keeps `audit()` pure
  over its inputs, which is how the rest of that function already works.
- `run_real_audit()` is where the real index is obtained, and where a failure to build it is
  caught and turned into `engine_index=None`.
- `engine_index=None` must produce a **visible "not verified" marker** in the report — distinct
  both from "verified clean" and from "verified and broken". Three states, not two.

**That marker does not count toward `ok`.** "I could not check" is not the same failure class
as "I checked and it is broken", and it is structurally the same as the existing
`intro_seed_unread` / `deferred_obligations` fields, which are reported but excluded from `ok`.
An unresolved flag (R1) *does* count toward `ok`. Getting these two the right way round is the
point of the requirement — Q2 and Q3 both probe it.

The genuinely open decision left to you is narrower: **what `run_real_audit` does when
`load_or_build` raises** — swallow and mark unverified, or let it propagate. Say which and why
in Q3.

### R4 — Retire or demote the old test

Once the audit owns the check, decide what happens to
`test_engine_attribute_flags_exist_in_the_fork`. Deleting it, keeping it as a cheap unit-level
guard, or rewriting it to exercise the new audit check are all defensible — but leaving two
independent implementations of the same check is exactly the §4.3 drift this assignment's other
two tasks are cleaning up. Q4 asks.

## Hints

- Read `run_real_audit` (`engine_audit.py:534`) and `audit` (`engine_audit.py:289`) first. The
  separation is deliberate: `run_real_audit` gathers real inputs, `audit` is pure over them.
  Your new check should sit on whichever side keeps it testable — that choice *is* R3.
- The existing test file `tests/test_story_state_engine_audit.py` shows the fixture style:
  synthetic fenced C trees under `tmp_path`, `monkeypatch.setattr(ea, "TRANSITIONS", ...)` to
  isolate one declaration at a time, plus two real-tree tests at the end
  (`test_real_engine_fenced_writes_found`, `test_run_real_audit_is_clean`). The second one is
  `skipif`-guarded on the corpus being present — note how, and match it.
- **`test_run_real_audit_is_clean` must still pass.** All four flags do currently resolve, so a
  correct implementation leaves the real audit green. If your change turns it red, your check is
  wrong before the fork is.
- A `FLAG_SYS_*` constant is defined as `(SYSTEM_FLAGS + 0x1)`, not a bare number — you are
  checking that the *name* is known, never its value.

## Tests

`tests/test_story_state_engine_audit_flags.py`: a synthetic index missing one flag produces one
finding naming attribute and flag; a complete index produces none; `ok` is False when a flag is
unresolved; the report text contains the new section; the absent-fork path behaves as R3
specifies; and a real-tree test asserting all four `ENGINE_ATTRIBUTES` flags resolve against the
vendored `engine/`.

## Questions (commit message)

1. The ruling's prose names three attributes; the table has four. You checked the table. What
   should happen if the prose named a *fifth* that the table lacked — is that a code bug, a doc
   bug, or an audit finding?
2. Why does an unresolved flag belong in `ok`, when `intro_seed_unread` and
   `deferred_obligations` deliberately do not?
3. What does `run_real_audit` do when `load_or_build` raises, and why is that better than the
   alternative? Separately: why is "could not verify" excluded from `ok` when "unresolved flag"
   is included — what would a CI run on a machine without `engine/` report under each choice?
4. What did you do with the old pytest check, and why?
5. `engine-audit` exit code before and after, and the new section's output on a clean tree.
