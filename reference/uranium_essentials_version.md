# Pokémon Uranium Essentials Version

## Version: Essentials v17

Pokémon Uranium is built on **Pokémon Essentials v17**, as evidenced by the large number of v17-tagged script files in `Scripts.rxdata`:

- Core game object classes: `Game_Screen_v17`, `Game_System_v17`, `Game_Player_v17`, `Game_Map_v17`, etc.
- UI and graphics: `Sprite_Picture_v17`, `Window_v17`, `SpriteWindow_sprites_v17`
- Audio and utilities: `AudioPlay_v17`, `AudioUtilities_v17`, `EventHandlers_v17`
- Field and terrain: `PBTerrain_v17`, `PField_Time_v17`

A total of 29 sections in the 260-section script dump have v17 markers, covering all core subsystems.

## PBS Format Implications

Essentials v17 uses the same PBS plain-text format as Essentials v18 and v19 for data definitions (pokemon.txt, moves.txt, items.txt, etc.). However, **Uranium does not distribute PBS source files**. Instead, Uranium compiles the PBS at first run to binary `.dat` files stored in `Data/`.

**This changes Phase 2 of the roadmap:** The deterministic PBS converters will need to read from `.dat` files via Ruby deserialization instead of parsing plain-text PBS. The `.dat` format is Marshal-serialized Ruby objects, so the existing `Scripts.rxdata` deserializer pattern can be extended.

## Notable Divergences from Vanilla Essentials v17

1. **Custom online/network features** (Scripts 233–236): URANIUM_ONLINE, POLL, and related online systems added post-v17
2. **BW-style UI overhauls** (Scripts 196–205): Modern Black/White/Black 2 interface layers (likely a community backport to v17)
3. **EliteBattle scene** (Scripts 238–245): Advanced battle animations beyond vanilla v17
4. **Nuclear type system** (Scripts 217, 224, 225): Custom type implementation with specialized mechanics
5. **Title screen customization** (Script 219): Uranium-specific branding and features
6. **Uranium pause menu** (Script 215): Custom menu system
7. **Achievements system** (Script 209): Game progression tracking beyond vanilla v17
8. **Tandor Championship** (Script 227): Post-game tournament system

All of these are *additive* to v17 — they don't change the PBS format itself, just layer new mechanics on top.
