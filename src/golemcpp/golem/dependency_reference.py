"""
Entries found in `deps=`.

A reference is a declared name, exactly, or a source.
"""

import os
from dataclasses import dataclass

from golemcpp.golem import source_location
from golemcpp.golem.source_id import SourceId


@dataclass(frozen=True)
class DependencyReference:
    """
    A `deps=` entry, and what reading it as a source gave.

    If the entry isn't valid, a reason is given.
    """

    # What the project file wrote. A declared name is matched against this.
    text: str
    # Which source it names, composed from a locator where it is one, and None
    # where the entry names none.
    identity: SourceId = None
    # What it asks of that source, empty where it asks for nothing.
    version: str = ""

    # What the location grammar said, where it refused the entry outright.
    refused_by: Exception = None
    # The local path the entry reads as, where nothing is there.
    missing_path: str = ""

    @property
    def names_a_source(self) -> bool:
        return self.identity is not None

    def is_asking_for_the_source(self, identity) -> bool:
        """
        Is this reference asking for the given identity?

        A reference reaches a declaration by being less qualified than it. E.g. `@boost`
        asks for `@boost@boostorg@github.com`, but `@boost@boostorg@github.com` doesn't
        ask for `@boost`.
        """
        if not self.names_a_source:
            return False

        return any(self.identity == rung for rung in identity.rungs())

    def asks_for_the_same_as(self, other) -> bool:
        """
        Do two references imply one dependency between them?

        Two references sharing the same source need to ask for the same version to
        share one implied dependency.
        """
        return self.identity == other.identity and self.version == other.version

    def explain(self) -> str:
        """Why this entry names no source, for a refusal to carry."""
        if self.refused_by is not None:
            return str(self.refused_by)

        if self.missing_path:
            return "read as a path it is '{}', which does not exist".format(
                self.missing_path
            )

        return "it names a source"


def read(text, project_directory) -> DependencyReference:
    """
    Read a `deps=` entry.
    """
    try:
        location = source_location.parse(
            text, project_directory=project_directory, identity_allowed=True
        )
    except Exception as refusal:
        return DependencyReference(text=text, refused_by=refusal)

    if location.names_an_identity:
        return DependencyReference(
            text=text, identity=location.identity, version=location.version
        )

    path = location.locator.get_local_path()

    if path is not None and not os.path.exists(path):
        return DependencyReference(text=text, missing_path=path)

    return DependencyReference(
        text=text,
        identity=SourceId.from_locator(str(location.locator)),
        version=location.version,
    )


def refuse_an_ambiguous_reference(text, matches):
    raise RuntimeError(
        "'{}' refers to {} dependencies ({}). Qualify it further, or give one "
        "of them a name".format(
            text,
            len(matches),
            ", ".join(str(dep.declared_identity()) for dep in matches),
        )
    )


def refuse_a_contradicted_version(reference, dep):
    raise RuntimeError(
        "'{}' asks for version '{}' of a dependency declared at '{}'. The "
        "versions are not matching.".format(
            reference.text, reference.version, dep.version or "no version"
        )
    )


def refuse_a_reference_naming_nothing(reference, declared_names):
    raise RuntimeError(
        "'{}' names no dependency and is not a location. The project declares "
        "{}, and reading it as a source gave: {}".format(
            reference.text, ", ".join(declared_names) or "none", reference.explain()
        )
    )


def find_dependency_referred_to(text, dependencies, project_directory):
    """
    Find the dependency a reference names, None where the project holds none.

    A declared `name` is matched first and exactly.

    Everything else is read as a source and matched by identity.

    Transitive dependencies are excluded.
    """
    declared = [dep for dep in dependencies if not dep.dynamically_added]

    for dep in declared:
        if dep.name and dep.name == text:
            return dep

    reference = read(text, project_directory)

    if not reference.names_a_source:
        return None

    matches = [dep for dep in declared if dep.is_referred_to_by(reference)]

    if len(matches) > 1:
        refuse_an_ambiguous_reference(text, matches)

    if not matches:
        return None

    # An entry naming a version of a declaration asking for another is a
    # contradiction rather than a second dependency.
    if reference.version and not matches[0].implicit:
        if reference.version != matches[0].version:
            refuse_a_contradicted_version(reference, matches[0])

    return matches[0]


def find_references_to_imply(texts, dependencies, project_directory):
    """
    Find all the references not matching to a dependency, and therefore needing to
    imply one.

    Two references sharing the same source need to ask for the same version to
    share one implied dependency.
    """
    implied = []
    declared = list(dependencies)

    for text in texts:
        if find_dependency_referred_to(text, declared, project_directory) is not None:
            continue

        reference = read(text, project_directory)

        if not reference.names_a_source:
            refuse_a_reference_naming_nothing(
                reference, [dep.name for dep in declared if dep.name]
            )

        # Check if the reference matches one previously settled as implied.
        if any(reference.asks_for_the_same_as(earlier) for earlier in implied):
            continue

        implied.append(reference)

    return implied
