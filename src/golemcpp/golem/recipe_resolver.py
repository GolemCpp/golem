'''
Which recipes serve an identity, and which cookbook each one came from.

A recipe is named after the identity it serves, therefore finding one is a probe
and never a listing: the rungs of the identity, most specific first, in each
cookbook from the last listed to the first. Nothing a cookbook holds is read
before a rung matches, so what it holds cannot slow a lookup down.

A recipe may be a delta on another one, and the search then continues from its
`overrides`. A lookup therefore resolves to a chain of recipes, most derived
first, and this module is what builds it. `Recipe` only reads it. One manifest
is read per link, and still never before a rung matches.
'''

from golemcpp.golem import project_file
from golemcpp.golem import recipe as recipe_module
from golemcpp.golem.declared_recipe import DeclaredRecipe
from golemcpp.golem.recipe import Recipe
from golemcpp.golem.source_id import SourceId

class RecipeResolver:
    '''The recipes a stack of cookbooks can serve, in the order they answer.'''

    def __init__(self, cached_cookbooks):
        self.cached_cookbooks = cached_cookbooks

    def resolve(self, recipe_id, report=True) -> Recipe:
        '''
        Return the recipe serving an identity.

        Raise when no match were found, or when the match contains nothing.

        What a caller then asks of the recipe is its own business.
        '''

        stack = self.searched_cookbooks()
        layer, declared, _ = self.probe(stack, recipe_id)

        if declared is None:
            self.refuse(recipe_id)

        recipe = Recipe(chain=self.chain_from(stack, layer, declared))
        self.require_an_answer(recipe)

        if report:
            self.report(recipe_id, recipe)

        return recipe

    def searched_cookbooks(self) -> list:
        '''List the cookbooks in the order they are asked, most derived first.'''
        return list(reversed(self.cached_cookbooks))

    @staticmethod
    def probe(stack, recipe_id, layer=0, skippable='', taken=frozenset()):
        '''
        Find the declaration serving an identity, from `layer` downward.

        Return...
        - which cookbook it came from,
        - the recipe found,
        - the recipe that confirms a cycle happened.

        Probing: Asking for a recipe on a cookbook consists in walking the allowed
        rungs: asking for @a@b@b will look for @a@b@c, then @a@b, then @a.

        Overriding: But each recipe can override another, which restarts the probing
        just described. Although the search excludes the last found recipe
        (`skippable`), finding again a recipe we already visited (`taken`) is a cycle,
        therefore an error case.

        Ladder: If no recipe is found on a cookbook, the probing continues on the next
        cookbook in the stack.
        '''

        for index in range(layer, len(stack)):
            for rung in recipe_id.rungs():
                declared = DeclaredRecipe.read(stack[index], rung)

                if declared is None:
                    continue

                if declared.directory == skippable:
                    continue

                if declared.directory in taken:
                    return index, None, declared

                return index, declared, None

        return len(stack), None, None

    def chain_from(self, stack, layer, declared) -> tuple:
        '''
        Follow `overrides` from a declaration, most derived first.

        Return a chain of `DeclaredRecipe`.

        Raise when a cycle is found, or when an overriding recipe points to nowhere.
        '''

        chain = [declared]
        taken = {declared.directory}

        while chain[-1].manifest.overrides:
            overriding = chain[-1]
            target = SourceId.parse(overriding.manifest.overrides)
            layer, base, revisited = self.probe(
                stack, target, layer, overriding.directory, taken
            )

            if revisited is not None:
                self.refuse_a_cycle(chain, revisited)

            if base is None:
                self.refuse_a_missing_override(overriding, target, chain)

            chain.append(base)
            taken.add(base.directory)

        return tuple(chain)

    @staticmethod
    def require_an_answer(recipe):
        '''Refuse a recipe that doesn't hold anything.'''

        # A recipe directory named right and holding nothing is an error case.
        if recipe:
            return

        raise RuntimeError(
            "ERROR: {} holds no project file ({}) and names no locator:\n"
            "  {}{}".format(
                recipe.served_by,
                project_file.PROJECT_FILE_NAMES_LISTED,
                recipe.served_by.directory,
                recipe.inherited_from(),
            )
        )

    @staticmethod
    def refuse_a_missing_override(overriding, target, chain):
        '''Refuse an `overrides` no cookbook at or below it holds.'''

        raise RuntimeError(
            "ERROR: {} overrides '{}', and no cookbook at or below it holds "
            "one.{}".format(overriding, target, recipe_module.inherited_from(chain))
        )

    @staticmethod
    def refuse_a_cycle(chain, revisited):
        '''
        Refuse an `overrides` resolving to a recipe the chain already took.
        '''

        closed_on = next(
            index
            for index, link in enumerate(chain)
            if link.directory == revisited.directory
        )
        loop = chain[closed_on:] + [revisited]

        raise RuntimeError(
            "ERROR: cycle in cookbook '{}': {}".format(
                revisited.cookbook.cache_key,
                ' -> '.join(str(link.rung) for link in loop),
            )
        )

    @staticmethod
    def report(recipe_id, recipe):
        '''Report every recipe serving an identity, and the cookbook each came from.'''

        # In the shape a resolved version is reported in.
        print("{}: served by {}".format(recipe_id, recipe.describe_chain()))

    def refuse(self, recipe_id):
        '''Report the recipe being looked for couldn't be found among the cookbooks.'''

        searched = '\n'.join(
            '  {}'.format(cookbook.source_path) for cookbook in self.cached_cookbooks
        )

        raise RuntimeError(
            "ERROR: no recipe '{}'.\nSearched {} cookbook(s):\n{}".format(
                recipe_id,
                len(self.cached_cookbooks),
                searched or '  (none)',
            )
        )
