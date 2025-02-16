"""
HWAE (Hostile Waters Antaeus Eternal)

src.objects

Contains all info regarding objects for the level
"""

from dataclasses import dataclass
import logging
import numpy as np
from enum import IntEnum, auto
from typing import Union

from src.fileio.ob3 import Ob3File, MAP_SCALER
from src.noisegen import NoiseGenerator
from src.terrain import TerrainHandler


class LocationEnum(IntEnum):
    LAND = auto()
    WATER = auto()
    COAST = auto()


class Team(IntEnum):
    PLAYER = 0
    ENEMY = 1
    # TODO support multiple teams (requires .for file likely)
    NEUTRAL = 4294967295  # FFFF


@dataclass
class ObjectHandler:
    terrain_handler: TerrainHandler
    ob3_interface: Ob3File
    noise_generator: NoiseGenerator

    def __post_init__(self):
        """Initialize the cached object mask"""
        self._cached_object_mask = np.ones(
            (
                self.terrain_handler.width,
                self.terrain_handler.length,
            )
        )

    def add_scenery(self, map_size: str) -> None:
        """Adds a lot of random/different scenery objects to the level"""
        # TODO in future, switch below on map size - the below seems reasonable
        # ... for 'large' 256x256
        objs = (
            ["troprockcd"] * 8
            + ["troprockbd"] * 7
            + ["troprockad"] * 6
            + ["troprockcw"] * 5
            + ["troprockaw"] * 2
            + ["palm1"] * 80
            + ["plant1"] * 30
            + ["palm2"] * 50
            + ["palm3"] * 25
            + ["rubblea"] * 5
            + ["rubbleb"] * 5
            + ["rubblec"] * 5
            + ["rubbled"] * 5
            + ["rubblee"] * 5
        )
        for obj in objs:
            self.add_object_on_land_random(
                obj,
                team=Team.NEUTRAL,
                required_radius=2,
            )
        logging.info(f"Done adding {len(objs)} scenery objects")

    def _update_mask_grid_with_radius(
        self, location_grid: np.ndarray, x: int, z: int, radius: int, set_to: int = 0
    ) -> None:
        """Updates the location grid to set_to in a radius around a location - used
        for object location masking or similar. Uses a simpler distance calculation
        since we only need integer radius.

        Args:
            location_grid (np.ndarray): Location grid to set 0 within
            x (int): x location
            z (int): z location
            radius (int): Radius to set within (must be integer)
            set_to (int): Value to set the location grid to
        """
        # Get bounds of the circle
        x_min = max(0, x - radius)
        x_max = min(self.terrain_handler.width, x + radius + 1)
        z_min = max(0, z - radius)
        z_max = min(self.terrain_handler.length, z + radius + 1)

        # For integer radius, we can just iterate through the square and check distance
        radius_sq = radius * radius  # Square once instead of sqrt
        for i in range(x_min, x_max):
            dx = i - x
            dx_sq = dx * dx
            for j in range(z_min, z_max):
                dz = j - z
                # If point is within radius, set it
                if dx_sq + dz * dz <= radius_sq:
                    location_grid[i, j] = set_to

        return location_grid

    def _update_cached_object_mask(self, x: int, z: int, required_radius: int) -> None:
        """Updates the cached object mask with a new object's radius

        Args:
            x (int): x location of new object
            z (int): z location of new object
            required_radius (int): radius to mark as occupied
        """
        self._cached_object_mask = self._update_mask_grid_with_radius(
            self._cached_object_mask, x, z, required_radius, set_to=0
        )

    def _get_binary_transition_mask(self, input_mask: np.ndarray) -> np.ndarray:
        """Generates a boolean edge transition mask, used for object radius checks
        as well as terrain transition checks (water-land etc). Iterates over the
        input mask, identifying the 2d cells where the state transitions to/from
        0. That cell is then marked as 1, all other cells are 0.

        Args:
            input_mask (np.ndarray): Input mask to check

        Returns:
            np.ndarray: Mask of edges from the input mask
        """
        # Create output mask of same shape as input
        transition_mask = np.zeros_like(input_mask, dtype=int)

        # Check horizontal transitions (left to right)
        horizontal_transitions = (input_mask[:, 1:] != input_mask[:, :-1]).astype(int)
        transition_mask[:, 1:] += horizontal_transitions
        transition_mask[:, :-1] += horizontal_transitions

        # Check vertical transitions (top to bottom)
        vertical_transitions = (input_mask[1:, :] != input_mask[:-1, :]).astype(int)
        transition_mask[1:, :] += vertical_transitions
        transition_mask[:-1, :] += vertical_transitions

        # Convert any non-zero values to 1
        transition_mask = (transition_mask > 0).astype(int)

        return transition_mask

    def _get_object_mask(self) -> np.ndarray:
        """Returns the cached object mask. The mask is maintained by _update_cached_object_mask
        which is called whenever a new object is added.

        Returns:
            np.ndarray: Object mask where 0 is occupied and 1 is free
        """
        return self._cached_object_mask

    def _get_land_mask(self, cutoff_height=-20) -> np.ndarray:
        """Generates a boolean map grid, where 1 is land and 0 is water via terrain
        lookup. Is returned in the same dimensions as the terrain (e.g. LEV scale).

        Args:
            cutoff_height (float, optional): Height above which is considered land.
            Defaults to -20.

        Returns:
            np.ndarray: Land mask
        """
        # assume more water than land, so start with zeros
        mask = np.zeros(
            (
                self.terrain_handler.width,
                self.terrain_handler.length,
            )
        )
        # check each point against the raw terrain height
        for x in range(self.terrain_handler.width):
            for z in range(self.terrain_handler.length):
                if self.terrain_handler.get_height(x, z) > cutoff_height:
                    mask[x, z] = 1

        return mask

    def _get_water_mask(self, cutoff_height=-20) -> np.ndarray:
        """Generates a boolean map grid, where 1 is water and 0 is land via terrain
        lookup. Is returned in the same dimensions as the terrain (e.g. LEV scale).

        Args:
            cutoff_height (float, optional): Height above which is considered water.
            Defaults to -20.

        Returns:
            np.ndarray: Water mask
        """
        return 1 - self._get_land_mask(cutoff_height=cutoff_height)

    def _get_coast_mask(
        self, cutoff_height: int = -20, radius_percent: int = 30
    ) -> np.ndarray:
        """Generates a boolean map grid, where 1 is coast and 0 not coast, within a
        radius of the max width/length of the terrain. Default radius is 30%

        Args:
            cutoff_height (int, optional): Height above which is considered coast.
            Defaults to -20.
            radius_percent (int, optional): Radius of the coast mask. Defaults to 30[%].

        Returns:
            np.ndarray: Coast mask
        """
        # assume more water than land, so start with zeros
        mask = np.zeros(
            (
                self.terrain_handler.width,
                self.terrain_handler.length,
            )
        )

        # find edges where water meets land, by finding edges of a binary masked
        # ... terrain map
        binary_terrain = self.terrain_handler._get_height_2d_array().copy()
        binary_terrain[binary_terrain < 0] = 0
        binary_terrain[binary_terrain > 0] = 1
        edge_mask = self._get_binary_transition_mask(binary_terrain)

        # set acceptable spawn within radius_percent% map dims radius of any terrain
        # ... point (this is a crude way to capture the shore, if we then crop out land)
        radius = (
            radius_percent
            / 100
            * max(self.terrain_handler.width, self.terrain_handler.length)
        )
        radius = int(radius)

        # Only apply radius around points that are both edges and above cutoff height
        for x in range(self.terrain_handler.width):
            for z in range(self.terrain_handler.length):
                if edge_mask[x, z] == 1:
                    mask = self._update_mask_grid_with_radius(
                        mask, x, z, radius, set_to=1
                    )
        # now multiply this against the land mask - so we exclude land, giving us only
        # ... coast
        return mask * self._get_water_mask(cutoff_height=cutoff_height)

    def _find_location(
        self, where: LocationEnum = LocationEnum.LAND, required_radius: float = 1
    ) -> tuple[float, float]:
        """Finds a random location on the land for the specified object. Will avoid
        clashing with other objects within their object's radius, including the
        optional required_radius (default 1 units on original LEV scale)

        Args:
            where (LocationEnum): Where to find the location (land, water, coast)
            required_radius (float, optional): Keep-clear radius of this new
            object. Defaults to 1 (unit = the original LEV scale e.g. 256x256).

        Returns:
            tuple[float, float]: x,z location of the object
        """
        # get correct reference mask from where
        if where == LocationEnum.WATER:
            where_mask = self._get_water_mask()
        elif where == LocationEnum.COAST:
            where_mask = self._get_coast_mask()
        else:
            where_mask = self._get_land_mask()
        # and apply that mask
        mask = where_mask * self._get_object_mask()

        # detect edges, and for each edge draw a circle of radius required_radius
        # ... (rounded up to closest int)
        required_radius = max(1, round(required_radius))
        edge_mask = self._get_binary_transition_mask(mask)
        for x in range(self.terrain_handler.width):
            for z in range(self.terrain_handler.length):
                if edge_mask[x, z] == 1:
                    mask = self._update_mask_grid_with_radius(
                        mask,
                        x,
                        z,
                        required_radius // 2,
                        set_to=0,  # mark as not allowed
                    )

        # check if we have any non-zero values in the edge mask
        if np.any(mask):
            return self.noise_generator.select_random_entry_from_2d_array(mask)
        logging.info("Find location: no suitable location found (empty mask)")
        return None

    def add_carrier(self) -> None:
        """Finds a location for the carrier, by using a coast search with a large
        required radius, then adds the object directly (special as it also sets the
        rotation of the object)
        """
        # find a coast location
        logging.info("ADD Carrier: Starting")
        x, z = self._find_location(where=LocationEnum.COAST, required_radius=30)

        # Calculate angle from north to inward-facing vector
        center_x = self.terrain_handler.width / 2
        center_z = self.terrain_handler.length / 2
        angle = np.rad2deg(np.arctan2(center_z - z, center_x - x))
        logging.info("ADD Carrier: Calculated location and angle")

        # Update the cached object mask before adding the object
        self._update_cached_object_mask(x, z, 30)

        # add directly via ob3 interface, as this is a bit special
        self.ob3_interface.add_object(
            object_type="Carrier",
            location=[z, 15, x],  # opposite order due to LEV flip
            team=Team.PLAYER,
            y_rotation=angle,
            required_radius=30,
        )
        logging.info("ADD Carrier: Done")

    def add_object_on_land_random(
        self,
        object_type: str,
        attachment_type: str = "",
        team: Union[int | Team] = Team.ENEMY,
        y_offset: float = 0,
        y_rotation: float = 0,
        required_radius: float = 1,
    ) -> None:
        """Creates a new object in the level, selects a random land location, then
        uses the normal add object method with the height determined from the terrain

        Args:
            object_type (str): Type of the object
            location (np.array): Location of the object in LEV 3D space [x, y, z]
            attachment_type (str, optional): Type of attachment. Defaults to "".
            team (Union[int | Team], optional): Team number. Defaults to Team.ENEMY.
            y_rotation (float, optional): Rotation of the object in degrees. Defaults to 0.
            y_offset (float, optional): Vertical offset of the object. Defaults to 0.
            required_radius (float, optional): Keep-clear radius of this new object. Defaults to 1.
        """
        # below defaults to add on land
        returnval = self._find_location(required_radius=required_radius)
        if returnval is None:
            return
        z, x = returnval
        # find height at the specified x and z location (in LEV 3D space)
        height = self.terrain_handler.get_height(z, x)
        # check the height isnt negative, else its water so dont add
        if height + y_offset < 0:
            return

        # Update the cached object mask before adding the object
        self._update_cached_object_mask(x, z, int(required_radius))

        # now use the normal add object method
        self.ob3_interface.add_object(
            object_type=object_type,
            location=np.array([x, height + y_offset, z]),
            attachment_type=attachment_type,
            team=team.value if isinstance(team, Team) else team,
            y_rotation=y_rotation,
            required_radius=required_radius,
        )

    def add_scenery(self, map_size: str) -> None:
        """Adds a lot of random/different scenery objects to the level"""
        # TODO in future, switch below on map size - the below seems reasonable
        # ... for 'large' 256x256
        objs = (
            ["troprockcd"] * 8
            + ["troprockbd"] * 7
            + ["troprockad"] * 6
            + ["troprockcw"] * 5
            + ["troprockaw"] * 2
            + ["palm1"] * 80
            + ["plant1"] * 30
            + ["palm2"] * 50
            + ["palm3"] * 25
            + ["rubblea"] * 5
            + ["rubbleb"] * 5
            + ["rubblec"] * 5
            + ["rubbled"] * 5
            + ["rubblee"] * 5
        )
        for obj in objs:
            self.add_object_on_land_random(
                obj,
                team=Team.NEUTRAL,
                required_radius=2,
            )
        logging.info(f"Done adding {len(objs)} scenery objects")
