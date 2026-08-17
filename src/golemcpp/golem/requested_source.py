'''
Where a resource was asked to come from, before anything was resolved.

A configured location says three things: which kind of source it is, where that
source is, and which version of it is wanted: `[<kind>+]<locator>[#<version>]`.
The first two are known as soon as the location is read; the third is a request,
which may be a semver spec matching no tag that exists yet.

That is what separates this from a Source: a RequestedSource is what a
configuration spells, a Source is what resolving one produces. Only the second
can name a commit, and only the second identifies anything in a cache.
'''

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from golemcpp.golem import locator as locator_module
from golemcpp.golem import source
from golemcpp.golem.locator import Locator
from golemcpp.golem.source import Source


# A configured location may spell its kind: `<kind>+<locator>`.
KIND_SEPARATOR = '+'

# A configured location may name the version to obtain: `<locator>#<version>`.
VERSION_SEPARATOR = '#'

# A leading bare word followed by the separator claims a kind. Kept narrow so a
# real locator never matches: a URL has `:` after its scheme, a path has none.
KIND_CLAIM = re.compile(r'^([a-z][a-z0-9]*)\{}'.format(KIND_SEPARATOR))


def split_kind(location):
    '''
    Extracts the explicit kind found on a location, if any. And returns
    what remains of the location.    

    Finding an unkonwn kind raises an error.
    '''
    match = KIND_CLAIM.match(location)
    if not match:
        return None, location

    kind = match.group(1)
    if kind not in source.SOURCE_KINDS:
        raise ValueError("unknown source kind '{}': expected {}".format(
            kind, ', '.join(name + KIND_SEPARATOR for name in source.SOURCE_KINDS)))

    return kind, location[match.end():]


def split_version(location):
    '''The locator and the version behind the first separator, if any.'''
    location, _, version = location.partition(VERSION_SEPARATOR)
    return location, version


def make_locator(locator, project_directory=None) -> Locator:
    '''
    Makes a Locator from the raw locator string.

    A path is the only shape relative to anything, so it is the only one
    resolved against the project it was configured in, into an absolute
    `file://` URL.
    
    Everything else git accepts is kept exactly as it was written.
    '''
    if not locator_module.is_bare_path(locator):
        return Locator(locator)

    locator_path = locator

    if project_directory:
        locator_path = os.path.join(project_directory, locator)

    return Locator(Path(os.path.realpath(locator_path)).as_uri())


def detect_kind(locator: Locator):
    '''Detects the kind from the locator's content.'''
    if not locator.is_existing_directory():
        return source.SOURCE_TYPE_GIT
    if locator.is_git_repository():
        return source.SOURCE_TYPE_GIT
    return source.SOURCE_TYPE_DIRECTORY


def is_path_locator_valid(locator: Locator, kind):
    '''Is the path locator valid for the given kind?'''

    # If it is a directory, there is no version to expect, it is valid.
    
    if kind == source.SOURCE_TYPE_DIRECTORY:
        # A copied directory has no version to ask for, so `#` can only be part
        # of the name, whether that directory is there yet or not.
        return True

    # If it is a repository, we must find an existing repository.

    if kind == source.SOURCE_TYPE_GIT:
        return locator.is_git_repository()

    # If the kind is unknown, we must find at least an existing directory. 

    return locator.is_existing_directory()


def validate_locator_kind(locator: Locator, kind):
    '''
    Refuses a locator the kind asked of it cannot be.
    '''
    if kind != source.SOURCE_TYPE_GIT:
        return

    if locator.is_existing_directory() and not locator.is_git_repository():
        raise ValueError(
            "'{}' is not a repository git can clone from, and a git location "
            "must name one".format(locator))


def resolve_locator(locator, kind, project_directory) -> Locator:
    '''
    Validates the locator corresponds to the kind and returns a resolved Locator.
    '''
    locator = make_locator(locator, project_directory)
    validate_locator_kind(locator, kind)
    return locator


def resolve_location(location, project_directory):
    '''
    Resolves a location into a locator, version and a kind.
    '''
    locator = None
    version = ''
    kind = source.SOURCE_TYPE_GIT

    # Extract any explicit kind defined

    kind, processed_location = split_kind(location)

    # If the location is a local path, assume it doesn't contain any version
    # fragment and see if it is valid.
    
    if locator_module.is_bare_path(processed_location):
        candidate_locator = make_locator(processed_location, project_directory)
        if is_path_locator_valid(candidate_locator, kind):
            locator = candidate_locator

    # Otherwise, let's assume there could be a version and extract it, whether
    # it is referring to a valid location or not.

    if locator is None:
        processed_location, version = split_version(processed_location)
        locator = make_locator(processed_location, project_directory)

    # Settle the kind

    kind = kind or detect_kind(locator)

    # If kind asks for a directory, check no version is asked.

    if kind == source.SOURCE_TYPE_DIRECTORY and version:
        raise ValueError(
            "location '{}' asks for version '{}' of a directory, but a copied "
            "directory is whatever it holds now".format(locator, version))

    # If kind asks for a repository, check the locator is one.

    validate_locator_kind(locator, kind)

    return locator, version, kind


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
        '''
        locator, version, kind = resolve_location(location, project_directory=project_dir)
        return cls(locator=locator, version=version, type=kind)

    def get_id(self):
        '''What identifies the source itself, whatever version is asked of it.'''
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
    spelled = requested.type + KIND_SEPARATOR + str(requested.locator)

    if not requested.version:
        return spelled

    return spelled + VERSION_SEPARATOR + requested.version
