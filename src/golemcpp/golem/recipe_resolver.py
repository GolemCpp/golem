'''
Which recipe serves an identity, and which cookbook it came from.

A recipe is named after what it answers to, therefore finding one is a probe and
never a listing: the rungs of the identity, most specific first, in each
cookbook from the last listed to the first. Nothing a cookbook holds is read
before a rung matches, so what it holds cannot slow a lookup down.
'''

from golemcpp.golem import project_file
from golemcpp.golem.declared_recipe import DeclaredRecipe
from golemcpp.golem.recipe import Recipe

class RecipeResolver:
    '''The recipes a stack of cookbooks can serve, in the order they answer.'''

    def __init__(self, cached_cookbooks):
        self.cached_cookbooks = cached_cookbooks

    def resolve(self, recipe_id) -> Recipe:
        '''
        Return the recipe serving an identity.

        Raise when no cookbook answers, and when the one that does answers
        nothing a caller could use.
        
        What a caller then asks of the recipe is its own business.
        '''

        for cookbook in reversed(self.cached_cookbooks):
            for rung in recipe_id.rungs():
                declared = DeclaredRecipe.read(cookbook, rung)

                if declared is None:
                    continue

                recipe = Recipe.resolve(declared)
                self.require_an_answer(recipe)
                self.report(recipe_id, recipe)

                return recipe

        self.refuse(recipe_id)

    @staticmethod
    def require_an_answer(recipe):
        '''Refuse a recipe saying neither where its package is nor how to build it.'''
        # Dropping to a shorter rung instead would serve a recipe nobody asked
        # for, so a directory named right and holding nothing is an error case.
        if recipe:
            return

        raise RuntimeError(
            "ERROR: {} holds no project file ({}) and names no locator:\n"
            "  {}".format(
                recipe.served_by,
                project_file.PROJECT_FILE_NAMES_LISTED,
                recipe.served_by.directory))

    @staticmethod
    def report(recipe_id, recipe):
        '''Say which recipe served an identity, and which cookbook it came from.'''
        # In the shape a resolved version is reported in.
        print("{}: served by {} ({})".format(
            recipe_id, recipe.served_by.rung, recipe.served_by.cookbook.cache_key))

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
                project_file.PROJECT_FILE_NAMES_LISTED,
                len(self.cached_cookbooks),
                searched or '  (none)',
            )
        )
