## Example: Pokémon Center nurse — heal with a yes/no choice (strip cosmetic calls)

The nurse-heal pattern. Several Script calls are STRIP-tagged cosmetic/bookkeeping
(`Kernel.pbSetPokemonCenter` → respawn is wired from metadata, not events;
`pbCallBub` → speech-bubble emote) and emit **nothing** — they are *not* queued as
unhandled. A Show Choices YES/NO (codes 102/402/404) becomes a `MSGBOX_YESNO`
prompt branched on `VAR_RESULT`; "Recover All" (314) becomes `healparty`. Movement,
wait, and SE-play (209/509/210/106/249/250) and the party-length bookkeeping var are
animation plumbing with no game-state effect — strip them.

**Input event JSON (abridged to the representative commands):**

```json
{
  "map_id": 2,
  "id": 1, "name": "EV001", "x": 4, "y": 5,
  "pages": [
    {
      "condition": {"self_switch_valid": false, "self_switch_ch": "A"},
      "list": [
        {"code": 355, "indent": 0, "parameters": ["Kernel.pbSetPokemonCenter"]},
        {"code": 355, "indent": 0, "parameters": ["pbCallBub(2,0,3)"]},
        {"code": 101, "indent": 0, "parameters": ["Hello, and welcome to the Pokémon Center."]},
        {"code": 101, "indent": 0, "parameters": ["We restore your tired Pokémon to full health."]},
        {"code": 101, "indent": 0, "parameters": ["Would you like to rest your Pokémon?"]},
        {"code": 102, "indent": 0, "parameters": [["YES", "NO"], 2]},
        {"code": 402, "indent": 0, "parameters": [0, "YES"]},
        {"code": 355, "indent": 1, "parameters": ["pbCallBub(2)"]},
        {"code": 101, "indent": 1, "parameters": ["OK, I'll take your Pokémon for a few seconds."]},
        {"code": 314, "indent": 1, "parameters": [0]},
        {"code": 249, "indent": 1, "parameters": [{"__class__": "RPG::AudioFile", "name": "Pokemon Healing"}]},
        {"code": 355, "indent": 1, "parameters": ["$game_variables[43]=$Trainer.party.length"]},
        {"code": 101, "indent": 1, "parameters": ["Thank you for waiting."]},
        {"code": 101, "indent": 1, "parameters": ["We've restored your Pokémon to full health."]},
        {"code": 101, "indent": 1, "parameters": ["We hope to see you again!"]},
        {"code": 0, "indent": 1, "parameters": []},
        {"code": 402, "indent": 0, "parameters": [1, "NO"]},
        {"code": 355, "indent": 1, "parameters": ["pbCallBub(2)"]},
        {"code": 101, "indent": 1, "parameters": ["We hope to see you again!"]},
        {"code": 0, "indent": 1, "parameters": []},
        {"code": 404, "indent": 0, "parameters": []},
        {"code": 0, "indent": 0, "parameters": []}
      ]
    }
  ]
}
```

**Expected output:**

```json
{
  "script": "script Map002_EV001_Page1 {\n    lock\n    faceplayer\n    msgbox(\"Hello, and welcome to the Pokémon Center.\\pWe restore your tired Pokémon to full health.\")\n    msgbox(\"Would you like to rest your Pokémon?\", MSGBOX_YESNO)\n    if (var(VAR_RESULT) == 1) {\n        msgbox(\"OK, I'll take your Pokémon for a few seconds.\")\n        healparty\n        msgbox(\"Thank you for waiting.\\pWe've restored your Pokémon to full health.\\pWe hope to see you again!\")\n    } else {\n        msgbox(\"We hope to see you again!\")\n    }\n    release\n    end\n}\n",
  "new_flags": [],
  "new_vars": [],
  "unhandled": []
}
```

Notes: `Kernel.pbSetPokemonCenter` and every `pbCallBub` are STRIP — gone, not
queued. The `$game_variables[43]=$Trainer.party.length` write is animation
bookkeeping (how many balls the nurse animation shows) with no GBA analogue — strip
it; it is *not* a `setvar`. `VAR_RESULT` is a built-in pokeemerald constant (the
yes/no result), so it needs no registry proposal.
