import os
import re
from dataclasses import dataclass, replace

from golemcpp.golem.cache_resolution_policy import CacheResolutionPolicy
from golemcpp.golem import cache_configuration
from golemcpp.golem import cache_lock
from golemcpp.golem import resource_manifest
from golemcpp.golem import helpers
from golemcpp.golem import safe_part
from golemcpp.golem.fetched import Fetched
from golemcpp.golem.resource_manifest import ResourceManifest
from golemcpp.golem.source import Source


# Reported kind for a resource that has neither a manifest nor a known
# subdirectory to infer from (e.g. a legacy flat entry stored at the cache root
# before the per-kind subdirectory layout existed).
UNKNOWN_KIND = 'unknown'


@dataclass
class CachedResource:
    path: str
    cache_root: str
    is_read_only: bool
    subdir: str
    cache_key: str
    size_bytes: int
    manifest: object = None  # resource_manifest.ResourceManifest | None
    # The Resource this cached form was made from, when there is one. It carries
    # the information that installing has to record in a manifest.
    resource: object = None  # resource.Resource | None

    def exists(self) -> bool:
        '''
        Whether the resource root is present on disk. This is about the location
        in cache, not its content. See ResourceManager.is_installed.
        '''
        return os.path.isdir(self.path)

    @property
    def source_path(self) -> str:
        '''The fetched content under the root, which is what a consumer reads.'''
        return cache_configuration.source_path(self.path)

    @property
    def staging_path(self) -> str:
        '''Where a fresh resource is built before being swapped into place.'''
        return self.path + '.tmp'

    @property
    def lock_path(self) -> str:
        '''What a golem holds while it writes here (see cache_lock).'''
        return self.path + '.lock'

    @property
    def is_identified(self) -> bool:
        return self.manifest is not None

    @property
    def is_installed(self) -> bool:
        '''
        Does the root hold the fetched source?

        A resource is installed once the source directory is under its root,
        where exists() asks whether the root directory itself is there.
        '''
        return os.path.isdir(self.source_path)

    @property
    def kind(self) -> str:
        if self.manifest is not None:
            return self.manifest.kind
        inferred = resource_manifest.ResourceKind.from_subdir(self.subdir)
        return inferred.value if inferred else UNKNOWN_KIND

    @property
    def source(self) -> dict:
        return self.manifest.source if self.manifest else {}

    @property
    def fetched(self) -> Fetched:
        '''What the manifest says the fetch left in this root.'''
        return Fetched.from_manifest(self.manifest)

    @property
    def created_at(self) -> str:
        return self.manifest.created_at if self.manifest else ''

    @property
    def last_used_at(self) -> str:
        return self.manifest.last_used_at if self.manifest else ''

    @property
    def manifest_version(self):
        return self.manifest.version if self.manifest else None


@dataclass
class CacheLocationSummary:
    location: str
    is_read_only: bool
    regex: object  # str | None
    exists: bool


