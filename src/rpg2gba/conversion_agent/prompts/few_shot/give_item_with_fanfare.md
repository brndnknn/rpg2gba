## Example: NPC gives an item (idiom recognition)

A multi-command RPG Maker sequence (show text → process item add → fanfare →
self-switch) collapses to the `giveitem` idiom plus a one-time guard.

**Input event JSON:**

```json
{
  "id": 4, "name": "EV004", "x": 9, "y": 5,
  "pages": [
    {
      "condition": {"self_switch_valid": false, "self_switch_ch": "A"},
      "list": [
        {"code": 101, "indent": 0, "parameters": ["Here, take this Potion!"]},
        {"code": 355, "indent": 0, "parameters": ["pbReceiveItem(:POTION,1)"]},
        {"code": 123, "indent": 0, "parameters": ["A", 0]},
        {"code": 0, "indent": 0, "parameters": []}
      ]
    }
  ]
}
```

**Expected output:**

```json
{
  "script": "script Map012_EV004_Page1 {\n    lock\n    faceplayer\n    msgbox(\"Here, take this Potion!\")\n    giveitem(ITEM_POTION, 1)\n    setflag(FLAG_MAP012_EVENT004_SSA)\n    release\n    end\n}\n",
  "new_flags": [],
  "new_vars": [],
  "unhandled": []
}
```

Notes: the self-switch A on event 4 becomes `FLAG_MAP012_EVENT004_SSA` (deterministic
pattern — no registry proposal needed); the terminating `code 0` is dropped.
