import subprocess
import pickle
from golemcpp.golem import helpers
from golemcpp.golem.configuration import Configuration
from golemcpp.golem.condition_expression import ConditionExpression
from golemcpp.golem.helpers import *
from golemcpp.golem import requested_source
from golemcpp.golem.requested_source import RequestedSource
from golemcpp.golem.resolved_version import ResolvedVersion
from golemcpp.golem import source
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
        self.resolved = ResolvedVersion()
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

    def requested(self):
        # What this dependency asks for. The three fields stay as they are,
        # golemfile keywords and dependencies.json keys.
        if self.directory:
            return RequestedSource.for_directory(self.directory)
        return RequestedSource.for_repository(
            self.repository, version=self.version,
            version_regex=self.version_regex)

    def update_source(self, project_dir):
        # Also the gate on a dependency read from a configuration: read_json
        # writes the members straight in, so __init__ never saw them.
        self.validate_source()
        if self.location:
            requested = RequestedSource.parse(self.location, project_dir=project_dir)
            # These two stay strings: they are golemfile keywords and
            # dependencies.json keys, so a Locator is built from them rather than
            # stored in them.
            self.directory = str(requested.locator) \
                if requested.type == source.SOURCE_TYPE_DIRECTORY else ''
            self.repository = '' if self.directory else str(requested.locator)
            self.location = ''
            self.update_version(requested.version)
        elif self.directory:
            # These two name their kind by being the field they are, so it is
            # stated rather than detected. No # version fragment.
            self.directory = str(requested_source.resolve_locator(
                self.directory, source.SOURCE_TYPE_DIRECTORY, project_dir))
        elif self.repository:
            self.repository = str(requested_source.resolve_locator(
                self.repository, source.SOURCE_TYPE_GIT, project_dir))

    def update_version(self, requested_version):
        '''
        Take the version a location named, refusing one that contradicts a version
        the dependency also declares.
        '''
        if not requested_version:
            return

        if self.version:
            raise ValueError(
                "dependency '{}' declares version '{}' and a location naming "
                "'{}'; it asks for exactly one".format(
                    self.name, self.version, requested_version))

        self.version = requested_version

    def is_non_git_directory(self):
        return bool(self.directory)

    def resolve(self):
        resolved = VersionResolver.resolve_requested(
            self.requested(), self.resolved, require_revision=True)

        # The same one back: a copied directory, or an answer already in hand.
        if resolved is self.resolved:
            return self.resolved

        if not resolved.revision:
            raise RuntimeError(
                "Bad version {} can't find any hash related".format(
                    self.version))

        self.resolved = resolved
        # The cache key is built from the resolved commit, so anything resolved
        # before this point identified a different dependency: drop it.
        self.cached_resource = None

        print("{}: {} -> {} ({})".format(self.name, self.version,
                                         resolved.reference, resolved.revision))
        return self.resolved

    def build(self, context, config):
        context.dep_command(config, self, 'build', False)

    def configure(self, context, config):
        context.dep_command(config, self, 'resolve', False)

    RESOLVED_MEMBER = 'resolved'

    @staticmethod
    def serialized_members():
        # `location` is read from a configuration but never written back:
        # update_source resolves it into `repository` or `directory` and clears it.
        return [
            'name', 'repository', 'directory', 'location', 'version',
            'version_regex', 'resolved', 'shallow'
        ]

    @staticmethod
    def serialize_to_json(o, avoid_lists=False):
        json_obj = Configuration.serialize_to_json(o, avoid_lists=avoid_lists)

        for key in o.__dict__:
            if key in Dependency.serialized_members():
                if o.__dict__[key]:
                    json_obj[key] = o.__dict__[key]

        if o.resolved:
            json_obj[Dependency.RESOLVED_MEMBER] = o.resolved.to_dict()

        return json_obj

    def read_json(self, o):
        Configuration.read_json(self, o)

        for key, value in o.items():
            if key in Dependency.serialized_members():
                self.__dict__[key] = value

        if Dependency.RESOLVED_MEMBER in o:
            self.resolved = ResolvedVersion.from_dict(
                o[Dependency.RESOLVED_MEMBER])

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