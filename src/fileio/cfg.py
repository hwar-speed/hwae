"""
HWAE (Hostile Waters Antaeus Eternal)

fileio.cfg

Contains all info to read and write HWAR's .cfg file type
"""

import struct
from dataclasses import dataclass
import logging
import os
import time


@dataclass
class _CfgRecord:
    """Container for a CFG file record - so we can maintain order,
    just in case HWAR expects a certain CFG section order"""

    section: str
    value: list[str]


@dataclass
class CfgFile:
    """Container for a CFG file"""

    full_file_path: str

    def __post_init__(self):
        """Read the specified file and set the internal data"""
        with open(self.full_file_path, "r") as f:
            data = f.read()
        # split into lines, then split into section headers and
        # ... make a dict
        self.records = []
        current_record = None

        # Parse the data
        for line in data.splitlines():
            line = line.strip()
            # strip comments and whitespace
            if ";" in line:
                line = line.split(";")[0].strip()
            if not line:
                continue

            if line.startswith("["):
                # New section found, create a new record
                if current_record is not None:
                    self.records.append(current_record)
                current_record = _CfgRecord(line.strip("[]"), [])
            elif current_record is not None:
                # Add content to current section
                current_record.value.append(line)

        # Don't forget to add the last record
        if current_record is not None:
            self.records.append(current_record)

    def save(self, save_in_folder: str, file_name: str) -> None:
        """Saves the CFG file to the specified path, using the data stored
        in this instance

        Args:
            save_in_folder (str): Location to save the file to
            file_name (str): Name of the file to save as
        """
        if not file_name.endswith(".cfg"):
            file_name += ".cfg"
        logging.info(f"Saving CFG file to: {save_in_folder}/{file_name}")

        # Create output path
        output_path = os.path.join(save_in_folder, file_name)

        # Write the file
        with open(output_path, "w") as f:
            # Add header comment with timestamp
            f.write(f";Created by HWAE at {time.strftime('%d\\%m\\%Y (%H:%M)')}\n")

            # Write each section
            for record in self.records:
                # Write section header
                f.write(f"[{record.section}]\n")
                # Write section values
                for value in record.value:
                    f.write(f"{value}\n")
                # Add blank line between sections
                f.write("\n")
