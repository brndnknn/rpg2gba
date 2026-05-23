# MEMORY.md Protocol

> Externalized from CLAUDE.md's "Memory System" section. The binding rules (read
> MEMORY.md first, targeted edits, evict stale entries, don't duplicate
> CLAUDE/ROADMAP) live in CLAUDE.md. This file holds the full how-to and the
> section template — consult it when you need the detail, not every session.

## Why this exists

Scanning the full repo to rebuild context burns tokens and time. MEMORY.md is the
build agent's running notes on the state of the project — what's been done, what
each key file actually does, what decisions have been made, and what's still open.
A well-maintained MEMORY.md means the next session starts in 30 seconds, not 5
minutes.

## Structure of MEMORY.md

```markdown
# rpg2gba Agent Memory

## Current Phase
<!-- Which phase is active, what's been completed, what the next concrete task is -->

## Key File Notes
<!-- Short notes on non-obvious files. Don't duplicate what's already obvious from
     the repo layout in CLAUDE.md. Only note things that would take >30s to figure
     out from reading the file itself. -->

## Decisions Made
<!-- Architectural and data-fidelity decisions that are settled. Format:
     - [DATE] Decision: <what was decided>. Reason: <why>. -->

## Uranium-Specific Discoveries
<!-- Quirks of the Uranium source that affect converter logic.
     Things you found during Phase 0 or stumbled on later. -->

## Flag Registry Notes
<!-- Summary of any notable flag/var assignments made so far.
     Full state is in the registry file; this is just notable ones. -->

## Open Questions
<!-- Things that need the user's input before you can proceed. Clear an item
     when the user answers it. -->

## Last Session Summary
<!-- One paragraph: what you did, what you left unfinished, where to pick up. -->
```

## How to use it

**At the start of a session:**
1. Read MEMORY.md first, before any other file
2. If Current Phase or Last Session Summary tells you exactly what to do next,
   start there
3. If you need to verify something in code, check the specific file — don't
   re-scan the whole repo

**During a session:**
- Update Key File Notes when you learn something non-obvious about a file
- Add to Decisions Made when a significant decision gets settled
- Add to Open Questions when you hit something that needs user input before
  proceeding
- Add to Uranium-Specific Discoveries when you find a quirk

**At the end of a session (or at a natural stopping point):**
1. Update Last Session Summary with what you did and where to pick up
2. Update Current Phase to reflect progress
3. Clear any Open Questions that got answered

## Rules

- Update MEMORY.md with targeted edits, not full rewrites — other sections
  shouldn't be disturbed when you update one
- Keep entries concise. If a Key File Note is longer than two sentences, it
  probably belongs in `reference/` as a proper doc, not here
- Don't put information here that's already in CLAUDE.md or ROADMAP.md — link or
  reference instead
- **Eviction discipline:** keep at most the 2 most recent Last Session Summary
  entries and only *live* Open Questions in MEMORY.md. Move retired summaries and
  resolved-question breadcrumbs to `reference/memory-archive.md`. Before retiring
  a resolved question, confirm its conclusion is captured in Decisions Made or
  Uranium-Specific Discoveries; promote it if it isn't.
- MEMORY.md is committed to git. Session-to-session state persists in version
  history. Don't gitignore it.
