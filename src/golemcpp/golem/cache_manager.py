import os
import re
from dataclasses import dataclass

from golemcpp.golem import cache
from golemcpp.golem import cache_manifest
from golemcpp.golem import helpers


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
    manifest: object = None  # cache_manifest.ResourceManifest | None

    @property
    def is_identified(self) -> bool:
        return self.manifest is not None

    @property
    def kind(self) -> str:
        if self.manifest is not None:
            return self.manifest.kind
        inferred = cache_manifest.ResourceKind.from_subdir(self.subdir)
        return inferred.value if inferred else UNKNOWN_KIND

    @property
    def identity(self) -> dict:
        return self.manifest.identity if self.manifest else {}

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
    def __init__(self, locations):
        self.locations = locations

    def list_cache_locations(self):
        summaries = []
        for cache_dir in self.locations:
            summaries.append(CacheLocationSummary(
                location=cache_dir.location,
                is_read_only=cache_dir.is_read_only,
                regex=cache_dir.regex,
                exists=os.path.isdir(cache_dir.location)))
        return summaries

    def _make_resource(self, cache_dir, subdir, entry, entry_path,
                       compute_size, read_manifest=True):
        manifest = (cache_manifest.ResourceManifest.read_from_root(entry_path)
                    if read_manifest else None)
        size = helpers.get_tree_size(entry_path) if compute_size else 0

        return CachedResource(
            path=entry_path,
            cache_location=cache_dir.location,
            is_read_only=cache_dir.is_read_only,
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
        - Any unexpected directory sitting directly at the cache root (e.g. a
          legacy flat resource predating the subdirectory layout): always
          reported as an unidentified resource of unknown kind.
        '''
        resources = []
        for cache_dir in self.locations:
            for subdir in cache.RESOURCE_SUBDIRS:
                subdir_path = os.path.join(cache_dir.location, subdir)
                if not os.path.isdir(subdir_path):
                    continue

                for entry in sorted(os.listdir(subdir_path)):
                    entry_path = os.path.join(subdir_path, entry)
                    if not os.path.isdir(entry_path):
                        continue

                    resources.append(self._make_resource(
                        cache_dir, subdir, entry, entry_path, compute_size))

            if not os.path.isdir(cache_dir.location):
                continue

            for entry in sorted(os.listdir(cache_dir.location)):
                if entry in cache.RESOURCE_SUBDIRS:
                    continue

                entry_path = os.path.join(cache_dir.location, entry)
                if not os.path.isdir(entry_path):
                    continue

                resources.append(self._make_resource(
                    cache_dir, '', entry, entry_path, compute_size,
                    read_manifest=False))

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
