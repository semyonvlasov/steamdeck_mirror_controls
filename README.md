# SteamDeck Mirror Controls (Decky Plugin)

Decky plugin to create a mirrored Steam Input layout from the current game's active layout and save it to game layouts.

## Features

- Mirror `D-pad <-> ABXY` bindings:
  - `D-pad Up <-> Y`
  - `D-pad Down <-> A`
  - `D-pad Left <-> X`
  - `D-pad Right <-> B`
- Mirror touchpad behavior (`left <-> right` touchpad tokens).
- Mirror stick behavior (`left_stick <-> right_stick` token pairs and common variants).
- Auto-detect current game app id from Steam UI.
- Uses the current game's layout files (`app_<appid>.vdf` and app-specific layout directories) as source.

## Backend behavior

`main.py` scans Steam userdata folders:

- `~/.local/share/Steam/userdata`
- `~/.steam/steam/userdata`
- `~/.steam/root/userdata`

Then it finds game layout sources under:

`<userdata>/<steam_user_id>/config/controller_configs/app_<app_id>.vdf`

and app-specific layout folders such as:

`<userdata>/<steam_user_id>/config/controller_configs/<app_id>/**/*.vdf`

It also scans Steam Controller Configs current layouts, for example:

`~/.local/share/Steam/steamapps/common/Steam Controller Configs/<steam_user_id>/config/**/controller_neptune.vdf`

The plugin writes mirrored layouts to Steam Controller Configs game layout directories:

`~/.local/share/Steam/steamapps/common/Steam Controller Configs/<steam_user_id>/config/<app_id>/<source>_app_<app_id>_mirror_YYYYmmdd_HHMMSS.vdf`

It also appends `(Mirror <timestamp>)` to template title.

## UI options

- `Mirror D-pad + ABXY`
- `Mirror Touchpads`
- `Mirror Left/Right Sticks`
- `Mirror Menu Position` (mirrors `touch_menu_position_x`, default on)
- `Mirror Gyro Buttons` (mirrors left/right activation tokens on gyro lines, default on)
- `Create Mirror Template` button

## Notes

- Token-level mirroring is string-based to stay resilient to different VDF structures.
- Backend saves output to game layout folders.
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

## Install Via Decky Manual Install URL

Use this URL in Decky `Developer -> Manual Plugin Install`:

`https://github.com/semyonvlasov/steamdeck_mirror_controls/releases/latest/download/steamdeck_mirror_controls.zip`

How to publish a new zip:

1. Commit and push changes to `main`.
2. Create and push a tag (example):
   - `git tag v0.1.0`
   - `git push origin v0.1.0`
3. GitHub Actions workflow `Build And Release Plugin Zip` will:
   - build frontend
   - create `steamdeck_mirror_controls.zip`
   - attach zip to the GitHub Release for the tag

Notes:

- Workflow artifacts are temporary and not ideal for Decky install links.
- Release assets are public and stable for manual install.

## Troubleshooting

If Manual Install closes with no error and plugin does not appear:

1. Restart Steam (or reboot Deck) and check again.
2. Ensure archive contains required files inside plugin directory:
   - `package.json`
   - `plugin.json`
   - `main.py`
   - `dist/index.js`
3. Check Decky logs in Desktop Mode:
   - `/home/deck/homebrew/logs/decky_loader.log`
   - `/home/deck/homebrew/logs/plugin_loader.log`

### Example copy from your dev machine

```bash
rsync -av --delete \
  --exclude node_modules \
  --exclude .git \
  /path/to/steamdeck_mirror_controls/ \
  deck@steamdeck:/home/deck/homebrew/plugins/steamdeck_mirror_controls/
```
