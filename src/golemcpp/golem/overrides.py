'''
The overrides configuration: dependency patches applied to a project's
dependencies before they resolve, so a whole dependency tree can be forced onto
one version or one variant.

An overlay carries one at its root under `OVERRIDES_FILENAME`, and several
overlays are layered into one by merge_overrides. This module owns the format
and the layering; where the files come from is the Context's business.
'''

import json
import os
from collections import OrderedDict

from golemcpp.golem import helpers
from golemcpp.golem.dependency import Dependency


# What an overlay carries at its root, and the name the layered result is
# written under.
OVERRIDES_FILENAME = 'overrides.json'

# The members an override writes onto the dependency it matches. The others it
# carries say which dependency is meant, not what to change about it.
OVERRIDDEN_MEMBERS = (
    'version',
    'resolved',
    'shallow',
    'link',
    'variant',
    'runtime_link',
    'runtime_variant',
)


def read_overrides(path, project_dir):
    '''
    The overrides a configuration file carries, each naming the source it
    overrides the way a project file names one.
    '''
    with open(path, 'r') as fp:
        entries = json.load(fp)

    overrides = []
    for entry in entries:
        override = Dependency.unserialize_from_json(entry)
        # An override names its source the way a project file does, so a
        # `location` resolves and a relative path lands on the project.
        override.update_source(project_dir)
        overrides.append(override)

    return overrides


def write_overrides(overrides, path):
    '''Record overrides at `path`, returned so a caller can point at the result.'''
    helpers.make_directory(os.path.dirname(path))
    with open(path, 'w') as fp:
        json.dump([Dependency.serialize_to_json(override) for override in overrides],
                  fp, indent=4)

    return path


def merge_overrides(contributions):
    '''
    One override list out of several, layered in the order they are given. An
    entry is identified by the source it overrides, and each layer writes only
    the members it actually sets, so a later one refines an earlier one instead
    of replacing it.
    '''
    # Layered as serialized entries: serialization already drops the members an
    # override leaves unset, which is what makes each one a sparse patch.
    merged = OrderedDict()
    for overrides in contributions:
        for override in overrides:
            merged.setdefault(override.get_source_location(), {}).update(
                Dependency.serialize_to_json(override))

    return [Dependency.unserialize_from_json(entry) for entry in merged.values()]


def apply_overrides(overrides, dependencies):
    '''
    Write each override onto the dependency coming from the same source. A
    dependency no override names keeps what it declares, and only the members an
    override sets are written, so it patches a dependency rather than replacing
    it.
    '''
    for dependency in dependencies:
        for override in overrides:
            if dependency.get_source_location() != override.get_source_location():
                continue

            for member in OVERRIDDEN_MEMBERS:
                value = getattr(override, member)
                if value:
                    setattr(dependency, member, value)
            break
