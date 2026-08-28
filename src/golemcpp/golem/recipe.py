'''
The recipe serving an identity, resolved from what the cookbooks declare.

A lookup answers with one of these rather than with a directory, because what a
caller needs can differs. E.g. where the source is, or how to build it.

Resolving once and asking afterwards is also what lets a recipe be assembled from
several declarations, which is what `overrides` will do.
'''

from dataclasses import dataclass

from golemcpp.golem import project_file
from golemcpp.golem.source_id import SourceId


@dataclass(frozen=True)
class Recipe:
    '''What the declarations answering an identity say, together.'''

    # Most derived first, the way the cookbooks were searched. One long until
    # a recipe can be a delta on another.
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
    def declaring(self):
        '''
        The declaration naming where the source is, None when none does.

        The most derived one supplies the default locator and the mirrors together,
        therefore a delta replacing a locator replaces the mirrors that came with it.
        '''

        return next(
            (declaration for declaration in self.chain if declaration.locators),
            None,
        )

    @property
    def locator(self) -> str:
        '''
        The default locator to clone, empty when the recipe declares none.

        A recipe declaring only mirrors has none. A mirror is a convenience and
        never stands in for it.
        '''

        return self.declaring.locator if self.declaring else ''

    @property
    def mirrors(self) -> tuple:
        '''The other locators the source is reachable at.'''
        return self.declaring.mirrors if self.declaring else ()

    @property
    def locators(self) -> tuple:
        '''Every locator the recipe names, the default one first.'''
        return self.declaring.locators if self.declaring else ()

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
            "location:\n  {}".format(
                self.served_by, self.served_by.rung, self.served_by.directory))

    def require_project_directory(self) -> str:
        '''
        Return where the project file is, refusing a recipe that holds none.

        Asked by a project with no golemfile of its own, which has nothing else
        to build from.
        '''
        if self.project_directory:
            return self.project_directory

        raise RuntimeError(
            "ERROR: {} holds no project file ({}):\n  {}".format(
                self.served_by,
                project_file.PROJECT_FILE_NAMES_LISTED,
                self.served_by.directory))


def first(values) -> str:
    '''The first value that says something, empty when none does.'''
    return next((value for value in values if value), '')


def agrees_with(identity, locator) -> bool:
    '''Does the identity say something contradictory to the locator?'''
    # Filling the blanks on the identity to test if it gives back the same identity as
    # what the locator translates to.
    composed = SourceId.from_locator(locator)

    return identity.filled_from(composed) == composed
