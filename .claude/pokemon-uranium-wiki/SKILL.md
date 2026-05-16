---
name: pokemon-uranium-wiki
description: >
  Reference guide for using the Pokémon Uranium Fandom wiki as a validation
  resource. Use this skill when working on the Pokémon Uranium RPG Maker XP
  game converter, cross-referencing map/event/encounter data against the wiki,
  checking story progression logic, verifying location names or connections,
  or answering any question about the game's content, mechanics, or structure.
  Trigger whenever the user mentions Uranium maps, .rxdata parsing, event
  flags, wild encounter tables, Nuclear-type Pokémon data, or wants to validate
  converter output against the actual game.
---

# Pokémon Uranium Wiki Reference

The canonical wiki is at **https://pokemon-uranium.fandom.com/wiki/Main_Page**

Wiki pages follow a consistent URL pattern:
`https://pokemon-uranium.fandom.com/wiki/<Page_Name>` (spaces become underscores)

---

## Key Pages by Category

### Game Structure / Validation Starting Points

| Purpose | URL |
|---|---|
| Full story walkthrough (ordered map progression) | `/wiki/Game_Walkthrough` |
| Tandor region overview + game summary | `/wiki/Pokémon_Uranium` |
| All sidequests with triggers/rewards | `/wiki/Sidequests` |
| Legendary Pokémon | `/wiki/Legendary_Pokémon` |
| Mega Evolution | `/wiki/Mega_Evolution` |

### Locations — Towns & Cities

| Location | URL |
|---|---|
| Moki Town (start) | `/wiki/Moki_Town` |
| Kevlar Town | `/wiki/Kevlar_Town` |
| Nowtoch City (Gym 1) | `/wiki/Nowtoch_City` |
| Bealbeach City (Gym 2) | `/wiki/Bealbeach_City` |
| Vinoville Town (Gym 3) | `/wiki/Vinoville_Town` |
| Rochfale Town (Gym 4) | `/wiki/Rochfale_Town` |
| Legen Town | `/wiki/Legen_Town` |
| Venesi City (Gym 5) | `/wiki/Venesi_City` |
| Tsukinami Village (Gym 6) | `/wiki/Tsukinami_Village` |
| Seaspray Town | `/wiki/Seaspray_Town` |
| Snowbank Town (Gym 7) | `/wiki/Snowbank_Town` |
| Silverport Town (Gym 8) | `/wiki/Silverport_Town` |
| Amatree Town | `/wiki/Amatree_Town` |
| Ara City | `/wiki/Ara_City` |

### Locations — Routes

Routes are numbered 1–17. URL pattern: `/wiki/Route_<N>`

| Route | Connects |
|---|---|
| Route 1 | Moki Town → Kevlar Town |
| Route 2 | Kevlar Town → Nowtoch City |
| Route 3 | Nowtoch City → Bealbeach City area |
| Route 4 | Bealbeach area |
| Route 5 | → Comet Cave / Rochfale area |
| Route 6 | Rochfale → cave area |
| Route 7 | → Nuclear Plant Epsilon (boat access) |
| Route 11 | Legen Town → Nuclear event area |
| Route 12–17 | Eastern Tandor progression |

Full route category: `/wiki/Category:Routes`

### Locations — Dungeons & Special Areas

| Location | URL |
|---|---|
| Passage Cave | `/wiki/Passage_Cave` |
| Comet Cave | `/wiki/Comet_Cave` |
| The Labyrinth | `/wiki/The_Labyrinth` |
| Nuclear Plant Epsilon (story) | `/wiki/Nuclear_Plant_Epsilon` |
| Nuclear Plant Zeta | `/wiki/Nuclear_Plant_Zeta` |
| Nuclear Plant Theta | `/wiki/Nuclear_Plant_Theta` |
| Victory Road | `/wiki/Victory_Road` |
| Championship Site | `/wiki/Championship_Site` |
| Dream World | `/wiki/Dream_World` |

### Mechanics

| Topic | URL |
|---|---|
| Nuclear type (full type chart, mechanics) | `/wiki/Nuclear_(type)` |
| Gym Leaders (all 8) | `/wiki/Gym_Leader` |
| HMs and field moves | `/wiki/HM` |
| Poké Radar | `/wiki/Poké_Radar` |
| Pokédex (all species) | `/wiki/Pokédex` |
| Mystery Gift | `/wiki/Mystery_Gift` |

### Key Pokémon

| Pokémon | URL |
|---|---|
| Urayne (legendary, final boss) | `/wiki/Urayne` |
| Actan (legendary) | `/wiki/Actan` |
| Nucleon (Eevee evolution) | `/wiki/Nucleon` |
| Geigeroach | `/wiki/Geigeroach` |
| Hazma | `/wiki/Hazma` |

Full Pokédex category: `/wiki/Category:Pokémon`

---

## Converter Validation Tips

When cross-referencing `.rxdata` output against the wiki:

**Map names / IDs**: Each location page lists connections to adjacent maps.
The walkthrough page is the most reliable source for the *expected order* of
map visits and which events unlock which transitions.

**Wild encounter tables**: Each route/dungeon page has a Pokémon section with
species, levels, and encounter method (grass/surf/fishing/radar). Nuclear forms
are listed separately where applicable and are often only available on a single
visit.

**Event flags / story triggers**: The walkthrough page and individual location
pages describe prerequisite conditions (e.g., "only accessible by boat from
Route 7 on a single visit before the Bealbeach City gym"). These are good
sanity checks for event sequencing logic.

**Nuclear type mechanics**: Nuclear Pokémon encountered in the wild use a
different disobedience rule from caught feral ones vs. naturally Nuclear
species. See `/wiki/Nuclear_(type)` for the full breakdown — important if
you're converting encounter or battle event data.

**HM gating**: Many area transitions are gated by HMs obtained from specific
story events. The walkthrough tracks when each HM is acquired and which paths
it unlocks.

---

## Usage Pattern

When validating converter output:

1. `web_fetch` the relevant wiki page (route, town, or dungeon)
2. Compare the wiki's listed Pokémon, items, trainers, and connections against
   what the converter produced
3. For story/event logic, cross-reference with the Game Walkthrough page for
   ordering and trigger conditions
4. For type/mechanic data, use the Nuclear type page or individual Pokémon pages

The wiki may be fetched with `web_fetch` — if a page 403s, try `web_search`
with `site:pokemon-uranium.fandom.com <location name>` to find the right URL
and pull a cached snippet.
