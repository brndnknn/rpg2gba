## Example: conditional branch on a story switch (new flag proposal)

A conditional branch (code 111) on a switch that is *not yet in the registry*.
The agent proposes a context-derived name; the orchestrator commits it.

**Input event JSON:**

```json
{
  "id": 1, "name": "EV001", "x": 3, "y": 7,
  "pages": [
    {
      "condition": {"switch1_valid": false, "switch1_id": 60},
      "list": [
        {"code": 111, "indent": 0, "parameters": [0, 60, 0]},
        {"code": 101, "indent": 1, "parameters": ["You saved the lighthouse! Thank you."]},
        {"code": 412, "indent": 0, "parameters": []},
        {"code": 101, "indent": 0, "parameters": ["Please, help us with the lighthouse."]},
        {"code": 0, "indent": 0, "parameters": []}
      ]
    }
  ]
}
```

**Expected output:**

```json
{
  "script": "script Map020_EV001_Page1 {\n    lock\n    faceplayer\n    if (flag(FLAG_LIGHTHOUSE_RESTORED)) {\n        msgbox(\"You saved the lighthouse! Thank you.\")\n    } else {\n        msgbox(\"Please, help us with the lighthouse.\")\n    }\n    release\n    end\n}\n",
  "new_flags": [
    {"switch_id": 60, "name": "FLAG_LIGHTHOUSE_RESTORED", "reason": "Branch gates on switch 60; dialogue thanks the player for saving the lighthouse"}
  ],
  "new_vars": [],
  "unhandled": []
}
```

Notes: `111` + `412` (branch end) become an `if/else`; the name is derived from the
dialogue's meaning, not the switch number.