class CacheManager:
    '''
    The single way to reach the caches.
    '''

    def __init__(self, cache_configuration):
        self.cache_configuration = cache_configuration

    @property
    def locations(self):
        return self.cache_configuration.locations

    @property
    def resolution_policy(self):
        return self.cache_configuration.resolution_policy

    @property
    def minimization_enabled(self):
        return self.cache_configuration.minimization_enabled

    @property
    def minimization_length(self):
        return self.cache_configuration.minimization_length

    # -- per-resource resolution & on-disk location -----------------------

    def resolve_cache_directory(self, resource):
        '''
        Resolves the CacheDirectory corresponding to the resource and all the cache settings.
        '''
        identifier = str(resource.locator)
        exists_in_cache = lambda cache_directory: self.make_cached_resource(cache_directory, resource).exists()

        read_only_caches_with_regex = self._find_matching_caches(
            identifier,
            is_read_only=True,
            with_regex=True)
        cache_directory = self._select_cache(read_only_caches_with_regex, exists_in_cache)
        if cache_directory is not None:
            return cache_directory

        read_only_caches_without_regex = self._find_matching_caches(
            identifier,
            is_read_only=True,
            with_regex=False)
        cache_directory = self._select_cache(read_only_caches_without_regex, exists_in_cache)
        if cache_directory is not None:
            return cache_directory

        writable_caches_with_regex = self._find_matching_caches(
            identifier,
            is_read_only=False,
            with_regex=True)
        cache_directory = self._select_cache(writable_caches_with_regex, exists_in_cache)
        if cache_directory is not None:
            return cache_directory

        writable_caches_without_regex = self._find_matching_caches(
            identifier,
            is_read_only=False,
            with_regex=False)
        cache_directory = self._select_cache(writable_caches_without_regex, exists_in_cache)
        if cache_directory is not None:
            return cache_directory

        if writable_caches_with_regex:
            return writable_caches_with_regex[0]
        if writable_caches_without_regex:
            return writable_caches_without_regex[0]

        raise RuntimeError("Can't find any writable cache location")

    def _get_resource_location(self, cache_directory, resource) -> str:
        '''
        When minimization is disabled the classic "<cache_root>/<subdir>/<cache_key>" 
        layout is used.
        
        When minimization is enabled a pre-existing classic location keeps priority 
        (so caches populated before minimization stay usable); otherwise the resource 
        is stored flat at "<cache_root>/<hash>".
        '''
        normal_path = os.path.join(cache_directory.location, resource.subdir, resource.cache_key)
        if not self.minimization_enabled:
            return normal_path
        if os.path.exists(normal_path):
            return normal_path
        return os.path.join(
            cache_directory.location,
            self.make_minimized_resource_name(resource, self.minimization_length))

    def resolve_cached_resource(self, resource, compute_size=False, read_manifest=False):
        '''
        The cached form of a resource, in whichever cache directory the
        resolution settles on.
        '''
        cached_resource = self.make_cached_resource(
            self.resolve_cache_directory(resource), resource,
            compute_size=compute_size, read_manifest=read_manifest)
        self.mark_used(cached_resource)
        return cached_resource

    def mark_used(self, cached_resource) -> None:
        '''
        Resolving a resource is an attempt to use it, which is what keeps it from
        being pruned. A read-only location has no timestamp to record.
        '''
        if not cached_resource.is_read_only:
            ResourceManifest.touch(cached_resource.path)

    def make_cached_resource(self, cache_directory, resource,
                             compute_size=False, read_manifest=False):
        # Makes a cached resource from a Resource
        path = self._get_resource_location(cache_directory, resource)

        return CachedResource(
            path=path,
            cache_root=cache_directory.location,
            is_read_only=cache_directory.is_read_only,
            subdir=resource.subdir,
            cache_key=resource.cache_key,
            size_bytes=helpers.get_tree_size(path) if compute_size else 0,
            manifest=ResourceManifest.read_from_root(path) if read_manifest else None,
            resource=resource)

    def make_minimized_resource_name(self, resource, length):
        '''
        Short flat directory name for a minimized resource.
        
        Hashing "<subdir>/<cache_key>" keeps names unique across resource kinds once
        the per-kind subdirectory is dropped.
        '''
        return safe_part.digest(
            '{}/{}'.format(resource.subdir, resource.cache_key), length)

    def _find_matching_caches(self, identifier, is_read_only, with_regex):
        found_caches = []

        for cache_directory in self.locations:
            if with_regex and not cache_directory.regex:
                continue
            if not with_regex and cache_directory.regex:
                continue
            if is_read_only and not cache_directory.is_read_only:
                continue
            if with_regex:
                pattern = re.compile(cache_directory.regex)
                if not pattern.match(identifier):
                    continue
            found_caches.append(cache_directory)

        return found_caches

    def _select_cache(self, candidates, exists_in_cache):
        if not candidates:
            return None

        if self.resolution_policy == CacheResolutionPolicy.STRICT:
            return candidates[0]

        if exists_in_cache is not None:
            for cache_directory in candidates:
                if exists_in_cache(cache_directory):
                    return cache_directory

        return None

    # -- per-resource manifests -------------------------------------------

    @staticmethod
    def read_manifest_source(cached_resource):
        '''The Source recorded in a resource's manifest, or None if unidentified.'''
        manifest = ResourceManifest.read_from_root(cached_resource.path)
        if manifest is None:
            return None
        return Source.from_manifest(manifest)

    @staticmethod
    def read_manifest_fetched(cached_resource) -> Fetched:
        '''What a resource's manifest says the fetch left in its root.'''
        return Fetched.from_manifest(
            ResourceManifest.read_from_root(cached_resource.path))

    @staticmethod
    def write_manifest(cached_resource, fetched=None) -> None:
        resource = cached_resource.resource
        resource_manifest.write_manifest(
            resource_root=cached_resource.path,
            kind=resource.kind,
            cache_key=resource.cache_key,
            source=resource.source.to_dict(),
            fetched=(fetched or Fetched()).to_dict())

    def record_manifest(self, cached_resource, fetched=None) -> None:
        '''
        Keep the manifest telling the truth about what the root holds.

        What the fetch left counts as much as the source: a resource following a
        branch keeps naming the same reference while landing on a different commit
        every time it moves.
        '''
        if (self.read_manifest_source(cached_resource) != cached_resource.resource.source
                or self.read_manifest_fetched(cached_resource) != (fetched or Fetched())):
            self.write_manifest(cached_resource, fetched=fetched)

    # -- per-resource mutations -------------------------------------------

    def guard_install(self, cached_resource, populate) -> str:
        '''
        Build a resource into a sibling `.tmp` staging directory, drop its
        manifest, then atomically swap it into place.

        `populate(staging_root)` fills the staging directory with the resource's
        contents and hands back what it recorded, which the manifest keeps.

        Held against another golem throughout: the staging directory is named
        after the root, so two of these are not two installs side by side but two
        writers in one directory.
        '''
        self.check_identity(cached_resource)

        resource_root = cached_resource.path
        # The same resource, seen where it is being built rather than where it
        # will live, so its manifest is staged and swapped along with the rest.
        staging = replace(cached_resource, path=cached_resource.staging_path)

        with cache_lock.held(cached_resource.lock_path):
            helpers.remove_tree(staging.path)
            os.makedirs(staging.path, exist_ok=True)
            try:
                self.write_manifest(staging, fetched=populate(staging.path))
                helpers.remove_tree(resource_root)
                os.makedirs(os.path.dirname(resource_root), exist_ok=True)
                os.replace(staging.path, resource_root)
            finally:
                helpers.remove_tree(staging.path)

        return resource_root

    def guard_refresh(self, cached_resource, refresh) -> str:
        '''
        A refresh cannot be staged: the resource is its own working copy. The
        manifest is recorded here instead, so what the root claims never outlives
        the source it was refreshed onto.

        Which is also why it is held against another golem: there is no staging
        directory standing between two of these, only the tree both are cleaning
        and resetting.
        '''
        self.check_identity(cached_resource)

        with cache_lock.held(cached_resource.lock_path):
            self.record_manifest(cached_resource, fetched=refresh(cached_resource.path))

        # TODO: Add a try catch like guard_install to recover or trigger a fallback mechanism when it
        # fails. Ideas are: removing the source, or running a hook function to let the derived manager
        # define how to recover.

        return cached_resource.path

    @staticmethod
    def check_identity(cached_resource) -> None:
        if cached_resource.resource is None:
            raise ValueError(
                'cannot install {}: this cached resource was not made from a '
                'resource, so it has no identity to write a manifest from'.format(
                    cached_resource.path))

    # -- cache inventory --------------------------------------------------

    def list_cache_locations(self):
        summaries = []
        for cache_directory in self.locations:
            summaries.append(CacheLocationSummary(
                location=cache_directory.location,
                is_read_only=cache_directory.is_read_only,
                regex=cache_directory.regex,
                exists=os.path.isdir(cache_directory.location)))
        return summaries

    def _make_scanned_resource(self, cache_directory, subdir, entry, entry_path,
                       compute_size):
        # Makes a cached resource from a manifest living in the given path.
        # No manifest means the resource is unidentified.
        manifest = ResourceManifest.read_from_root(entry_path)
        size = helpers.get_tree_size(entry_path) if compute_size else 0

        return CachedResource(
            path=entry_path,
            cache_root=cache_directory.location,
            is_read_only=cache_directory.is_read_only,
            subdir=subdir,
            cache_key=(manifest.cache_key if manifest and manifest.cache_key else entry),
            size_bytes=size,
            manifest=manifest)

    def scan(self, compute_size=True):
        '''
        Walk every configured cache location and return one CachedResource per
        resource root. Two sources are scanned:

        - The known resource-kind subdirectories: entries without a valid
          manifest come back with manifest=None (unidentified).
        - Any directory sitting directly at the cache root: this covers both
          minimized flat resources (short hashed names, identified by their
          manifest) and legacy flat resources predating the subdirectory layout
          (no manifest, reported as unknown kind).
        '''
        resources = []
        for cache_directory in self.locations:
            for subdir in cache_configuration.RESOURCE_SUBDIRS:
                subdir_path = os.path.join(cache_directory.location, subdir)
                if not os.path.isdir(subdir_path):
                    continue

                for entry in sorted(os.listdir(subdir_path)):
                    entry_path = os.path.join(subdir_path, entry)
                    if not os.path.isdir(entry_path):
                        continue

                    resources.append(self._make_scanned_resource(
                        cache_directory, subdir, entry, entry_path, compute_size))

            if not os.path.isdir(cache_directory.location):
                continue

            for entry in sorted(os.listdir(cache_directory.location)):
                if entry in cache_configuration.RESOURCE_SUBDIRS:
                    continue

                entry_path = os.path.join(cache_directory.location, entry)
                if not os.path.isdir(entry_path):
                    continue

                resources.append(self._make_scanned_resource(
                    cache_directory, '', entry, entry_path, compute_size))

        return resources

    @staticmethod
    def select(resources, pattern, use_regex=False):
        if not pattern:
            return list(resources)

        if use_regex:
            compiled = re.compile(pattern)
            return [
                resource for resource in resources
                if compiled.search(resource.cache_key) or compiled.search(resource.path)
            ]

        return [
            resource for resource in resources
            if pattern in resource.cache_key or pattern in resource.path
        ]

    @staticmethod
    def filter_kind(resources, kind):
        if not kind:
            return list(resources)
        return [resource for resource in resources if resource.kind == kind]

    @staticmethod
    def unidentified(resources):
        return [resource for resource in resources if not resource.is_identified]

    @staticmethod
    def remove_resources(resources):
        '''
        Delete the given resource roots. Resources living in a read-only cache
        are never touched and are returned separately so the caller can report
        them. A resource that is no longer on disk is not reported as removed.
        '''
        removed = []
        skipped_read_only = []
        for resource in resources:
            if resource.is_read_only:
                skipped_read_only.append(resource)
                continue
            if not resource.exists():
                continue
            helpers.remove_tree(resource.path)
            removed.append(resource)
        return removed, skipped_read_only


def get_cache_manager(cache_configuration) -> CacheManager:
    '''The single factory for a CacheManager over a resolved configuration.'''
    return CacheManager(cache_configuration)
