'''
Where a resource was asked to come from, before anything was resolved.

A RequestedSource always has a locator.

`source_location` reads a configured location and answers with either a locator
or an identity. An identity says which source is wanted without saying where it
is, therefore only a locator becomes a RequestedSource.

A Source is what resolving one produces. Only a Source can name a commit, and
only a Source has an identity in a cache.
'''

from dataclasses import dataclass, field

from golemcpp.golem import source
from golemcpp.golem import source_location
from golemcpp.golem.locator import Locator
from golemcpp.golem.source import Source

@dataclass(frozen=True)
class RequestedSource:
    # `locator` is where the source is, settled. `version` is what was asked of
    # it, empty when the location named nothing.
    locator: Locator = field(default_factory=Locator)
    version: str = ''
    type: str = source.SOURCE_TYPE_GIT
    # Which tags `version` may be matched against, when a repository names them
    # in a way a version range cannot be read from directly. It is a golemfile
    # keyword only for now.
    version_regex: str = ''

    # As on Source: the named constructors take either a Locator or the string
    # spelling one, the field takes only a Locator.

    @classmethod
    def for_repository(cls, locator, version='', version_regex=''):
        return cls(locator=Locator(str(locator)), version=version,
                   type=source.SOURCE_TYPE_GIT, version_regex=version_regex)

    @classmethod
    def for_directory(cls, locator):
        # A copied directory is whatever it holds now: there is no version of it
        # to ask for.
        return cls(locator=Locator(str(locator)), version='',
                   type=source.SOURCE_TYPE_DIRECTORY)

    @classmethod
    def parse(cls, location, project_dir):
        '''
        The RequestedSource a configured location denotes:
        `[<kind>+]<locator>[#<version>]`.

        Refuses the shape naming an identity, since a RequestedSource always has
        a locator. A dependency reads its location through `source_location`
        instead, which answers either shape.
        '''
        settled = source_location.parse(location, project_directory=project_dir)

        return cls(locator=settled.locator, version=settled.version,
                   type=settled.kind)

    def get_id(self):
        '''Make the identity of the source itself, whatever version is asked of it.'''
        return self.locator.get_id()

    def resolved_at(self, resolved) -> Source:
        '''
        This source as the resolved one it becomes, at the version resolving it
        landed on.
        '''
        return Source(locator=self.locator, resolved=resolved, type=self.type)


def parse_location(value, context):
    '''A location setting into the RequestedSource it denotes.'''
    return RequestedSource.parse(value, project_dir=context.project_dir)


def format_location(requested, context):
    '''
    The way a RequestedSource is spelled back into a setting, the reverse of
    parse_location.

    Always explicit about the kind. What is written is never re-detected.

    The version is written only when one was asked for.
    '''
    spelled = requested.type + source_location.KIND_SEPARATOR + str(requested.locator)

    if not requested.version:
        return spelled

    return spelled + source_location.VERSION_SEPARATOR + requested.version
