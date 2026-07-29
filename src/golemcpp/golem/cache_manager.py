import hashlib
import os
import re
from dataclasses import dataclass

from golemcpp.golem.cache_resolution_policy import CacheResolutionPolicy
from golemcpp.golem import cache_configuration
from golemcpp.golem import resource_manifest
from golemcpp.golem import helpers
from golemcpp.golem.resource_manifest import ResourceManifest
from golemcpp.golem.source import Source


# Reported kind for a resource that has neither a manifest nor a known
# subdirectory to infer from (e.g. a legacy flat entry stored at the cache root
# before the per-kind subdirectory layout existed).
UNKNOWN_KIND = 'unknown'


@dataclass
class CachedResource:
    path: str
    cache_location: str
    is_read_only: bool
    subdir: str
    cache_key: str
    size_bytes: int
    manifest: object = None  # resource_manifest.ResourceManifest | None

    @property
    def is_identified(self) -> bool:
        return self.manifest is not None

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

    def resolve_cache_directory(self, spec):
        '''
        Resolves the CacheDirectory corresponding to the resource and all the cache settings.
        '''
        identifier = spec.location
        exists_in_cache = lambda cache_directory: self.is_resource_in_cache_directory(cache_directory, spec)

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

    def get_resource_location(self, cache_directory, spec) -> str:
        '''
        When minimization is disabled the classic "<cache_root>/<subdir>/<cache_key>" 
        layout is used.
        
        When minimization is enabled a pre-existing classic location keeps priority 
        (so caches populated before minimization stay usable); otherwise the resource 
        is stored flat at "<cache_root>/<hash>".
        '''
        normal_path = os.path.join(cache_directory.location, spec.subdir, spec.cache_key)
        if not self.minimization_enabled:
            return normal_path
        if os.path.exists(normal_path):
            return normal_path
        return os.path.join(
            cache_directory.location,
            self.make_minimized_resource_name(spec, self.minimization_length))

    def is_resource_in_cache_directory(self, cache_directory, spec) -> bool:
        '''
        Whether a resource root already exists in a given cache directory.
        '''
        return os.path.exists(self.get_resource_location(cache_directory, spec))

    def make_minimized_resource_name(self, spec, length):
        '''
        Short flat directory name for a minimized resource.
        
        Hashing "<subdir>/<cache_key>" keeps names unique across resource kinds once 
        the per-kind subdirectory is dropped.
        '''
        digest = hashlib.sha1('{}/{}'.format(spec.subdir, spec.cache_key).encode('utf-8')).hexdigest()
        return digest[:length]

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
    def read_manifest(cache_root: str):
        return ResourceManifest.read_from_root(cache_root)

    @staticmethod
    def read_manifest_source(cache_root: str):
        '''The Source recorded in a resource's manifest, or None if unidentified.'''
        manifest = ResourceManifest.read_from_root(cache_root)
        if manifest is None:
            return None
        return Source.from_manifest(manifest)

    @staticmethod
    def write_manifest(cache_root: str, spec) -> None:
        resource_manifest.write_manifest(
            resource_root=cache_root,
            kind=spec.kind,
            cache_key=spec.cache_key,
            source=spec.source.to_dict())

    @staticmethod
    def touch_last_used(cache_root: str) -> None:
        resource_manifest.touch_last_used(cache_root)

    # -- per-resource mutations -------------------------------------------

    def staged_install(self, cache_directory, spec, populate) -> str:
        '''
        Build a resource into a sibling `.tmp` staging directory, drop its
        manifest, then atomically swap it into place. `populate(staging_root)`
        fills the staging directory with the resource's contents.
        '''
        cache_root = self.get_resource_location(cache_directory, spec)
        staging_root = cache_root + '.tmp'

        helpers.remove_tree(staging_root)
        os.makedirs(staging_root, exist_ok=True)
        try:
            populate(staging_root)
            self.write_manifest(staging_root, spec)
            helpers.remove_tree(cache_root)
            os.makedirs(os.path.dirname(cache_root), exist_ok=True)
            os.replace(staging_root, cache_root)
        finally:
            helpers.remove_tree(staging_root)

        return cache_root

    def remove(self, cache_directory, spec) -> bool:
        '''Remove a resource root, honoring the read-only guard. Returns whether it was removed.'''
        cache_root = self.get_resource_location(cache_directory, spec)
        if cache_directory.is_read_only or not os.path.isdir(cache_root):
            return False
        helpers.remove_tree(cache_root)
        return True

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

    def _make_resource(self, cache_directory, subdir, entry, entry_path,
                       compute_size):
        # The manifest is the source of truth for a resource's identity,
        # wherever it lives: an entry with a valid manifest is identified (by its
        # own kind and cache_key), one without stays unidentified. Storage layout
        # (classic subdir vs minimized flat) is not the resource's concern.
        manifest = ResourceManifest.read_from_root(entry_path)
        size = helpers.get_tree_size(entry_path) if compute_size else 0

        return CachedResource(
            path=entry_path,
            cache_location=cache_directory.location,
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

                    resources.append(self._make_resource(
                        cache_directory, subdir, entry, entry_path, compute_size))

            if not os.path.isdir(cache_directory.location):
                continue

            for entry in sorted(os.listdir(cache_directory.location)):
                if entry in cache_configuration.RESOURCE_SUBDIRS:
                    continue

                entry_path = os.path.join(cache_directory.location, entry)
                if not os.path.isdir(entry_path):
                    continue

                resources.append(self._make_resource(
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
        them.
        '''
        removed = []
        skipped_read_only = []
        for resource in resources:
            if resource.is_read_only:
                skipped_read_only.append(resource)
                continue
            helpers.remove_tree(resource.path)
            removed.append(resource)
        return removed, skipped_read_only


def get_cache_manager(cache_configuration) -> CacheManager:
    '''The single factory for a CacheManager over a resolved configuration.'''
    return CacheManager(cache_configuration)
