# Strengthening the party on a walk ROM (debug menu)

The intermission's I1 stopgap (`reference/intermission_a1_a2.md` §I1): every
`make modern` ROM includes pokeemerald-expansion's debug menu. It is on because
`DEBUG_OVERWORLD_MENU` is `DISABLED_ON_RELEASE` (`engine/include/config/debug.h:4`),
and only `make release` sets `RELEASE`. Verified on a real ROM run 2026-10-16
(`output/scratch/debug_menu_probe.py`): a level-31 Orchynx and 5 Rare Candies
were given in Moki Town.

## Opening it

In the overworld, with the player free to move: **hold R, press START.**

Numbers are entered digit by digit:
- **Up/Down** change the selected digit.
- **Left/Right** move between digits. The cursor starts on the ones digit.
- **A** confirms; **B** backs out.

The current name shows live, so a wrong id is obvious.

## Common recipes

| Want | Path | Value |
|---|---|---|
| Add a Pokémon at a chosen level | Give X… → Pokémon (Basic) → species id → level | Ids below |
| Level up what you have | Give X… → Give item XYZ… → id **102** (Rare Candy) → quantity, then use it from the bag | Exp. Candy XS–XL are 103–107 |
| Heal | Party… → Heal party | — |
| Money | Give X… → Max Money | — |
| Moves, IVs, nature | Give X… → Pokémon (Complex) | — |

There is no "set level" or "set EXP" entry; use Rare Candies, or give a fresh
Pokémon at the level you want.

## Uranium species ids (snapshot 2026-10-16)

The ids are append-only, so these stay valid. A species added later gets the
next id. Regenerate with `python output/scratch/species_ids.py`, or read
`engine/include/constants/rpg2gba_species_constants.h` (ids start at
`SPECIES_GLIMMORA_MEGA + 1` = 1573). Stock species keep their national-dex ids.

| Id | Species | Id | Species |
|---|---|---|---|
| 1573 | Orchynx | 1591 | Tofurang |
| 1574 | Metalynx | 1592 | Fartog |
| 1575 | Raptorch | 1593 | Folerog |
| 1576 | Archilles | 1594 | Blubelrog |
| 1577 | Eletux | 1595 | Owten |
| 1578 | Electruxo | 1596 | Eshouten |
| 1579 | Chyinmunk | 1597 | Luxi |
| 1580 | Kinetmunk | 1598 | Luxor |
| 1581 | Birbie | 1599 | Luxelong |
| 1582 | Aveden | 1600 | Grozard |
| 1583 | Splendifowl | 1601 | Terlard |
| 1584 | Cubbug | 1602 | Baashaun |
| 1585 | Cubblfly | 1603 | Baaschaf |
| 1586 | Nimflora | 1604 | Baariette |
| 1587 | Barewl | 1605 | Feleng |
| 1588 | Dearewl | 1606 | Felunge |
| 1589 | Gararewl | 1607 | Feliger |
| 1590 | Tonemy |  |  |

## Limits

- **Walk ROMs reset on every boot** (I6): the embedded save loads before the
  `.sav`, so a party built this way lasts until you power off.
- A species whose data is missing shows "Species Disabled" and can't be given.
