# Playing Pokémon Uranium on Ubuntu via Wine

Checked against the dev machine: Ubuntu 24.04 LTS, no Wine installed, no `i386` architecture enabled. Instructions below assume that starting point. Light/occasional use — the distro's Wine package (currently `9.0` in Ubuntu 24.04's `universe` repo) is plenty for this; no need for the WineHQ third-party repo.

Pokémon Uranium is built on **RPG Maker XP** (RGSS102E.dll), a 32-bit Windows engine. It's one of the best-supported categories of game on Wine.

---

## 1. Enable 32-bit support

RPG Maker XP games are 32-bit. Ubuntu needs the `i386` architecture enabled before `wine32` becomes installable.

```bash
sudo dpkg --add-architecture i386
sudo apt update
```

## 2. Install Wine and winetricks

```bash
sudo apt install wine winetricks
```

Verify:

```bash
wine --version
```

## 3. Create a dedicated Wine prefix

Don't dump Uranium into your default `~/.wine` — give it its own 32-bit prefix so it's isolated and easy to nuke/rebuild if something goes wrong.

```bash
WINEARCH=win32 WINEPREFIX=~/.wine-uranium winecfg
```

This pops up the Wine configuration GUI and initializes the prefix at `~/.wine-uranium`. Click through it (default Windows version, e.g. "Windows 7" or "Windows XP", is fine) and close it — that's enough to create the prefix.

From here on, always pass `WINEPREFIX=~/.wine-uranium` when running `wine` or `winetricks` commands for this game, so you don't touch your default prefix.

## 4. (Optional) Install common runtime components

Most RPG Maker XP games — Uranium included — work out of the box because the game ships its own `RGSS102E.dll` in the install folder. Only bother with this if you actually hit a font-rendering glitch or missing-DLL popup:

```bash
WINEPREFIX=~/.wine-uranium winetricks -q corefonts
WINEPREFIX=~/.wine-uranium winetricks -q vcrun2005 vcrun6
```

## 5. Get the game files

The Uranium source referenced by `RPG2GBA_URANIUM_SRC` in this project is the game's install directory (it should contain `Game.exe`, `Data/`, `Graphics/`, `Audio/`, etc.). Copy it somewhere convenient for actually playing, rather than running it out of the pipeline's working tree:

```bash
mkdir -p ~/Games
cp -r "$RPG2GBA_URANIUM_SRC" ~/Games/PokemonUranium
```

Keeping the play copy separate avoids ever mixing pipeline-touched files with the game you're running.

## 6. Run it

```bash
cd ~/Games/PokemonUranium
WINEPREFIX=~/.wine-uranium wine Game.exe
```

If that launches into the title screen, you're done — the rest below is only for when something doesn't work.

## 7. Fullscreen / display tuning (optional)

RPG Maker XP renders at a small native resolution (usually 640×480) and upscales, which can look soft or run in a tiny window depending on the game's own settings. Two independent knobs:

- **In-game**: Uranium's options menu / F5 (title-screen fullscreen toggle, standard for RPG Maker XP) may control window vs. fullscreen.
- **Wine-side**: `WINEPREFIX=~/.wine-uranium winecfg` → **Graphics** tab has options like "Emulate a virtual desktop" if the game misbehaves going fullscreen on a modern multi-monitor setup. Leave these off unless you hit a specific problem — they're a fallback, not a default.

## 8. Make a launcher (optional convenience)

```bash
cat > ~/.local/share/applications/pokemon-uranium.desktop <<'EOF'
[Desktop Entry]
Type=Application
Name=Pokémon Uranium
Exec=env WINEPREFIX=/home/YOURUSER/.wine-uranium wine /home/YOURUSER/Games/PokemonUranium/Game.exe
Path=/home/YOURUSER/Games/PokemonUranium
Icon=wine
Terminal=false
Categories=Game;
EOF
```

Replace `YOURUSER` with your actual username (`echo $USER` if unsure), then it'll show up in your app launcher.

---

## Troubleshooting

**"RGSS102E.dll could not be found"**
The dll should already be sitting next to `Game.exe` in the game folder — if it's missing, your copy of the game files is incomplete rather than a Wine problem. Re-check `$RPG2GBA_URANIUM_SRC`.

**Game launches but window is black / crashes immediately**
Try forcing a specific Windows version in the prefix:
```bash
WINEPREFIX=~/.wine-uranium winecfg
```
→ **Applications** tab → set version to Windows XP, and re-test.

**Choppy audio / crackling**
Wine's audio driver defaults are usually fine on modern Ubuntu (PipeWire), but if it's bad:
```bash
WINEPREFIX=~/.wine-uranium winetricks sound=disabled
```
to confirm audio is the culprit, then re-enable and adjust via `winecfg` → **Audio** tab.

**Keyboard/controller input feels laggy or wrong**
RPG Maker XP games read raw keyboard by default; an Xbox/generic USB controller usually needs a tool like `antimicrox` mapped to arrow keys + Z/X (the RPG Maker XP default confirm/cancel bindings) if Uranium doesn't have native controller support — check its in-game options menu first, since some fan games add this.

**Something else breaks**
RPG Maker XP + Wine is a very well-trodden combination — search the specific error text plus "wine" before assuming it's Uranium-specific; it's very likely a generic RGSS/Wine interaction with an existing fix on ArchWiki, WineHQ AppDB, or the RPG Maker community.
