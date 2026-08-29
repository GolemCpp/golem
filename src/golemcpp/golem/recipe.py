'''
The recipe serving an identity, resolved from what the cookbooks declare.

A lookup returns one of these rather than a directory, because what a caller needs can
differs. E.g. where the source is, or how to build it.

Resoved once to allow asking for anything afterwards.

It's a lazy view over one or more cookbooks, because it can hold a chain of overriding
recipes. In such case, each declared recipe in the chain can be considered as a delta
holding an answer to a query. The most derived recipe holding the answer always wins.
'''

from dataclasses import dataclass

from golemcpp.golem import project_file
from golemcpp.golem.source_id import SourceId


@dataclass(frozen=True)
class Recipe:
    '''
    What the declarations serving an identity hold, together.

    What's declared in the most derived declaration always win:
    - A field from the manifest (`locator`, `mirrors`)
    - The project file

    Fields from the manifest are independant and can be overriden individually.
    '''

    # Most derived first, the way the cookbooks were searched.
    chain: tuple = ()

    @classmethod
    def resolve(cls, declared):
        '''Make the recipe one declaration answers with.'''
        return cls(chain=(declared,))

    @property
    def served_by(self):
        '''The declaration answering the lookup.'''
        return self.chain[0]

    @property
    def locator(self) -> str:
        '''
        The default locator to clone, empty when no declaration names one.

        A recipe declaring only mirrors has none. A mirror is a convenience and
        never stands in for it.
        '''

        return first(declaration.locator for declaration in self.chain)

    @property
    def mirrors(self) -> tuple:
        '''The other locators the source is reachable at.'''
        return first((declaration.mirrors for declaration in self.chain), default=())

    @property
    def locators(self) -> tuple:
        '''Every locator the recipe names, the default one first.'''
        return tuple(locator for locator in (self.locator,) + self.mirrors if locator)

    def locator_for(self, identity) -> str:
        '''
        Where to clone the source, empty when matching nothing the recipe names.

        `locator` serves every identity it does not contradict. This is what makes it
        the default locator.

        `mirrors` serve the identity naming one exactly.

        An identity naming the recipe exactly reaches the default locator and no mirror.
        '''
        if self.locator and agrees_with(identity, self.locator):
            return self.locator

        for mirror in self.mirrors:
            if identity == SourceId.from_locator(mirror):
                return mirror

        return ''

    @property
    def project_directory(self) -> str:
        '''Where the project file is, empty when no declaration holds one.'''
        return first(declaration.project_directory for declaration in self.chain)

    def __bool__(self) -> bool:
        '''Does this recipe answer anything a caller can use?'''
        return bool(self.locators or self.project_directory)

    def describe_chain(self) -> str:
        '''Name every declaration this recipe was made of, most derived first.'''
        return describe_chain(self.chain)

    def inherited_from(self) -> str:
        '''Name the chain for a refusal, empty when one declaration made it.'''
        return inherited_from(self.chain)

    def require_locators(self) -> tuple:
        '''
        Return every locator the recipe names, refusing one that names none.

        Asked by a caller pointed at an identity, which has nothing else to
        clone from.
        '''

        if self.locators:
            return self.locators

        raise RuntimeError(
            "ERROR: {} names no locator, therefore '{}' cannot be used as a "
            "location:\n  {}{}".format(
                self.served_by,
                self.served_by.rung,
                self.served_by.directory,
                self.inherited_from(),
            )
        )

    def require_project_directory(self) -> str:
        '''
        Return where the project file is, refusing a recipe that holds none.

        Asked by a project with no golemfile of its own, which has nothing else
        to build from.
        '''
        if self.project_directory:
            return self.project_directory

        raise RuntimeError(
            "ERROR: {} holds no project file ({}):\n  {}{}".format(
                self.served_by,
                project_file.PROJECT_FILE_NAMES_LISTED,
                self.served_by.directory,
                self.inherited_from(),
            )
        )


def describe_chain(chain) -> str:
    '''Name every declaration in a chain, most derived first.'''
    return ' -> '.join(
        '{} ({})'.format(declaration.rung, declaration.cookbook.cache_key)
        for declaration in chain
    )


def inherited_from(chain) -> str:
    '''
    Name a chain for a refusal, empty when one declaration makes it.
    '''
    if len(chain) < 2:
        return ''

    return '\nInherited through {}'.format(describe_chain(chain))


def first(values, default=''):
    '''The first value holding something, `default` when none does.'''
    return next((value for value in values if value), default)


def agrees_with(identity, locator) -> bool:
    '''Does the identity say something contradictory to the locator?'''
    # Filling the blanks on the identity to test if it gives back the same identity as
    # what the locator translates to.
    composed = SourceId.from_locator(locator)

    return identity.filled_from(composed) == composed
