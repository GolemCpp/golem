import subprocess
import pickle
from golemcpp.golem import helpers
from golemcpp.golem.configuration import Configuration
from golemcpp.golem.condition_expression import ConditionExpression
from golemcpp.golem.helpers import *
from golemcpp.golem import source_location
from golemcpp.golem.locator import Locator
from golemcpp.golem.requested_source import RequestedSource
from golemcpp.golem.dependency_resolution import DependencyResolution
from golemcpp.golem import source
from golemcpp.golem.version import Version
from golemcpp.golem import version_resolver
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
        # A dependency comes from one of three mutually-exclusive sources: a
        # git `repository` (cloned), a local `directory` (copied as-is), or a
        # `location` naming either in one field, spelling its kind or leaving
        # it to detection.
        self.location = '' if location is None else location
        self.repository = '' if repository is None else repository
        self.directory = '' if directory is None else directory
        self.validate_source()
        self.version = '' if version is None else version
        self.version_regex = '' if version_regex is None else version_regex
        self.resolved = DependencyResolution()
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
                "exactly one".format(self.name, ', '.join(declared))
            )

    def get_source_location(self):
        # Where this dependency was found to come from.
        # Normalized, so two spellings of one place are one key.
        return self.resolved.locator

    def requested_source(self):
        # What this dependency asks for. The locator is the resolved one: a
        # declaration may be relative, or an identity naming no locator at all.
        if not self.resolved.locator:
            raise ValueError(
                "dependency '{}' has no settled source yet: a declaration has "
                "to be resolved against a project first, and an identity "
                "through a cookbook".format(self.name)
            )

        is_directory = self.resolved.kind == source.SOURCE_TYPE_DIRECTORY

        return RequestedSource(
            locator=Locator(self.resolved.locator),
            # A copied directory is whatever it holds now, so there is no
            # version of it to ask for.
            version='' if is_directory else self.version,
            type=self.resolved.kind,
            version_regex=self.version_regex,
        )

    def resolved_version(self):
        return self.resolved.version

    def update_source(self, project_dir, identity_allowed=False):
        # Also the gate on a dependency read from a configuration: read_json
        # writes the members straight in, so __init__ never saw them.
        #
        # `identity_allowed` is false unless a caller says otherwise: an
        # override entry arrives through here too and aren't supporting this.
        self.validate_source()
        if self.location:
            settled = source_location.parse(
                self.location,
                project_directory=project_dir,
                identity_allowed=identity_allowed,
            )

            self.update_version(settled.version)

            if settled.names_an_identity:
                # An identity says which source is wanted without saying where
                # it is, so the cookbook lookup settles both fields below.
                return

            self.resolved = self.resolved.settle_locator(
                str(settled.locator), settled.kind
            )
        elif self.directory:
            # These two name their kind by being the field they are, so it is
            # stated rather than detected. No # version fragment.
            self.resolved = self.resolved.settle_locator(
                str(
                    source_location.resolve_locator(
                        self.directory, source.SOURCE_TYPE_DIRECTORY, project_dir
                    )
                ),
                source.SOURCE_TYPE_DIRECTORY,
            )
        elif self.repository:
            self.resolved = self.resolved.settle_locator(
                str(
                    source_location.resolve_locator(
                        self.repository, source.SOURCE_TYPE_GIT, project_dir
                    )
                ),
                source.SOURCE_TYPE_GIT,
            )

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
                    self.name, self.version, requested_version
                )
            )

        self.version = requested_version

    def is_non_git_directory(self):
        return self.resolved.kind == source.SOURCE_TYPE_DIRECTORY

    def resolve(self):
        resolved = VersionResolver.resolve_requested(
            self.requested_source(), self.resolved.version, require_revision=True
        )

        # The same one back: a copied directory, or an answer already in hand.
        if resolved is self.resolved.version:
            return self.resolved.version

        # Settled onto what reading the location already worked out, rather
        # than over it.
        self.resolved = self.resolved.settle_version(resolved)
        # The cache key is built from the resolved commit, so anything resolved
        # before this point identified a different dependency: drop it.
        self.cached_resource = None

        version_resolver.report_resolution(self.name, self.version, resolved)
        return self.resolved.version

    def build(self, context, config):
        context.dep_command(config, self, 'build', False)

    def configure(self, context, config):
        context.dep_command(config, self, 'resolve', False)

    RESOLVED_MEMBER = 'resolved'

    @staticmethod
    def serialized_members():
        # The first four are what a golemfile declared, kept as it wrote them.
        # What Golem worked out about them sits in `resolved`.
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
            self.resolved = DependencyResolution.from_dict(
                o[Dependency.RESOLVED_MEMBER]
            )

            # A resolution names the commit it landed on, and everything reading
            # one downstream takes it for a commit: the cache root is named after
            # it, and the fetch resets onto it without interpreting it. A name
            # written here would reach git as a revision it reads its own way.
            revision = self.resolved.version.revision
            if revision and not Version.parse_git_hash(revision):
                raise RuntimeError(
                    "dependency '{}' records '{}' as its revision, which names "
                    "no commit; write the version asked for as `version` "
                    "instead".format(self.name, revision)
                )

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
