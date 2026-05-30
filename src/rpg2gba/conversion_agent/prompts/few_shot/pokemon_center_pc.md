## Example: a single UNHANDLED script call (the PC)

Some events are nothing but one Uranium call with no safe GBA equivalent. The PC
storage call `pbPokeCenterPC` is tagged **UNHANDLED** in the script-call reference
(opening pokeemerald's PC is a Phase 5/6 wiring concern, not a field command we can
emit yet). There is nothing translatable here, so emit a compiling stub that marks
the gap and queue the call — do **not** guess a `special` or macro.

**Input event JSON:**

```json
{
  "map_id": 2,
  "id": 3, "name": "EV003", "x": 7, "y": 3,
  "pages": [
    {
      "condition": {"self_switch_valid": false, "self_switch_ch": "A"},
      "list": [
        {"code": 355, "indent": 0, "parameters": ["pbPokeCenterPC"]},
        {"code": 0, "indent": 0, "parameters": []}
      ]
    }
  ]
}
```

**Expected output:**

```json
{
  "script": "script Map002_EV003_Page1 {\n    lock\n    faceplayer\n    # UNHANDLED: command 355 pbPokeCenterPC — see unhandled[]\n    release\n    end\n}\n",
  "new_flags": [],
  "new_vars": [],
  "unhandled": [
    {"command_code": 355, "description": "pbPokeCenterPC opens the PC storage UI; pokeemerald wires the PC via a dedicated tile-script/special, not a field command — needs Phase 5/6 wiring", "event_id": 3, "page": 1, "line": 1}
  ]
}
```

Notes: the stub still compiles (so the map builds) and leaves a visible `# UNHANDLED`
breadcrumb; the call is recorded in `unhandled[]` for the triage queue. Queueing is
correct here precisely because the reference tags `pbPokeCenterPC` UNHANDLED — unlike
the STRIP-tagged `pbCallBub`, which is dropped silently.
