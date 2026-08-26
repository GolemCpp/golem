'''
Which recipe serves an identity, and which cookbook it came from.

A recipe is named after what it answers to, therefore finding one is a probe and
never a listing: the rungs of the identity, most specific first, in each
cookbook from the last listed to the first. Nothing is read to decide, so what a
cookbook holds cannot slow a lookup down.
'''

import os

# What makes a directory a project, whether it is a project of its own or a
# recipe standing in for one. Ordered as `Context.load_project` tries them, and
# it has to agree with this.
PROJECT_FILE_NAMES = ('golemfile.py', 'golemfile.json')

PROJECT_FILE_NAMES_LISTED = ' or '.join(
    "'{}'".format(name) for name in PROJECT_FILE_NAMES
)


class RecipeResolver:
    '''The recipes a stack of cookbooks can serve, in the order they answer.'''

    def __init__(self, cached_cookbooks):
        self.cached_cookbooks = cached_cookbooks

    def resolve(self, recipe_id):
        '''
        Return the directory of the recipe serving an identity.

        Raise when no cookbook answers, and when the one that does holds no
        project file.
        '''
        for cookbook in reversed(self.cached_cookbooks):
            for rung in recipe_id.rungs():
                directory = self.directory_of(cookbook, rung)

                if not os.path.exists(directory):
                    continue

                self.require_a_project(cookbook, rung, directory)
                self.report(recipe_id, rung, cookbook)

                return directory

        self.refuse(recipe_id)

    @staticmethod
    def directory_of(cookbook, rung):
        '''Name where a rung would sit in a cookbook.'''
        # Recipes sit in the cookbook's content, never at the resource root.
        return os.path.join(cookbook.source_path, str(rung))

    @staticmethod
    def require_a_project(cookbook, rung, directory):
        '''Refuse a recipe directory that holds nothing to load.'''
        if any(
            os.path.exists(os.path.join(directory, name)) for name in PROJECT_FILE_NAMES
        ):
            return

        raise RuntimeError(
            "ERROR: recipe '{}' in cookbook '{}' holds no project file "
            "({}):\n  {}".format(
                rung, cookbook.cache_key, PROJECT_FILE_NAMES_LISTED, directory
            )
        )

    @staticmethod
    def report(recipe_id, rung, cookbook):
        '''Say which recipe served an identity, and which cookbook it came from.'''
        # In the shape a resolved version is reported in.
        print("{}: served by {} ({})".format(recipe_id, rung, cookbook.cache_key))

    def refuse(self, recipe_id):
        '''Refuse an identity no cookbook answers, naming the ones searched.'''
        # The project carries no golemfile of its own, and a message about a
        # missing one sends the reader to the wrong repository entirely.
        searched = '\n'.join(
            '  {}'.format(cookbook.source_path) for cookbook in self.cached_cookbooks
        )

        raise RuntimeError(
            "ERROR: no recipe '{}' and no project file ({}).\n"
            "Searched {} cookbook(s):\n{}".format(
                recipe_id,
                PROJECT_FILE_NAMES_LISTED,
                len(self.cached_cookbooks),
                searched or '  (none)',
            )
        )
