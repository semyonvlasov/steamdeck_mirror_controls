# SteamDeck Mirror Controls (Decky Plugin)

Decky plugin to create a mirrored Steam Input template for the current game and save it as a new template.

## Features

- Mirror `D-pad <-> ABXY` bindings:
  - `D-pad Up <-> Y`
  - `D-pad Down <-> A`
  - `D-pad Left <-> X`
  - `D-pad Right <-> B`
- Mirror touchpad behavior (`left <-> right` touchpad tokens).
- Mirror stick behavior (`left_stick <-> right_stick` token pairs and common variants).
- Auto-detect current game app id from Steam UI when possible.
- Fallback: backend auto-selects the latest non-mirror template found in Steam userdata.

## Backend behavior

`main.py` scans Steam userdata folders:

- `~/.local/share/Steam/userdata`
- `~/.steam/steam/userdata`
- `~/.steam/root/userdata`

Then it finds templates under:

`<userdata>/<steam_user_id>/config/controller_configs/<app_id>/**/*.vdf`

The plugin creates a new file near the source template:

`<source_name>_mirror_YYYYmmdd_HHMMSS.vdf`

It also appends `(Mirror <timestamp>)` to template title.

## UI options

- `Mirror D-pad + ABXY`
- `Mirror Touchpads`
- `Mirror Left/Right Sticks`
- `Create Mirror Template` button

## Notes

- Token-level mirroring is string-based to stay resilient to different VDF structures.
- If both options are disabled, the plugin returns an error.

## Install On Steam Deck

1. Build frontend bundle:
   - `pnpm i`
   - `pnpm run build`
2. Ensure resulting file exists: `dist/index.js`
3. Copy plugin folder to Decky plugins path:
   - `/home/deck/homebrew/plugins/steamdeck_mirror_controls`
4. Make sure these files are present in plugin folder:
   - `main.py`
   - `plugin.json`
   - `dist/index.js`
5. Reload Decky plugins (or restart Steam Deck).

### Example copy from your dev machine

```bash
rsync -av --delete \
  --exclude node_modules \
  --exclude .git \
  /path/to/steamdeck_mirror_controls/ \
  deck@steamdeck:/home/deck/homebrew/plugins/steamdeck_mirror_controls/
```
