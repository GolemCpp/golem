"""
What a consumer project reads to know what it can ask for.

Written beside the configurations it reads.

Anything golem cannot read as one of its manifests reads as an absent one, because
one `golem resolve` writes the file again.
"""

import json
import os
from dataclasses import dataclass
from dataclasses import field

# Manifest format this Golem reads.
EXPORT_MANIFEST_VERSION = 1


@dataclass(frozen=True)
class ExportManifest:
    """
    Every export a project declares, against the targets each one is filed under.

    `default` is what the project falls back to when being asked to use the defaults.
    """

    exports: dict = field(default_factory=dict)
    default: list = field(default_factory=list)

    def resolve_defaults(self) -> list:
        """
        Resolve the exports a consumer naming neither import nor target is given.

        The declared set, or every export where the project declared none.
        """
        return self.default or list(self.exports)

    def find_owning_export(self, target: str):
        """Find the export owning a target, None where no export owns it."""
        for name, targets in self.exports.items():
            if target in targets:
                return name

        return None

    def write(self, path: str):
        """Write the manifest, replacing what an earlier run left there."""
        content = {
            "version": EXPORT_MANIFEST_VERSION,
            "exports": self.exports,
            "default": self.default,
        }

        with open(path, "w", encoding="utf-8") as fileout:
            json.dump(content, fileout, sort_keys=True, indent=4)

    @classmethod
    def read(cls, path: str):
        """
        Read the manifest at path, or None where there is no manifest to read.

        Returns None for a file that is absent, unreadable, or written in a
        version this golem does not know.
        """
        if not os.path.isfile(path):
            return None

        try:
            with open(path, "r", encoding="utf-8") as filein:
                data = json.load(filein)
        except (ValueError, OSError):
            return None

        if not isinstance(data, dict):
            return None

        if data.get("version") != EXPORT_MANIFEST_VERSION:
            return None

        exports = read_exports(data.get("exports"))
        default = read_names(data.get("default"))

        if exports is None or default is None:
            return None

        return cls(exports=exports, default=default)


def read_exports(exports):
    """Read what each export is filed under, or None where the field is not one."""
    if not isinstance(exports, dict):
        return None

    read = {}

    for name, targets in exports.items():
        if not isinstance(name, str):
            return None

        targets = read_names(targets)
        if targets is None:
            return None

        read[name] = targets

    return read


def read_names(names):
    """Read a field written as a list of names, or None where it is not one."""
    if not isinstance(names, list):
        return None

    if any(not isinstance(name, str) for name in names):
        return None

    return names
