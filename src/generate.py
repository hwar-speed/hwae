"""
HWAE (Hostile Waters Antaeus Eternal)

Python package (released as a pyinstaller exe) to generate additional maps for Hostile Waters: Antaeus Rising (2001)
"""

import os
import shutil
import pathlib
from pathlib import Path

from fileio.cfg import CfgFile
from fileio.lev import LevFile
from fileio.ob3 import Ob3File
from fileio.ars import ArsFile
from fileio.pat import PatFile
from fileio.ail import AilFile
from fileio.ait import AitFile

from construction import ConstructionManager
from noisegen import NoiseGenerator
from objects import ObjectHandler
from terrain import TerrainHandler
from texture import select_map_texture_group
from minimap import generate_minimap
from zone_manager import ZoneManager, ZoneType, ZoneSize, ZoneSubType
from constants import NEW_LEVEL_NAME
from paths import get_assets_path, get_templates_path, get_textures_path
from logger import setup_logger, close_logger
from config_loader import load_config, MapConfig


def generate_new_map(
    progress_callback: callable,
    complete_callback: callable,
    config_path: str,
    exe_parent: Path,
) -> None:
    """Generates a new game map with randomized elements for Hostile Waters: Antaeus Rising.

    This function handles the entire process of generating a new map, including setting up
    file objects, selecting textures, generating terrain, and populating the map with objects
    and zones. The map is saved to the specified output location.

    Args:
        progress_callback (callable): A callback function to update the progress of map generation.
        complete_callback (callable): A callback function to indicate that the generation is complete.
        config_path (str): The path to the configuration file.
        exe_parent (Path): The parent path where the output files will be saved.
    """

    # Set up the logger outside the try block so it can be closed in the finally block
    logger = None
    try:

        # STEP 1 - INITALISATION -----------------------------------------------------------
        progress_callback("Starting...")

        # Set up the logger
        logger = setup_logger(exe_parent / NEW_LEVEL_NAME)

        # Load configuration
        map_config = load_config(config_path) if config_path else load_config()
        logger.info(f"Using configuration: {map_config}")

        # Initialize noise generator (seed will be set by config if specified)
        if map_config.seed == -1:
            noise_generator = NoiseGenerator()
            logger.info(f"Using random seed of {noise_generator.get_seed()}")
        else:
            logger.info(f"Using seed: {map_config.seed}")
            noise_generator = NoiseGenerator(seed=map_config.seed)

        # Use map size from config
        map_size_template = "large"  # CURRENTLY NO OTHER SUPPORTED
        template_root = get_templates_path()
        zonegen_root = get_assets_path() / "zonegen"
        texture_root = get_textures_path()

        # STEP 2 - CLEAN EXISTING FILES ----------------------------------------------------
        progress_callback("Cleaning existing files")
        # check if the map folder exists - if so, remove all files in it
        if (exe_parent / NEW_LEVEL_NAME).exists():
            shutil.rmtree(exe_parent / NEW_LEVEL_NAME, ignore_errors=True)

        # STEP 3 - SET UP COMMON FILES -----------------------------------------------------
        progress_callback("Importing common data")
        logger.info("Setting up file objects and copying template files")
        cfg_data = CfgFile(template_root / f"{map_size_template}.cfg")
        lev_data = LevFile(template_root / f"{map_size_template}.lev")
        ars_data = ArsFile(template_root / "common.ars")
        ait_data = AitFile(template_root / "common.ait")
        ob3_data = Ob3File("")
        pat_data = PatFile("")
        ail_data = AilFile("")
        os.makedirs(exe_parent / NEW_LEVEL_NAME, exist_ok=True)
        shutil.copy(
            template_root / "common.s0u",
            exe_parent / NEW_LEVEL_NAME / f"{NEW_LEVEL_NAME}.s0u",
        )
        shutil.copy(
            template_root / "common.for",
            exe_parent / NEW_LEVEL_NAME / f"{NEW_LEVEL_NAME}.for",
        )

        # STEP 3 - GENERATE PALETTE --------------------------------------------------------
        progress_callback("Generating palette")
        logger.info("Selecting map texture group")
        select_map_texture_group(
            path_to_textures=texture_root,
            cfg=cfg_data,
            noise_gen=noise_generator,
            paste_textures_path=exe_parent / NEW_LEVEL_NAME,
        )
        logger.info("Generating terrain from noise")
        terrain_handler = TerrainHandler(lev_data, noise_generator)
        terrain_handler.set_terrain_from_noise()

        # STEP 4 - HANDLE COMMON ARS -------------------------------------------------------
        progress_callback("Loading map logic")
        mission_type = "destroy_all"  # ONLY TYPE OF MISSION SUPPORTED FOR NOW
        logger.info(f"Setting mission type: {mission_type}")
        ars_data.load_additional_data(template_root / f"{mission_type}.ars")
        # set carrier shells
        carrier_shells = noise_generator.randint(1, 4)
        logger.info(f"Setting carrier shells: {carrier_shells}")
        ars_data.add_action_to_existing_record(
            record_name="HWAE set carrier shells",
            action_title="AIScript_SetCarrierShells",
            action_details=[str(carrier_shells)],
        )

        # STEP 5 - OBJECT INIT -------------------------------------------------------
        progress_callback("Object initalisation")
        logger.info("Creating object handler")
        object_handler = ObjectHandler(terrain_handler, ob3_data, noise_generator)
        logger.info("Adding carrier")
        carrier_mask = object_handler.add_carrier_and_return_mask()

        # STEP 6 - ZONE MANAGER -------------------------------------------------------
        progress_callback("Creating default zones")
        logger.info("Creating zone manager")
        zone_manager = ZoneManager(object_handler, noise_generator, zonegen_root)

        # starting scrap
        # issue 7 - the below will return a random location within the mask if it
        # ... cant fit a scrap zone, so place the revealer there regardless. it
        # ... will really rarely be in the middle of an enemy base, but this will
        # ... only happen if there isnt space for a tiny scrap zone
        zone_coords, (xr, zr) = zone_manager.add_tiny_scrap_near_carrier_and_calc_rally(
            carrier_mask
        )
        logger.info("Adding map revealer")  # add at zone coords (which might also
        # ... be an empty space if no zone could fit)
        object_handler.add_object_at_coords("MapRevealer1", *zone_coords)
        # and set rally point (which if no zone can fit is the same as the rally
        # ... point coords)
        yr = terrain_handler.get_height(xr, zr)
        cfg_data["RallyPoint"] = f"{zr*10*51.7:.6f},{yr:.6f},{xr*10*51.7:.6f}"

        # at least one tiny base
        zone_manager.generate_random_zones(
            1, zone_type=ZoneType.BASE, zone_size=ZoneSize.TINY
        )

        # STEP 7 - ZONE (ENEMY) -------------------------------------------------------
        progress_callback("Creating enemy base zones")
        logger.info("Generating enemy base zones")
        num_extra_enemy_bases = (
            map_config.num_extra_enemy_bases - 1
            # ^ take off 1 as we always get at least 1 base
            if map_config.num_extra_enemy_bases >= 0
            else noise_generator.randint(1, 5)
        )
        zone_manager.generate_random_zones(num_extra_enemy_bases, ZoneType.BASE)

        # STEP 8 - ZONE (SCRAP) -------------------------------------------------------
        progress_callback("Creating scrap zones")
        logger.info("Generating additional scrap zones")
        num_scrap_zones = (
            map_config.num_scrap_zones - 1
            # ^ take off 1 as we always get at least 1 scrap zone
            if map_config.num_scrap_zones >= 0
            else noise_generator.randint(1, 5)
        )
        zone_manager.generate_random_zones(num_scrap_zones, zone_type=ZoneType.SCRAP)

        # STEP 9 - ZONE POPULATE -------------------------------------------------------
        progress_callback("Processing zones (texturing, flattening, populating)")
        logger.info("Processing zones (texturing, flattening, populating)")
        for zone in object_handler.zones:
            terrain_handler.apply_texture_based_on_zone(zone)
            terrain_handler.flatten_terrain_based_on_zone(
                zone, all_existing_zones=object_handler.zones
            )
            zone.populate(noise_generator, object_handler)

        # STEP 10 - MISC OBJECTS -------------------------------------------------------
        progress_callback("Adding other objects...")
        logger.info("Adding scenery")
        object_handler.add_scenery(map_size_template)
        logger.info("Adding alien miscellaneous objects")
        object_handler.add_alien_misc(carrier_xz=[xr, zr], map_size=map_size_template)
        # pick 3-6 random points within the map for patrol
        logger.info("Creating patrol points")
        patrol_points = object_handler.create_patrol_points(
            n_points=noise_generator.randint(3, 7)
        )
        pat_data.add_patrol_record("patrol1", patrol_points)

        logger.info("Adding flying units with patrol routes")
        for _ in range(noise_generator.randint(3, 7)):
            new_obj_id = object_handler.add_object_on_land_random(
                "MediumFlyer",  # small flyers seem to get stuck on terrain
                team=7,  # <-- use the last alien team, same as scattered AA and radar
                required_radius=4,
                y_offset=15,
            )
            if new_obj_id is None:
                continue
            ars_data.add_action_to_existing_record(
                record_name="HWAE patrol 1",
                action_title="AIScript_AssignRoute",
                action_details=['"patrol1"', f"{new_obj_id - 1}"],
            )

        # STEP 11 - MINIMAP -------------------------------------------------------
        progress_callback("Generating minimap")
        logger.info("Generating minimap")
        generate_minimap(
            terrain_handler, cfg_data, exe_parent / NEW_LEVEL_NAME / "map.pcx"
        )

        # STEP 12 - CONSTRUCTION ----------------------------------------------------------
        # do this as late as possible - so if it changes, it doesnt change the level data
        progress_callback("Selecting vehicles & addons")
        logger.info("Setting up construction availability")
        construction_manager = ConstructionManager(
            ars_data, noise_generator, map_config
        )
        construction_manager.select_random_construction_availability()

        # Set EJ if not already set by configuration
        if map_config.starting_ej == -1:
            cfg_data["LevelCash"] = noise_generator.randint(12, 32) * 250  # 4k-8k
            logger.info(f"Set random EJ: {cfg_data['LevelCash']}")

        # STEP 13 - FINALISE SCRIPT/TRIGGERS -------------------------------------------------------
        progress_callback("Finalizing scripts and triggers")
        logger.info("Finalizing scripts and triggers")
        for zone in object_handler.zones:
            zone.update_mission_logic(
                level_logic=ars_data,
                location_data=ail_data,
                text_data=ait_data,
                template_root=template_root,
                construction_manager=construction_manager,
            )

        # STEP 14 - SAVE -------------------------------------------------------
        progress_callback("Saving all files")
        logger.info("Saving all files to output location")
        for file in [lev_data, cfg_data, ob3_data, ars_data, pat_data, ail_data]:
            file.save(exe_parent / NEW_LEVEL_NAME, NEW_LEVEL_NAME)
        # save ait in special place
        ait_path = pathlib.Path(exe_parent / "Text" / "English")
        ait_path.mkdir(parents=True, exist_ok=True)
        ait_data.save(ait_path, NEW_LEVEL_NAME)
        logger.info("Cleaning up .aim files")
        for aim_file in (exe_parent / NEW_LEVEL_NAME).glob("*.aim"):
            os.remove(aim_file)

        # Handle the Levels.lst file
        logger.info("Handling Levels.lst")
        levels_file = exe_parent / "Config" / "Levels.lst"
        template_levels = template_root / "Levels.lst"
        # backup existing file if needed
        if (
            levels_file.exists()
            and levels_file.read_text() != template_levels.read_text()
        ):
            logger.info("Backing up existing Levels.lst")
            levels_file.rename(levels_file.with_suffix(".lst.bak"))
        # finally copy the template Levels.lst (after making the folder(s))
        levels_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(template_levels, levels_file)
        logger.info("Saved Levels.lst")

        logger.info("Map generation complete!")
        # save the json config used into the new level directory (but set the seed
        # ... to the seed we have used though)
        map_config.seed = noise_generator.get_seed()
        map_config.to_json(exe_parent / NEW_LEVEL_NAME / "HWAE_config.json")
        close_logger()
        progress_callback("Done")
        complete_callback()

    finally:
        # Always close the logger, even if an exception occurred
        if logger is not None:
            logger.info("Closing logger")
            close_logger()
