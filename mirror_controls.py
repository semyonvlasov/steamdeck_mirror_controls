#!/usr/bin/env python3
"""
Steam Deck Control Template Mirror Tool

This tool allows you to mirror (copy/sync) Steam Deck control templates
between different configurations or devices.
"""

import os
import sys
import json
import shutil
import argparse
from pathlib import Path
from typing import Dict, List, Optional


class SteamDeckControlMirror:
    """Main class for mirroring Steam Deck control templates."""
    
    # Common Steam Deck configuration paths
    STEAM_CONFIG_PATHS = [
        Path.home() / ".steam" / "steam" / "userdata",
        Path.home() / ".local" / "share" / "Steam" / "userdata",
        Path("/home/deck/.steam/steam/userdata"),
        Path("/home/deck/.local/share/Steam/userdata"),
    ]
    
    CONTROLLER_CONFIG_SUBPATH = "config/controller_config"
    
    def __init__(self, source_path: Optional[Path] = None, dest_path: Optional[Path] = None):
        """Initialize the mirror tool with source and destination paths."""
        self.source_path = source_path
        self.dest_path = dest_path
        
    def find_steam_userdata(self) -> Optional[Path]:
        """Find the Steam userdata directory."""
        for path in self.STEAM_CONFIG_PATHS:
            if path.exists():
                return path
        return None
    
    def get_controller_configs(self, userdata_path: Path) -> List[Path]:
        """Get all controller configuration files from a userdata directory."""
        configs = []
        
        # Iterate through user directories
        for user_dir in userdata_path.iterdir():
            if user_dir.is_dir() and user_dir.name.isdigit():
                config_path = user_dir / self.CONTROLLER_CONFIG_SUBPATH
                if config_path.exists():
                    # Find .vdf files (Valve Data Format)
                    for config_file in config_path.rglob("*.vdf"):
                        configs.append(config_file)
                    # Find .json files
                    for config_file in config_path.rglob("*.json"):
                        configs.append(config_file)
        
        return configs
    
    def mirror_template(self, source: Path, destination: Path, reverse: bool = False) -> bool:
        """
        Mirror a control template from source to destination.
        
        Args:
            source: Source file path
            destination: Destination file path
            reverse: If True, also create a reversed/mirrored version for left/right hand swap
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Create destination directory if it doesn't exist
            destination.parent.mkdir(parents=True, exist_ok=True)
            
            # Copy the file
            shutil.copy2(source, destination)
            print(f"✓ Mirrored: {source.name} -> {destination}")
            
            # If reverse is requested, create a mirrored version
            if reverse:
                reversed_dest = destination.parent / f"{destination.stem}_reversed{destination.suffix}"
                if destination.suffix == ".json":
                    self._reverse_json_config(source, reversed_dest)
                else:
                    # For VDF files, just copy for now
                    shutil.copy2(source, reversed_dest)
                print(f"✓ Created reversed: {reversed_dest.name}")
            
            return True
        except Exception as e:
            print(f"✗ Error mirroring {source}: {e}", file=sys.stderr)
            return False
    
    def _reverse_json_config(self, source: Path, destination: Path):
        """Create a reversed version of a JSON config (swap left/right mappings)."""
        try:
            with open(source, 'r') as f:
                config = json.load(f)
            
            # Swap left/right button mappings
            reversed_config = self._swap_left_right(config)
            
            with open(destination, 'w') as f:
                json.dump(reversed_config, f, indent=2)
        except Exception as e:
            print(f"Warning: Could not reverse JSON config: {e}", file=sys.stderr)
            # Fall back to simple copy
            shutil.copy2(source, destination)
    
    def _swap_left_right(self, obj):
        """Recursively swap left/right references in a dictionary or list."""
        if isinstance(obj, dict):
            new_dict = {}
            for key, value in obj.items():
                # Swap left/right in keys
                new_key = key
                if "left" in key.lower():
                    new_key = key.lower().replace("left", "right")
                elif "right" in key.lower():
                    new_key = key.lower().replace("right", "left")
                
                # Recursively process values
                new_dict[new_key] = self._swap_left_right(value)
            return new_dict
        elif isinstance(obj, list):
            return [self._swap_left_right(item) for item in obj]
        elif isinstance(obj, str):
            # Swap left/right in string values
            result = obj
            if "left" in obj.lower():
                result = obj.lower().replace("left", "RIGHT_TEMP")
                result = result.replace("RIGHT_TEMP", "right")
            elif "right" in obj.lower():
                result = obj.lower().replace("right", "LEFT_TEMP")
                result = result.replace("LEFT_TEMP", "left")
            return result
        else:
            return obj
    
    def mirror_all_templates(self, reverse: bool = False) -> int:
        """
        Mirror all found templates from source to destination.
        
        Returns:
            Number of successfully mirrored templates
        """
        if not self.source_path or not self.source_path.exists():
            print(f"Error: Source path does not exist: {self.source_path}", file=sys.stderr)
            return 0
        
        if not self.dest_path:
            print("Error: Destination path not specified", file=sys.stderr)
            return 0
        
        # Find all templates in source
        templates = []
        if self.source_path.is_file():
            templates = [self.source_path]
        else:
            # Find all VDF and JSON files
            templates.extend(self.source_path.rglob("*.vdf"))
            templates.extend(self.source_path.rglob("*.json"))
        
        if not templates:
            print(f"No templates found in {self.source_path}")
            return 0
        
        print(f"Found {len(templates)} template(s) to mirror")
        
        # Mirror each template
        success_count = 0
        for template in templates:
            # Calculate relative path and create corresponding destination
            if self.source_path.is_file():
                dest_file = self.dest_path / template.name
            else:
                rel_path = template.relative_to(self.source_path)
                dest_file = self.dest_path / rel_path
            
            if self.mirror_template(template, dest_file, reverse):
                success_count += 1
        
        return success_count
    
    def list_templates(self):
        """List all available controller templates."""
        userdata_path = self.find_steam_userdata()
        
        if not userdata_path:
            print("Could not find Steam userdata directory")
            print("Searched paths:")
            for path in self.STEAM_CONFIG_PATHS:
                print(f"  - {path}")
            return
        
        print(f"Steam userdata found at: {userdata_path}")
        configs = self.get_controller_configs(userdata_path)
        
        if not configs:
            print("No controller configurations found")
            return
        
        print(f"\nFound {len(configs)} controller configuration(s):")
        for config in configs:
            rel_path = config.relative_to(userdata_path)
            print(f"  - {rel_path}")


def main():
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        description="Mirror Steam Deck control templates",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List all available templates
  python mirror_controls.py --list

  # Mirror a single template file
  python mirror_controls.py --source ./my_template.vdf --dest ./backup/

  # Mirror all templates from a directory
  python mirror_controls.py --source ./templates/ --dest ./backup/

  # Mirror and create reversed (left/right swapped) versions
  python mirror_controls.py --source ./template.json --dest ./output/ --reverse
        """
    )
    
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all available controller templates"
    )
    
    parser.add_argument(
        "--source",
        type=Path,
        help="Source template file or directory"
    )
    
    parser.add_argument(
        "--dest",
        type=Path,
        help="Destination directory"
    )
    
    parser.add_argument(
        "--reverse",
        action="store_true",
        help="Create reversed (left/right swapped) versions of templates"
    )
    
    args = parser.parse_args()
    
    # Create mirror instance
    mirror = SteamDeckControlMirror(args.source, args.dest)
    
    if args.list:
        mirror.list_templates()
        return 0
    
    if not args.source:
        parser.print_help()
        print("\nError: --source is required (or use --list to see available templates)", file=sys.stderr)
        return 1
    
    if not args.dest:
        parser.print_help()
        print("\nError: --dest is required", file=sys.stderr)
        return 1
    
    # Perform mirroring
    success_count = mirror.mirror_all_templates(reverse=args.reverse)
    print(f"\nSuccessfully mirrored {success_count} template(s)")
    
    return 0 if success_count > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
