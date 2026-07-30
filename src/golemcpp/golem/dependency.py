import subprocess
import pickle
from golemcpp.golem import helpers
from golemcpp.golem.configuration import Configuration
from golemcpp.golem.condition_expression import ConditionExpression
from golemcpp.golem.dependency_manager import get_dependency_manager
from golemcpp.golem.helpers import *
from golemcpp.golem.source import Source
from golemcpp.golem.version_resolver import VersionResolver
from collections import OrderedDict


class Dependency(Configuration):
    def __init__(self,
                 name=None,
                 repository=None,
                 directory=None,
                 version=None,
                 version_regex=None,
                 shallow=False,
                 **kwargs):
        super(Dependency, self).__init__(type='library',
                                         **kwargs)
        self.name = '' if name is None else name
        # A dependency comes from one of two mutually-exclusive sources: a git
        # `repository` (cloned) or a local `directory` (copied as-is).
        self.repository = '' if repository is None else repository
        self.directory = '' if directory is None else directory
        self.version = '' if version is None else version
        self.version_regex = '' if version_regex is None else version_regex
        self.resolved_version = ''
        self.resolved_hash = ''
        self.shallow = shallow
        self.cached_resource = None
        self.dynamically_added = False

    def __str__(self):
        return helpers.print_obj(self)

    def get_source_location(self):
        if self.directory:
            return self.directory
        return self.repository

    def to_source(self):
        # View the dependency as a Source to compute cache keys / identity the same
        # way as every other resource kind.
        if self.directory:
            return Source.for_directory(self.directory)
        return Source.for_repository(
            self.repository,
            helpers.resolved_reference(self.resolved_version, self.resolved_hash))

    def update_cached_resource(self, cache_configuration):
        '''(Re)resolve where this dependency lives in the caches.'''
        self.cached_resource = get_dependency_manager(
            cache_configuration).resolve_cached_resource(self)
        return self.cached_resource

    def get_cached_resource(self, cache_configuration):
        '''
        Where this dependency lives in the caches, resolved on first use: a
        dependency restored from a dependencies.json comes back without one (it is
        not part of serialized_members).
        '''
        if self.cached_resource is None:
            return self.update_cached_resource(cache_configuration)
        return self.cached_resource

    def update_source(self, project_dir):
        if self.directory:
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
        return [
            'name', 'repository', 'directory', 'version', 'version_regex',
            'resolved_version', 'resolved_hash', 'shallow'
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