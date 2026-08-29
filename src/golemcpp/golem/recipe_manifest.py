'''
What a recipe declares about itself, beside the project file it may also hold.

A recipe manifest is written by hand, in a cookbook golem does not own.

A file it cannot read is refused rather than taken for an absent one.

A missing file is benign, and it is the common case, since a recipe is reachable by
name alone.
'''

import json
import os
from dataclasses import dataclass

from golemcpp.golem import source_id
from golemcpp.golem.source_id import SourceId

# What a recipe declares itself in, beside its project file.
RECIPE_MANIFEST_FILENAME = 'recipe.json'

# Newest manifest format this golem reads.
RECIPE_MANIFEST_VERSION = 1


def recipe_manifest_path(recipe_directory: str) -> str:
    return os.path.join(recipe_directory, RECIPE_MANIFEST_FILENAME)


@dataclass(frozen=True)
class RecipeManifest:
    '''
    The fields a recipe.json holds, as written.

    A locator is kept verbatim, therefore one written relative stays relative.
    What it is relative to is the recipe directory, which this does not know.
    '''

    locator: str = ''
    mirrors: tuple = ()
    overrides: str = ''
    version: int = RECIPE_MANIFEST_VERSION

    @classmethod
    def read(cls, path: str, origin: str = None) -> 'RecipeManifest':
        '''
        Read the manifest at path, or an empty one where there is no file.

        Raise on a file golem cannot read as a manifest.

        `origin` is how the recipe is named for logging purposes, defaulting to the
        path, because a path under the cache names its cookbook by a hash.
        '''
        if not os.path.isfile(path):
            return cls()

        origin = origin or path

        try:
            with open(path, 'r', encoding='utf-8') as filein:
                data = json.load(filein)
        except (ValueError, OSError) as error:
            raise RuntimeError(
                "ERROR: {} holds a {} golem cannot read: {}".format(
                    origin, RECIPE_MANIFEST_FILENAME, error
                )
            )

        if not isinstance(data, dict):
            raise RuntimeError(
                "ERROR: {} holds a {}, and a manifest names fields".format(
                    origin, type(data).__name__
                )
            )

        return cls(
            locator=read_locator(data, origin),
            mirrors=read_mirrors(data, origin),
            overrides=read_overrides(data, origin),
            version=read_version(data, origin),
        )


def read_version(data: dict, origin: str) -> int:
    '''
    Read the format version a manifest is written in, 1 when it names none.

    Refuse a version newer than this golem reads.
    '''
    version = data.get('version', RECIPE_MANIFEST_VERSION)

    # A bool is an int in Python, and `"version": true` names no format.
    if isinstance(version, bool) or not isinstance(version, int):
        raise RuntimeError(
            "ERROR: {} declares version '{}', which is not a number".format(
                origin, version
            )
        )

    if version > RECIPE_MANIFEST_VERSION:
        raise RuntimeError(
            "ERROR: {} declares version {}, and this Golem reads {}. Upgrade "
            "Golem, or use a cookbook written for it.".format(
                origin, version, RECIPE_MANIFEST_VERSION
            )
        )

    return version


def read_locator(data: dict, origin: str) -> str:
    '''
    Read where a recipe says the source is, empty when it says nothing.

    A locator isn't an identity, so if an identity is encountered, it's refused.
    '''

    locator = read_text(data, 'locator', origin)

    refuse_an_identity(locator, 'locator', origin)

    return locator


def read_mirrors(data: dict, origin: str) -> tuple:
    '''
    Read the other locators the source is served from.

    A recipe has no default remote when it declares no locator. Mirrors aren't default
    remotes.
    '''

    mirrors = data.get('mirrors')

    if mirrors is None:
        return ()

    if not isinstance(mirrors, list):
        raise RuntimeError(
            "ERROR: {} declares mirrors as {}, and mirrors are written as a "
            "list of locators".format(origin, type(mirrors).__name__)
        )

    for mirror in mirrors:
        if not isinstance(mirror, str):
            raise RuntimeError(
                "ERROR: {} declares a mirror as {}, and a mirror is written as "
                "text".format(origin, type(mirror).__name__)
            )

        refuse_an_identity(mirror, 'mirror', origin)

    return tuple(mirrors)


def refuse_an_identity(locator: str, field: str, origin: str):
    '''Refuse an identity in a field taking a locator.'''
    # A recipe cannot delegate where the source is.
    if not locator.startswith(source_id.FIELD_SEPARATOR):
        return

    raise RuntimeError(
        "ERROR: {} declares the {} '{}', which is an identity. Write "
        "the locator the identity is composed from.".format(origin, field, locator)
    )


def read_overrides(data: dict, origin: str) -> str:
    '''
    Read the recipe this one is a delta on, empty when it is a delta on none.

    Nothing acts on it yet.
    '''
    overrides = read_text(data, 'overrides', origin)

    if not overrides:
        return ''

    try:
        SourceId.parse(overrides)
    except ValueError as error:
        raise RuntimeError(
            "ERROR: {} overrides '{}', which is no identity: {}".format(
                origin, overrides, error
            )
        )

    return overrides


def read_text(data: dict, name: str, origin: str) -> str:
    '''Read a field written as text, empty when the manifest names none.'''
    value = data.get(name, '')

    if not isinstance(value, str):
        raise RuntimeError(
            "ERROR: {} declares {} as {}, and {} is written as text".format(
                origin, name, type(value).__name__, name
            )
        )

    return value
