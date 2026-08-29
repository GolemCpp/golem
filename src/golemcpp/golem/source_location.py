"""
What a configured location spells, before anything is resolved.

A location takes one of two shapes:

    [<kind>+]<locator>[#<version>]
    <identity>[#<version>]

The first says where a source is, so its kind is settled as it is read.

The second names an identity, which stands for a source without saying where it
is. What resolves it decides that, therefore the location carries no kind and no
locator: both arrive with the lookup.

For now, only a recipe is what resolves an identity, making it a sort of pacakge ID.
"""

import os
import re
from dataclasses import dataclass
from pathlib import Path

from golemcpp.golem import locator as locator_module
from golemcpp.golem import safe_part
from golemcpp.golem import source
from golemcpp.golem import source_id
from golemcpp.golem.locator import Locator
from golemcpp.golem.source_id import SourceId


@dataclass(frozen=True)
class SourceLocation:
    """One configured location, read."""

    # Exactly one of these says which source is wanted. `locator` is what git
    # is handed; `identity` stands for one until something resolves it.
    locator: Locator = None
    identity: SourceId = None
    # Empty for an identity, since nothing is there to detect a kind from.
    kind: str = ""
    # What was asked of the source, which may match no tag that exists yet.
    version: str = ""

    @classmethod
    def for_identity(cls, identity: SourceId, version: str = ""):
        return cls(identity=identity, version=version)

    @classmethod
    def for_locator(cls, locator: Locator, kind: str, version: str = ""):
        return cls(locator=locator, kind=kind, version=version)

    @property
    def names_an_identity(self) -> bool:
        """Does this location name a source indirectly, rather than say where it is?"""

        return self.identity is not None


# A configured location may spell its kind: `<kind>+<locator>`.
KIND_SEPARATOR = "+"

# A configured location may name the version to obtain: `<locator>#<version>`,
# the same separator a cache key uses between an identity and its version.
VERSION_SEPARATOR = safe_part.VERSION_SEPARATOR

# A leading bare word followed by the separator claims a kind. Kept narrow so a
# real locator never matches: a URL has `:` after its scheme, a path has none.
KIND_CLAIM = re.compile(r"^([a-z][a-z0-9]*)\{}".format(KIND_SEPARATOR))


def split_kind(location):
    """
    Extracts the explicit kind found on a location, if any. And returns
    what remains of the location.

    Finding an unkonwn kind raises an error.
    """
    match = KIND_CLAIM.match(location)
    if not match:
        return None, location

    kind = match.group(1)
    if kind not in source.SOURCE_KINDS:
        raise ValueError(
            "unknown source kind '{}': expected {}".format(
                kind, ", ".join(name + KIND_SEPARATOR for name in source.SOURCE_KINDS)
            )
        )

    return kind, location[match.end() :]


def split_version(location):
    """The locator and the version behind the first separator, if any."""
    location, _, version = location.partition(VERSION_SEPARATOR)
    return location, version


def make_locator(locator, project_directory=None) -> Locator:
    """
    Makes a Locator from the raw locator string.

    A path is the only shape relative to anything, so it is the only one
    resolved against the project it was configured in, into an absolute
    `file://` URL.

    Everything else git accepts is kept exactly as it was written.
    """
    if not locator_module.is_bare_path(locator):
        return Locator(locator)

    locator_path = locator

    if project_directory:
        locator_path = os.path.join(project_directory, locator)

    return Locator(Path(os.path.realpath(locator_path)).as_uri())


def detect_kind(locator: Locator):
    """Detects the kind from the locator's content."""
    if not locator.is_existing_directory():
        return source.SOURCE_TYPE_GIT
    if locator.is_git_repository():
        return source.SOURCE_TYPE_GIT
    return source.SOURCE_TYPE_DIRECTORY


def is_path_locator_valid(locator: Locator, kind):
    """Is the path locator valid for the given kind?"""

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
    """
    Refuses a locator the kind asked of it cannot be.
    """
    if kind != source.SOURCE_TYPE_GIT:
        return

    if locator.is_existing_directory() and not locator.is_git_repository():
        raise ValueError(
            "'{}' is not a repository git can clone from, and a git location "
            "must name one".format(locator)
        )


def resolve_locator(locator, kind, project_directory) -> Locator:
    """
    Validates the locator corresponds to the kind and returns a resolved Locator.
    """
    refuse_an_identity(locator)
    locator = make_locator(locator, project_directory)
    validate_locator_kind(locator, kind)
    return locator


def names_an_identity(value) -> bool:
    """Does a location name an identity rather than say where it is?"""
    # The leading `@` is what selects the shape, so a directory named `@foo` is
    # written `./@foo`, the escape git already forces for a `:`.
    return value.startswith(source_id.FIELD_SEPARATOR)


def refuse_an_identity(value):
    """Refuse an identity in a field taking a locator."""

    if not names_an_identity(value):
        return

    raise ValueError(
        "'{}' is an identity, and this field takes where a source is. Write it "
        "as `location`, or './{}' for a directory of that name.".format(value, value)
    )


def resolve_identity(processed_location, kind) -> "SourceLocation":
    """
    Read a location naming an identity, and the version asked of it.

    Nothing else about it is known here. E.g. a recipe settles what is the source of the
    package the identity is referring to, and therefore what kind of source it turns out
    to be.
    """
    if kind:
        raise ValueError(
            "location '{}{}{}' spells a kind on an identity, but only the source it "
            "refers to can settle this (e.g. a recipe)".format(
                kind, KIND_SEPARATOR, processed_location
            )
        )

    identity, version = split_version(processed_location)

    # Read rather than kept as text: reading folds case and drops a trailing
    # empty field, so one identity has one spelling everywhere below.
    return SourceLocation.for_identity(SourceId.parse(identity), version)


def parse(location, project_directory, identity_allowed=False) -> "SourceLocation":
    """
    Read a location into what it names, whether that is a source or an identity
    referring to a source.

    `identity_allowed` is false unless a caller says otherwise. A cookbook, an
    overlay and an override are not resolved out of an identity today, therefore
    only a dependency reads one.
    """

    locator = None
    version = ""
    kind = source.SOURCE_TYPE_GIT

    # Extract any explicit kind defined

    kind, processed_location = split_kind(location)

    # A location names an identity or says where a source is, and the leading `@`
    # is what tells them apart. Asked before the path test.

    if names_an_identity(processed_location):
        if not identity_allowed:
            raise ValueError(
                "location '{}' names an identity, and only a dependency's source "
                "may be one".format(location)
            )

        return resolve_identity(processed_location, kind)

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
            "directory is whatever it holds now".format(locator, version)
        )

    # If kind asks for a repository, check the locator is one.

    validate_locator_kind(locator, kind)

    return SourceLocation.for_locator(locator, kind=kind, version=version)
