"""
HWAE (Hostile Waters Antaeus Eternal)

src.config_loader

Contains functionality for loading and managing map configuration settings
"""

import json
import os
from dataclasses import dataclass, field
from typing import List, Union
from pathlib import Path

from logger import get_logger
from paths import get_assets_path
from constants import VERSION_STR

logger = get_logger()


@dataclass
class MapConfig:
    """Class for storing and managing map configuration settings"""

    # Default values
    seed: int = -1
    num_extra_enemy_bases: int = -1
    num_scrap_zones: int = -1
    soulcatcher_include_list: List[str] = field(default_factory=list)
    weapon_include_list: List[str] = field(default_factory=list)
    addon_include_list: List[str] = field(default_factory=list)
    vehicle_include_list: List[str] = field(default_factory=list)
    starting_ej: int = -1
    created_version: str = VERSION_STR

    @classmethod
    def from_json(cls, json_path: Union[str, Path]) -> "MapConfig":
        """Load configuration from a JSON file

        Args:
            json_path: Path to the JSON configuration file

        Returns:
            MapConfig: An instance of MapConfig with values from the JSON file
        """
        try:
            with open(json_path, "r") as f:
                config_data = json.load(f)

            logger.info(f"Loaded configuration from {json_path}")

            # check version and warn in log
            if config_data.get("created_version", "") != VERSION_STR:
                logger.warning(
                    f"Configuration file version {config_data['created_version']} does "
                    f"not match current version {VERSION_STR}. The generated map may "
                    "be different between this version"
                )

            return cls(**config_data)
        except FileNotFoundError:
            logger.info(f"Configuration file not found at {json_path}, using defaults")
            return cls()
        except json.JSONDecodeError:
            logger.info(f"Error parsing JSON from {json_path}, using defaults")
            return cls()
        except Exception as e:
            logger.info(
                f"Unexpected error loading configuration: {str(e)}, using defaults"
            )
            return cls()

    def to_json(self, json_path: Union[str, Path]) -> bool:
        """Save configuration to a JSON file

        Args:
            json_path: Path to save the JSON configuration file

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Ensure directory exists
            json_path = Path(json_path)
            json_path.parent.mkdir(parents=True, exist_ok=True)

            with open(json_path, "w") as f:
                json.dump(self.__dict__, f, indent=4)

            logger.info(f"Saved configuration to {json_path}")
            return True
        except Exception as e:
            logger.error(f"Error saving configuration to {json_path}: {str(e)}")
            return False


# NON CLASS BASED FUNCTION BELOW
def load_config(config_path: Union[str, Path] = None) -> MapConfig:
    """Convenience function to load configuration from a JSON file

    Args:
        config_path: Path to the JSON configuration file. If None, uses the default path.

    Returns:
        MapConfig: An instance of MapConfig with values from the JSON file
    """
    if config_path is None:
        config_path = get_assets_path() / "default.json"

    return MapConfig.from_json(config_path)
