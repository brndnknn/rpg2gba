"""Generate the converted game's own items into the engine.

The items a game has that the engine lacks (`uranium_id_map.json` ->
`needs_engine.items`) are emitted as gitignored headers that fenced
`RPG2GBA GAME PROFILE` hooks include: enum members, `gItemsInfo` rows, berry
tables, composed item effects, icons and berry pics. How each item behaves is
decided by `reference/item_rulings.json`; berries continue the stock berry run
and everything else follows the last stock item
(reference/engine_layers_i3_i5.md §8 S2).
"""
