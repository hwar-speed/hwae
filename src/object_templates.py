"""
HWAE (Hostile Waters Antaeus Eternal)

src.object_templates

This module contains templates for object placement (e.g. for placing groups of
alien AA guns, or groups of scrap/salvage)
"""

from src.models import Team, ObjectContainer


# NOTE since this is a dict based structure, no optional keys
TEMPLATE_ALIEN_AA = [
    # first entry is the main object
    ObjectContainer(
        object_type="Alienspybase",
        team=Team.ENEMY,
        required_radius=2,
    ),
    # and subsequent entries are associated objects, so they
    # ... have x,y,z offsets relative to the first
    ObjectContainer(
        object_type="Alienackackgun",
        team=Team.ENEMY,
        required_radius=2,
        # below values came from ob3 review of an existing map/ob3 file
        template_x_offset=0.008398056640626095,
        template_y_offset=18.072725546874995,
        template_z_offset=0.45655822656249256,
    ),
]
