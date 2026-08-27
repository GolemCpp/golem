'''
What one cookbook declares for one recipe name.

A recipe is a directory, therefore what an author declares is everything in it:
the manifest saying where the package is, and the project file saying how to
build it. A Recipe is resolved from these, one per cookbook it was found in.
'''

import os
from dataclasses import dataclass
from dataclasses import field

from golemcpp.golem import locator as locator_module
from golemcpp.golem import project_file
from golemcpp.golem import recipe_manifest
from golemcpp.golem.recipe_manifest import RecipeManifest


@dataclass(frozen=True)
class DeclaredRecipe:
    '''One recipe directory, read.'''

    # Where the directory is, which cookbook holds it, and the rung it answers
    # at. The rung is a SourceId.
    directory: str = ''
    cookbook: object = None
    rung: object = None
    manifest: RecipeManifest = field(default_factory=RecipeManifest)

    @classmethod
    def read(cls, cookbook, rung):
        '''
        Read what a cookbook declares at a rung, or None where it declares
        nothing.

        Answering None is what lets the probe carry on to the next rung, so a
        cookbook holding no such directory costs one stat.
        '''
        directory = cls.directory_of(cookbook, rung)

        if not os.path.exists(directory):
            return None

        return cls(
            directory=directory,
            cookbook=cookbook,
            rung=rung,
            manifest=RecipeManifest.read(
                recipe_manifest.recipe_manifest_path(directory),
                origin=cls.describe(cookbook, rung),
            ),
        )

    @staticmethod
    def directory_of(cookbook, rung):
        '''Name where a rung would sit in a cookbook.'''
        # Recipes sit in the cookbook's content, never at the resource root.
        return os.path.join(cookbook.source_path, str(rung))

    @staticmethod
    def describe(cookbook, rung):
        '''Name a recipe the way a message about it does.'''
        return "recipe '{}' in cookbook '{}'".format(rung, cookbook.cache_key)

    def __str__(self):
        return self.describe(self.cookbook, self.rung)

    @property
    def locator(self) -> str:
        '''
        Where this declaration says its package is, empty when it says nothing.

        A relative locator is relative to the recipe directory.
        '''
        locator = self.manifest.locator

        if not locator or not is_relative(locator):
            return locator

        return os.path.realpath(os.path.join(self.directory, locator))

    @property
    def project_directory(self) -> str:
        '''Where this declaration's project file is, empty when it holds none.'''
        if not project_file.holds_a_project(self.directory):
            return ''

        return self.directory


def is_relative(locator: str) -> bool:
    '''Is a locator a path resolved against something else?'''
    # A URL and an scp-style address are neither, and `is_bare_path` is what
    # tells a path from them, the way git does.
    return locator_module.is_bare_path(locator) and not os.path.isabs(locator)
