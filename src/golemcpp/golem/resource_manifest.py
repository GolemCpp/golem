import json
import os
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from datetime import timezone
from enum import Enum

from golemcpp.golem import cache_configuration
from golemcpp.golem import command_version


# Filename of the descriptor dropped at the root of every cached resource. It is
# hidden and golem-namespaced so it never collides with (and stays visually
# distinct from) the contents of a cloned repository, and it survives a
# `git reset --hard`, which does not remove untracked files.
MANIFEST_FILENAME = '.golem-manifest.json'

# Current manifest schema version. Bump this whenever the on-disk layout or the
# manifest structure changes, so future golem versions can migrate old entries.
MANIFEST_VERSION = 1


class ResourceKind(Enum):
    DEPENDENCY = 'dependency'
    COOKBOOK = 'cookbook'
    OVERLAY = 'overlay'
    TOOL = 'tool'

    @property
    def subdir(self) -> str:
        return _KIND_TO_SUBDIR[self]

    @classmethod
    def from_subdir(cls, subdir: str):
        return _SUBDIR_TO_KIND.get(subdir)


_KIND_TO_SUBDIR = {
    ResourceKind.DEPENDENCY: cache_configuration.DEPENDENCIES_SUBDIR,
    ResourceKind.COOKBOOK: cache_configuration.COOKBOOKS_SUBDIR,
    ResourceKind.OVERLAY: cache_configuration.OVERLAYS_SUBDIR,
    ResourceKind.TOOL: cache_configuration.TOOLS_SUBDIR,
}

_SUBDIR_TO_KIND = {subdir: kind for kind, subdir in _KIND_TO_SUBDIR.items()}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def manifest_path(resource_root: str) -> str:
    return os.path.join(resource_root, MANIFEST_FILENAME)


@dataclass
class ResourceManifest:
    kind: str
    cache_key: str
    # The serialized Source that produced this resource ({type, location, reference}).
    source: dict = field(default_factory=dict)
    # Holds what a fetch operation against the asked 'source' left behind.
    # Empty for a copied directory, which is not fetched at all.
    fetched: dict = field(default_factory=dict)
    version: int = MANIFEST_VERSION
    golem_version: str = ''
    created_at: str = ''
    last_used_at: str = ''

    @classmethod
    def create(cls, kind, cache_key: str, source: dict,
               fetched: dict = None) -> 'ResourceManifest':
        if isinstance(kind, ResourceKind):
            kind = kind.value
        now = utc_now()
        return cls(
            kind=kind,
            cache_key=cache_key,
            source=dict(source),
            fetched=dict(fetched or {}),
            version=MANIFEST_VERSION,
            golem_version=command_version.get_golem_version(),
            created_at=now,
            last_used_at=now,
        )

    @classmethod
    def read(cls, path: str):
        if not os.path.isfile(path):
            return None

        try:
            with open(path, 'r', encoding='utf-8') as filein:
                data = json.load(filein)
        except (ValueError, OSError):
            return None

        if not isinstance(data, dict) or 'kind' not in data:
            return None

        return cls(
            kind=data.get('kind', ''),
            cache_key=data.get('cache_key', ''),
            source=data.get('source', {}),
            fetched=data.get('fetched', {}),
            version=data.get('version', MANIFEST_VERSION),
            golem_version=data.get('golem_version', ''),
            created_at=data.get('created_at', ''),
            last_used_at=data.get('last_used_at', ''),
        )

    @classmethod
    def read_from_root(cls, resource_root: str):
        return cls.read(manifest_path(resource_root))

    def to_dict(self) -> dict:
        return {
            'version': self.version,
            'kind': self.kind,
            'cache_key': self.cache_key,
            'golem_version': self.golem_version,
            'source': self.source,
            'fetched': self.fetched,
            'created_at': self.created_at,
            'last_used_at': self.last_used_at,
        }

    def write(self, path: str) -> None:
        # Atomic write: dump to a sibling temp file then replace, so a crash mid
        # write can never leave a truncated manifest behind.
        os.makedirs(os.path.dirname(path), exist_ok=True)
        temp_path = path + '.tmp'
        with open(temp_path, 'w', encoding='utf-8') as fileout:
            json.dump(self.to_dict(), fileout, indent=2)
            fileout.write('\n')
        os.replace(temp_path, path)

    def write_to_root(self, resource_root: str) -> None:
        self.write(manifest_path(resource_root))

    @classmethod
    def touch(cls, resource_root: str) -> None:
        '''
        Refresh the `last_used_at` timestamp of an already-cached resource.
        Best-effort: does nothing when the resource has no manifest or cannot be
        written (e.g. a read-only cache), so it never interferes with a build.
        '''
        path = manifest_path(resource_root)
        manifest = cls.read(path)
        if manifest is None:
            return
        manifest.last_used_at = utc_now()
        try:
            manifest.write(path)
        except OSError:
            pass


def write_manifest(resource_root: str, kind, cache_key: str, source: dict,
                   fetched: dict = None) -> None:
    '''
    Write a fresh manifest at the root of a newly created cache resource.
    Best-effort: a failure here must never break a build, so errors are
    swallowed.
    '''
    try:
        manifest = ResourceManifest.create(
            kind=kind, cache_key=cache_key, source=source, fetched=fetched)
        manifest.write_to_root(resource_root)
    except OSError:
        pass


