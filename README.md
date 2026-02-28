# Steam Deck Control Template Mirror Tool

A Python utility to mirror (copy/sync/backup) Steam Deck control templates between configurations, devices, or for creating reversed (left/right hand swapped) controller layouts.

## Features

- 🎮 **Mirror control templates** - Copy Steam Deck controller configurations
- 🔄 **Reverse mappings** - Create left/right swapped versions for ambidextrous play
- 📁 **Batch operations** - Mirror entire directories of templates at once
- 🔍 **Auto-discovery** - Automatically finds Steam userdata directories
- 💾 **Backup support** - Easy backup and restore of your controller configs

## Installation

### Requirements
- Python 3.6 or higher
- Steam Deck or Linux system with Steam installed

### Setup
```bash
# Clone the repository
git clone https://github.com/semyonvlasov/steamdeck_mirror_controls.git
cd steamdeck_mirror_controls

# Make the script executable (optional)
chmod +x mirror_controls.py
```

## Usage

### List Available Templates

To see all controller templates on your system:
```bash
python mirror_controls.py --list
```

### Mirror a Single Template

Copy a single template file to a backup location:
```bash
python mirror_controls.py --source ./my_template.vdf --dest ./backup/
```

### Mirror All Templates from a Directory

Backup all templates from a directory:
```bash
python mirror_controls.py --source ~/.steam/steam/userdata/12345/config/controller_config/ --dest ./backup/
```

### Create Reversed (Mirrored) Versions

Create left/right swapped versions of your templates (useful for left-handed gaming):
```bash
python mirror_controls.py --source ./template.json --dest ./output/ --reverse
```

## Steam Deck Control Template Locations

Steam Deck controller templates are typically stored in:
- `~/.steam/steam/userdata/<USER_ID>/config/controller_config/`
- `~/.local/share/Steam/userdata/<USER_ID>/config/controller_config/`
- `/home/deck/.steam/steam/userdata/<USER_ID>/config/controller_config/`

Where `<USER_ID>` is your Steam user ID (a numeric folder).

## Template File Formats

The tool supports:
- **VDF files** (`.vdf`) - Valve Data Format, Steam's native format
- **JSON files** (`.json`) - JSON-formatted controller configurations

## Use Cases

### 1. Backup Your Configurations
```bash
# Back up all your controller configs
python mirror_controls.py --source ~/.steam/steam/userdata/12345/config/controller_config/ --dest ~/steam_config_backup/
```

### 2. Sync Between Devices
```bash
# Copy from one Steam Deck to another (via USB or network share)
python mirror_controls.py --source /media/usb/controller_config/ --dest ~/.steam/steam/userdata/12345/config/controller_config/
```

### 3. Create Left-Handed Layouts
```bash
# Create mirrored versions for left-handed play
python mirror_controls.py --source ./my_config.json --dest ./left_handed/ --reverse
```

### 4. Share Configurations
```bash
# Export specific templates to share with friends
python mirror_controls.py --source ~/.steam/steam/userdata/12345/config/controller_config/game_xyz.vdf --dest ./shared_configs/
```

## Command-Line Options

```
usage: mirror_controls.py [-h] [--list] [--source SOURCE] [--dest DEST] [--reverse]

Mirror Steam Deck control templates

optional arguments:
  -h, --help       show this help message and exit
  --list           List all available controller templates
  --source SOURCE  Source template file or directory
  --dest DEST      Destination directory
  --reverse        Create reversed (left/right swapped) versions of templates
```

## Examples

### Example 1: Quick Backup
```bash
python mirror_controls.py \
  --source ~/.steam/steam/userdata/12345/config/controller_config/ \
  --dest ~/Documents/steam_backup_$(date +%Y%m%d)/
```

### Example 2: Mirror Specific Game Config
```bash
python mirror_controls.py \
  --source ~/.steam/steam/userdata/12345/config/controller_config/game_480.vdf \
  --dest ~/my_configs/
```

### Example 3: Create Reversed Layout
```bash
python mirror_controls.py \
  --source ./competitive_layout.json \
  --dest ./layouts/ \
  --reverse
```

## Troubleshooting

### "Could not find Steam userdata directory"
- Ensure Steam is installed on your system
- Check that the paths in `STEAM_CONFIG_PATHS` match your installation
- Manually specify the source path with `--source`

### "No templates found"
- Make sure you have created some controller configurations in Steam
- Check that you're pointing to the correct user ID directory
- Use `--list` to see what the tool can find

## Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues for bugs and feature requests.

## License

This project is open source and available under the MIT License.

## Disclaimer

This tool is not affiliated with or endorsed by Valve Corporation. Steam Deck and Steam are trademarks of Valve Corporation. Use this tool at your own risk and always backup your configurations before making changes.

## Author

Semyon Vlasov

## Related Projects

- [Steam Controller Configuration](https://partner.steamgames.com/doc/features/steam_controller)
- [Steam Input API](https://partner.steamgames.com/doc/api/isteaminput)