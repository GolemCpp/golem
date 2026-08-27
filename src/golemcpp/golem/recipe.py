'''
The recipe serving an identity, resolved from what the cookbooks declare.

A lookup answers with one of these rather than with a directory, because what a
caller needs can differs. E.g. where the package is, or how to build it.

Resolving once and asking afterwards is also what lets a recipe be assembled from
several declarations, which is what `overrides` will do.
'''

from dataclasses import dataclass

from golemcpp.golem import project_file


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
    def locator(self) -> str:
        '''Where the package is, empty when no declaration says.'''
        return first(declaration.locator for declaration in self.chain)

    @property
    def project_directory(self) -> str:
        '''Where the project file is, empty when no declaration holds one.'''
        return first(
            declaration.project_directory for declaration in self.chain
        )

    def __bool__(self) -> bool:
        '''Does this recipe answer anything a caller can use?'''
        return bool(self.locator or self.project_directory)

    def require_locator(self) -> str:
        '''
        Return where the package is, refusing a recipe that does not say.

        Asked by a caller pointed at an identity, which has nothing else to
        clone from.
        '''
        if self.locator:
            return self.locator

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
