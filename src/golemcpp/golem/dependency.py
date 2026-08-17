import subprocess
import pickle
from golemcpp.golem import helpers
from golemcpp.golem.configuration import Configuration
from golemcpp.golem.condition_expression import ConditionExpression
from golemcpp.golem.helpers import *
from golemcpp.golem.source import Source
from golemcpp.golem.source import SOURCE_TYPE_DIRECTORY
from golemcpp.golem.version_resolver import VersionResolver
from collections import OrderedDict


# The members naming where a dependency comes from, at most one of which a
# dependency declares.
SOURCE_MEMBERS = ('repository', 'directory', 'location')


class Dependency(Configuration):
    def __init__(self,
                 name=None,
                 repository=None,
                 directory=None,
                 location=None,
                 version=None,
                 version_regex=None,
                 shallow=False,
                 **kwargs):
        super(Dependency, self).__init__(type='library',
                                         **kwargs)
        self.name = '' if name is None else name
        # A dependency comes from one of three mutually-exclusive sources: a git
        # `repository` (cloned), a local `directory` (copied as-is), or a
        # `location` naming either in one field, spelling its kind or leaving it
        # to detection. update_source resolves a location into the two others.
        self.location = '' if location is None else location
        self.repository = '' if repository is None else repository
        self.directory = '' if directory is None else directory
        self.validate_source()
        self.version = '' if version is None else version
        self.version_regex = '' if version_regex is None else version_regex
        self.resolved_version = ''
        self.resolved_hash = ''
        self.shallow = shallow
        # Where this dependency lives in the caches, once a DependencyManager has
        # worked it out. Not part of serialized_members, so a dependency restored
        # from a dependencies.json comes back without one.
        self.cached_resource = None
        self.dynamically_added = False

    def __str__(self):
        return helpers.print_obj(self)

    def validate_source(self):
        '''
        Refuse a dependency naming its source more than once: which one wins
        would be left to the order the readers happen to test them in. Naming
        none is allowed -- a project file declares one later.
        '''
        declared = [member for member in SOURCE_MEMBERS if getattr(self, member)]
        if len(declared) > 1:
            raise ValueError(
                "dependency '{}' declares several sources ({}); it comes from "
                "exactly one".format(self.name, ', '.join(declared)))

    def get_source_location(self):
        # Falls back to `location` so a dependency is identifiable before
        # update_source has resolved which of the two fields it fills.
        if self.directory:
            return self.directory
        return self.repository or self.location

    def to_source(self):
        # View the dependency as a Source to compute cache keys / identity the same
        # way as every other resource kind.
        if self.directory:
            return Source.for_directory(self.directory)
        return Source.for_repository(
            self.repository,
            helpers.resolved_reference(self.resolved_version, self.resolved_hash))

    def update_source(self, project_dir):
        # Also the gate on a dependency read from a configuration: read_json
        # writes the members straight in, so __init__ never saw them.
        self.validate_source()
        if self.location:
            source = Source.parse(self.location, project_dir=project_dir)
            self.directory = source.location if source.type == SOURCE_TYPE_DIRECTORY else ''
            self.repository = '' if self.directory else source.location
            self.location = ''
        elif self.directory:
            self.directory = Source.normalize_url(self.directory, project_dir)
        elif self.repository:
            self.repository = Source.normalize_url(self.repository, project_dir)

    def is_non_git_directory(self):
        return bool(self.directory)

    def resolve(self):
        if self.resolved_hash:
            return self.resolved_hash

        if self.directory:
            # A copied directory has no version to resolve.
            self.resolved_version = '-'
            self.resolved_hash = '-'
        else:
            self.resolved_version, self.resolved_hash = VersionResolver.resolve(
                self.repository, self.version, self.version_regex)

        if not self.resolved_hash:
            raise RuntimeError(
                "Bad version {} can't find any hash related".format(
                    self.version))

        # The cache key is built from the resolved reference, so anything resolved
        # before this point identified a different dependency: drop it.
        self.cached_resource = None

        print("{}: {} -> {} ({})".format(self.name, self.version,
                                         self.resolved_version,
                                         self.resolved_hash))
        return self.resolved_hash

    def build(self, context, config):
        context.dep_command(config, self, 'build', False)

    def configure(self, context, config):
        context.dep_command(config, self, 'resolve', False)

    @staticmethod
    def serialized_members():
        # `location` is read from a configuration but never written back:
        # update_source resolves it into `repository` or `directory` and clears it.
        return [
            'name', 'repository', 'directory', 'location', 'version',
            'version_regex', 'resolved_version', 'resolved_hash', 'shallow'
        ]

    @staticmethod
    def serialize_to_json(o, avoid_lists=False):
        json_obj = Configuration.serialize_to_json(o, avoid_lists=avoid_lists)

        for key in o.__dict__:
            if key in Dependency.serialized_members():
                if o.__dict__[key]:
                    json_obj[key] = o.__dict__[key]

        return json_obj

    def read_json(self, o):
        Configuration.read_json(self, o)

        for key, value in o.items():
            if key in Dependency.serialized_members():
                self.__dict__[key] = value

    @staticmethod
    def unserialize_from_json(o):
        dependency = Dependency()
        dependency.read_json(o)
        return dependency

    @staticmethod
    def save_cache(dependencies):
        cache = []

        for dependency in dependencies:
            json = Dependency.serialize_to_json(dependency, avoid_lists=True)
            cache.append(json)

        return cache

    @staticmethod
    def load_cache(cache):
        dependencies = []

        for item in cache:
            dependency = Dependency.unserialize_from_json(item)
            dependencies.append(dependency)

        return dependencies