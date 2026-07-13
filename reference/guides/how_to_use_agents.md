# How to Use CLAUDE.md, MEMORY.md, and system.md

**Audience:** You, Brandon — instructions for what to tell a new build agent session when starting work on rpg2gba.

---

## The Three Files and What They're For

| File | Who reads it | What it does |
|---|---|---|
| `CLAUDE.md` | Build agent | Permanent operating manual. Conventions, principles, boundaries. Rarely changes. |
| `MEMORY.md` | Build agent | Running project state. Changes every session. Replaces the need to re-scan the repo. |
| `src/conversion_agent/prompts/system.md` | Conversion agent (at runtime) | The conversion agent's instructions. Maintained by the build agent as a source file. |

The build agent reads CLAUDE.md and MEMORY.md. It also *maintains* system.md — treating it like any other source file — but it does not run as the conversion agent.

---

## Starting a New Build Agent Session

This is the exact prompt to give Claude Code (or whatever build agent you're using) at the start of a session. Copy-paste it, or keep it as a saved snippet:

```
Read CLAUDE.md, then MEMORY.md, then stop and tell me:
1. What phase we're in and what the next concrete task is
2. Any open questions from last session that need answers before we proceed
3. Anything you want to confirm before starting work

Do not read any other files until after we've talked.
```

This gives you a check-in before the agent starts doing things. If MEMORY.md is accurate, the agent should be oriented in under a minute without scanning the repo.

---

## Mid-Session: When the Agent Needs to Check Something

If the agent needs context on a specific file during a session, let it look up that file directly — that's fine. What you're preventing is the agent doing a broad re-scan ("let me read all the converter modules to understand the project") when MEMORY.md already has that context. If you see the agent doing broad scans, redirect it:

```
Check MEMORY.md first — the answer may already be there.
```

---

## Ending a Session

Before finishing any session, tell the agent:

```
Update MEMORY.md with what we did today and where to pick up next session.
Then stop.
```

The agent should update:
- **Last Session Summary** — what was done and where to resume
- **Current Phase** — if it changed
- **Decisions Made** — anything settled that wasn't already there
- **Uranium-Specific Discoveries** — anything found about the source material
- **Open Questions** — anything that needs your input next time
- Clear any Open Questions that got answered during the session

---

## When You're Starting the Project from Scratch (First Session Ever)

The first session is different — there's no existing MEMORY.md state yet. Use this prompt:

```
Read CLAUDE.md in full. Then read ROADMAP.md. Then read MEMORY.md.

This is the first session on this project. MEMORY.md is a blank template.
Your job in this session is Phase 0 reconnaissance as described in ROADMAP.md.

Before you do anything else, tell me your plan for Phase 0 and confirm
you understand the distinction between your role (build agent) and the
conversion agent that will run inside the pipeline later.
```

The confirmation step is important — the build/conversion agent distinction is the most common thing to get muddled, and it's cheapest to catch before any code is written.

---

## When to Update system.md

The build agent updates `system.md` when:
- The few-shot calibration run in Phase 4 Stage A reveals the instructions are producing bad output
- A new category of event command is discovered that needs explicit handling rules
- The output format needs to change (e.g., adding a field to the JSON schema)

Do not update system.md during an active conversion run (Stage B or Stage C). Prompt changes happen between stages. If you discover a bug mid-run, add it to MEMORY.md as an open question and address it in the next stage.

When you ask the build agent to update system.md, be explicit:

```
Update system.md to add a rule about [X]. Don't change anything else.
Show me the diff before committing.
```

---

## Quick Reference: Session Patterns

**Starting cold (new session):**
> "Read CLAUDE.md, then MEMORY.md, then stop and tell me where we are."

**Starting the project for the first time:**
> "Read CLAUDE.md, ROADMAP.md, MEMORY.md. First session. Tell me your Phase 0 plan and confirm you understand the build/conversion agent distinction."

**Picking up mid-phase:**
> "Read CLAUDE.md and MEMORY.md. Last session summary will tell you where we left off. Continue from there."

**Updating the conversion agent's instructions:**
> "Update system.md to add [rule]. Show me the diff first."

**Ending a session:**
> "Update MEMORY.md with what we did and where to pick up. Then stop."

**Agent is doing too much scanning:**
> "Check MEMORY.md first — the answer may already be there."

**Agent is about to hit a manual review gate:**
> The agent should stop itself (it's in CLAUDE.md). If it doesn't, tell it:
> "This is a manual review gate. Stop, show me what you have, and wait for my approval."