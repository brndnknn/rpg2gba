# Asset Inventory

| Directory | Files | Types | Description |
|---|---|---|---|
| `Graphics/Battlers` | 1646 | `.png` ×1644, `.act` ×2 | Battle sprites (front/back) |
| `Graphics/Characters` | 718 | `.png` ×718 | Overworld / character sprites |
| `Graphics/Tilesets` | 61 | `.png` ×61 | Tileset graphics |
| `Graphics/Autotiles` | 112 | `.png` ×111, `.pdn` ×1 | Autotile graphics |
| `Graphics/Icons` | 1441 | `.png` ×1441 | Pokémon box icons |
| `Graphics/Pictures` | 855 | `.png` ×845, `.pdn` ×4, `.gif` ×3, `.net` ×1, `.js` ×1, `.bmp` ×1 | UI / cutscene images |
| `Graphics/Animations` | 181 | `.png` ×181 | Battle animations |
| `Graphics/Windowskins` | 79 | `.png` ×65, `.txt` ×14 | UI window skins |
| `Audio/BGM` | 84 | `.ogg` ×79, `.mid` ×3, `.sfk` ×1, `.wav` ×1 | Background music |
| `Audio/SE` | 593 | `.wav` ×271, `.ogg` ×264, `.mp3` ×55, `.reapeaks` ×1, `.ini` ×1, `.mid` ×1 | Sound effects |
| `Audio/ME` | 24 | `.ogg` ×23, `.sfk` ×1 | Music effects (fanfares, jingles) |
| `Audio/BGS` | 12 | `.ogg` ×12 | Background sounds (ambience) |

## Conversion notes

- **Sprites:** GBA is 4bpp indexed, 16 colors per palette. All Uranium PNGs (full-color) will
  visibly degrade. Budget manual cleanup for high-visibility sprites: player, starters, gym leaders.
- **Tilesets:** RPG Maker uses 32×32 logical tiles with full-color art. GBA uses 8×8 tiles.
  Phase 5 uses Approach A: substitute closest pokeemerald-expansion tiles rather than reconvert.
- **Audio:** Not converted. GBA uses sappy/m4a sequences. Plan to substitute existing
  pokeemerald music. Leave as Phase 8 polish.
