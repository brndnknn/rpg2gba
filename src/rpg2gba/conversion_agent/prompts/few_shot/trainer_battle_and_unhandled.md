## Example: trainer battle + an untranslatable custom call (unhandled)

A trainer battle (translatable) alongside a Uranium-specific script call with no
GBA analogue — which must be flagged in `unhandled`, not guessed at.

**Input event JSON:**

```json
{
  "id": 7, "name": "EV007", "x": 14, "y": 2,
  "pages": [
    {
      "condition": {},
      "list": [
        {"code": 355, "indent": 0, "parameters": ["NuclearMeter.show"]},
        {"code": 355, "indent": 0, "parameters": ["pbTrainerBattle(:YOUNGSTER, \"Ben\", \"You win.\")"]},
        {"code": 101, "indent": 0, "parameters": ["Wow, you're strong!"]},
        {"code": 0, "indent": 0, "parameters": []}
      ]
    }
  ]
}
```

**Expected output:**

```json
{
  "script": "script Map033_EV007_Page1 {\n    lock\n    faceplayer\n    # UNHANDLED: command 355 NuclearMeter.show — see unhandled[]\n    trainerbattle_single(TRAINER_YOUNGSTER_BEN, \"\", \"You win.\")\n    msgbox(\"Wow, you're strong!\")\n    release\n    end\n}\n",
  "new_flags": [],
  "new_vars": [],
  "unhandled": [
    {"command_code": 355, "description": "Uranium custom UI call NuclearMeter.show — no GBA equivalent", "event_id": 7, "page": 1, "line": 1}
  ]
}
```

Notes: the translatable parts are still emitted; the untranslatable call is marked
in-place with a `# UNHANDLED` comment AND recorded in `unhandled[]`. The trainer
constant comes from the Phase 2 trainer data, not invented.
