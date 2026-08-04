'''
Per-kind resource managers.

Every resource kind (dependency, cookbook, overlay, tool) is cached the same way
— resolve which configured cache it belongs to, compute its on-disk location,
read/write its manifest, install/remove it. That shared plumbing lives once in
`cache_manager.CacheManager`; each kind only knows how to turn its own object
into a `Resource` (via `resource_for`) and delegates every cache access to the
CacheManager it holds.

Fetching a source into the cache is shared the same way. Whatever a resource
holds, it is fetched whole and kept faithful to the reference it names. Use
FetchPolicy to customize the behavior.

Installing is a lifecycle rather than a single step: `install` brackets the fetch
with `pre_install`, `pre_install_refresh` and `post_install`, which is how a kind
that makes something from its source — a tool builds its binary there — says so
without owning the fetch.
'''

import os
import shutil
import subprocess
from dataclasses import dataclass

from golemcpp.golem import cache_configuration
from golemcpp.golem import helpers
from golemcpp.golem.source import SOURCE_TYPE_DIRECTORY


# Records where a copied directory came from, so a resource obtained without git
# can still name its origin (see Context.load_git_remote_origin_url).
ORIGIN_FILENAME = '.golem-origin'


@dataclass(frozen=True)
class FetchPolicy:
    '''
    Describes the requirements for a resource kind to be fetched from its source.
    '''

    # Fetch only the requested commit instead of the whole history.
    # TODO: Can't use shallow by default because of git describe --tags required for golem repos
    shallow: bool = False
    # Checked out before the reset, when the ref to land on is not the one to
    # check out (a dependency resets to a hash under a version tag).
    checkout: str = ''
    # What to reset to. Empty resets to the current HEAD, which is what a
    # resource pinned to a commit wants.
    reference: str = ''
    # Whether refreshing consults the remote. A pinned resource cannot move, so
    # it has nothing to fetch.
    fetch_remote: bool = True


@dataclass(frozen=True)
class FetchResult:
    '''
    What a fetch left behind, for the manifest to keep. The source says what was
    asked for — a branch as often as a commit — and this says what that turned
    out to be.

    Serialized like a Source is: the manifest holds the dict, this holds what it
    means.
    '''

    # The commit the fetch landed on. Empty when there was no git involved, as a
    # copied directory has no commit to name.
    head: str = ''

    def to_dict(self) -> dict:
        return {'head': self.head}

    @classmethod
    def from_dict(cls, data) -> 'FetchResult':
        if not data:
            return cls()
        return cls(head=data.get('head', ''))

    @classmethod
    def from_manifest(cls, manifest) -> 'FetchResult':
        '''What a cached resource's manifest says its root was left holding.'''
        return cls.from_dict(manifest.fetched if manifest else None)


class ResourceManager:
    '''A per-kind manager holds the shared CacheManager and delegates to it.'''

    def __init__(self, cache_manager):
        self.cache_manager = cache_manager

    @property
    def locations(self):
        return self.cache_manager.locations

    def resolve_cached_resource(self, item, compute_size=False, read_manifest=False, with_version_resolution=True):
        '''
        Where an item lives in the caches: which cache it belongs to, where it
        sits there and whether it is already fetched, resolved in one go. The
        version comes first, since what it resolves to identifies the resource.
        '''
        resolved_item = self.resolve_version(item) if with_version_resolution else item
        return self.cache_manager.resolve_cached_resource(
            self.resource_for(resolved_item),
            compute_size=compute_size,
            read_manifest=read_manifest)

    def guard_install(self, cached_resource, populate) -> str:
        '''Fetch a source into a staging dir, then atomically swap it into place
        with its manifest (see CacheManager.guard_install).'''
        return self.cache_manager.guard_install(cached_resource, populate)

    def guard_refresh(self, cached_resource, refresh) -> str:
        '''Bring a resource up to date in place and record what it now holds
        (see CacheManager.guard_refresh).'''
        return self.cache_manager.guard_refresh(cached_resource, refresh)

    # -- what a kind says for itself: data, not mechanism -------------------

    @staticmethod
    def resolve_version(item):
        '''
        The item with its version resolved to a concrete reference, returned so a
        caller keeps reading the one it handed over.
        '''
        return item

    @staticmethod
    def source_for(item):
        '''The Source an item denotes. Most kinds are handed one already.'''
        return item

    @staticmethod
    def source_path(root):
        '''Where a resource keeps its fetched content under its root.'''
        return cache_configuration.source_path(root)

    @classmethod
    def policy_for(cls, item):
        '''
        How to fetch this item. Tracks a branch on the remote, which is what a
        resource that is not pinned to a commit wants.
        '''
        return FetchPolicy(reference='origin/' + cls.source_for(item).reference)

    @staticmethod
    def pre_install(item):
        '''
        Called before a fresh fetch, never before a refresh. Not where a version
        is resolved: that has to happen before the resource is even located, see
        resolve_version.
        '''

    @staticmethod
    def pre_install_refresh(root, item):
        '''
        Called before a refresh moves the source: whatever the kind made from the
        previous one, which is stale the moment the source changes.
        '''

    @staticmethod
    def post_install(root, item):
        '''
        What the kind makes from the source it now holds, beside it in the
        resource root. Most kinds are built by a later command and make nothing.
        '''

    # -- installation ------------------------------------------------------

    def is_installed(self, cached_resource) -> bool:
        '''
        Whether the root holds the fetched source a consumer reads. This is about
        the content. CachedResource.exists() is about the location in cache,
        which is what resolution matches a resource to.
        '''
        return os.path.isdir(cached_resource.source_path)

    def install(self, item, refresh=True, cached_resource=None):
        '''
        Installs the item in cache and returns the cached resource associated.

        Fresh install: the whole root and its manifest are staged and swapped
        in one step.

        Existing install: refreshed in place, keeping the cache root.

        An installed resource is handed back untouched without `refresh`.

        Installing into a read-only cache location is refused. Nothing is written
        there, whether the resource has to be populated or refreshed.

        `cached_resource` skips the resolution when the caller already did it.
        '''
        if cached_resource is None:
            cached_resource = self.resolve_cached_resource(item)

        installed = self.is_installed(cached_resource)
        if installed and not refresh:
            return cached_resource

        # Everything below writes into the cache root.
        if cached_resource.is_read_only:
            raise RuntimeError(
                'cannot install {} into read-only cache location {}'.format(
                    cached_resource.cache_key, cached_resource.cache_root))

        if installed:
            self.pre_install_refresh(cached_resource.path, item)
            self.guard_refresh(
                cached_resource,
                lambda root: self.refresh_source(self.source_path(root), item))
        else:
            self.pre_install(item)
            self.guard_install(
                cached_resource,
                lambda staging_root: self.populate(
                    self.source_path(staging_root), item))

        self.post_install(cached_resource.path, item)
        return cached_resource

    def make_available(self, item, fetch=True, refresh=True):
        '''
        The item's cached resource, ready to read. Either installed, or kept as
        is from a read-only location.

        `fetch=False` only resolves where the resource lives and fetches nothing.

        Raises when a read-only location does not hold the resource. There is
        nothing to serve and nothing may be written.
        '''
        cached_resource = self.resolve_cached_resource(item)

        if not fetch:
            return cached_resource

        if cached_resource.is_read_only and self.is_installed(cached_resource):
            return cached_resource

        return self.install(item, refresh=refresh, cached_resource=cached_resource)

    def make_available_all(self, items, fetch=True, refresh=True):
        '''Each item made available, in the order it was given.'''
        return [
            self.make_available(item, fetch=fetch, refresh=refresh)
            for item in items
        ]

    def populate(self, path, item):
        '''Materialize a source freshly into `path`, writing no manifest.'''
        source = self.source_for(item)
        local_path = self.validate_local_source(source)

        if source.type == SOURCE_TYPE_DIRECTORY:
            print("Copying directory {} into {}".format(source.location, path))
            self.copy_directory(source.location, local_path, path)
            return FetchResult()

        print("Cloning repository {} into {}".format(source.location, path))
        os.makedirs(path, exist_ok=True)
        return self.clone_source(path, source, self.policy_for(item))

    def refresh_source(self, path, item):
        '''Bring an already-fetched source up to date in place, without re-cloning.'''
        source = self.source_for(item)
        local_path = self.validate_local_source(source)

        if source.type == SOURCE_TYPE_DIRECTORY:
            print("Copying directory {} into {}".format(source.location, path))
            self.copy_directory(source.location, local_path, path)
            return FetchResult()

        return self.update_source(path, source, self.policy_for(item))

    # -- the mechanism itself ----------------------------------------------

    @staticmethod
    def clone_source(path, source, policy):
        '''A source obtained fresh from its remote, as much of it as asked for.

        Everything that only moves the working tree is quiet. What reaches the
        remote keeps reporting its progress.
        '''
        if policy.shallow:
            helpers.run_git(['init'], cwd=path, quiet=True)
            helpers.run_git(['remote', 'add', 'origin', source.location], cwd=path, quiet=True)
            helpers.run_git(['fetch', '--depth=1', 'origin', policy.reference], cwd=path)
            helpers.run_git(['reset', '--hard', 'FETCH_HEAD'], cwd=path, quiet=True)
        else:
            helpers.run_git(['clone', '--', source.location, '.'], cwd=path)
            if policy.checkout:
                helpers.run_git(['checkout', policy.checkout], cwd=path, quiet=True)
            ResourceManager.ensure_reference(path, source, policy)
            helpers.run_git(['reset', '--hard'] + ([policy.reference] if policy.reference else []), cwd=path, quiet=True)

        if ResourceManager.has_submodules(path):
            # Only a shallow resource takes shallow submodules: at a depth of one, a
            # submodule whose recorded commit is not a tip the remote advertises
            # cannot be fetched at all.
            submodule_update = ['submodule', 'update', '--init', '--recursive']
            if policy.shallow:
                submodule_update.append('--depth=1')
            helpers.run_git(submodule_update, cwd=path)

        return FetchResult(head=ResourceManager.read_head(path))

    @staticmethod
    def update_source(path, source, policy):
        '''An already-cloned source brought back to what it should be.

        Cleaning comes first: a reset alone leaves behind what the previous
        reference put there, and a cached resource is only worth reading when it
        holds the reference it names and nothing else.
        '''
        helpers.run_git(['clean', '-ffxd'], cwd=path, quiet=True)
        if ResourceManager.has_submodules(path):
            helpers.run_git(['submodule', 'foreach', '--recursive', 'git', 'clean', '-ffxd'], cwd=path, quiet=True)

        if policy.fetch_remote:
            # Pruning both ways: a branch deleted upstream stops being tracked, and a
            # tag that moved is honoured rather than kept at what it used to point to.
            helpers.run_git(['fetch', '--prune', '--prune-tags', '--tags', 'origin'], cwd=path)

        ResourceManager.ensure_reference(path, source, policy)
        helpers.run_git(['reset', '--hard'] + ([policy.reference] if policy.reference else []), cwd=path, quiet=True)

        if ResourceManager.has_submodules(path):
            helpers.run_git(['submodule', 'foreach', '--recursive', 'git', 'reset', '--hard'], cwd=path, quiet=True)

            # After the reset, so .gitmodules is the one the reference names, and
            # before the update, which otherwise keeps fetching from the URL recorded
            # at clone time however the resource respelled it since.
            helpers.run_git(['submodule', 'sync', '--recursive'], cwd=path, quiet=True)

            submodule_update = ['submodule', 'update', '--init', '--recursive']
            if not policy.fetch_remote:
                submodule_update.append('--no-fetch')
            helpers.run_git(submodule_update, cwd=path)

        return FetchResult(head=ResourceManager.read_head(path))

    @staticmethod
    def ensure_reference(path, source, policy):
        '''
        The reference has to name something the repository holds before anything
        resets to it.
        '''
        if not policy.reference or ResourceManager.holds_reference(path, policy.reference):
            return

        missing = RuntimeError(
            'Cannot find "{}" in "{}", and {} does not offer it. '
            'Run golem resolve first.'.format(policy.reference, path, source.location))

        try:
            helpers.run_git(['fetch', 'origin', policy.reference], cwd=path)
        except RuntimeError as error:
            # A reference the remote no longer has: a branch pruned away, a tag
            # deleted, a commit never pushed.
            # 
            # What git says about a refspec it could not find says nothing about
            # which resource asked for it.
            raise missing from error

        if not ResourceManager.holds_reference(path, policy.reference):
            raise missing

    @staticmethod
    def has_submodules(path) -> bool:
        '''
        Whether the revision in place declares any submodule.
        '''
        return os.path.isfile(os.path.join(path, '.gitmodules'))

    @staticmethod
    def holds_reference(path, reference) -> bool:
        '''Whether the repository already holds the commit a reference names.'''
        return helpers.call_git(
            ['rev-parse', '--verify', '--quiet', '{}^{{commit}}'.format(reference)],
            cwd=path, stdout=subprocess.DEVNULL) == 0

    @staticmethod
    def read_head(path) -> str:
        '''
        The commit the working tree is on, for the manifest to record. Best-effort:
        what the root holds is worth knowing, never worth failing a fetch over.
        '''
        try:
            return helpers.check_git_output(
                ['rev-parse', 'HEAD'], cwd=path, stderr=subprocess.DEVNULL).strip()
        except Exception:
            return ''

    @staticmethod
    def copy_directory(location, local_path, path):
        '''A source obtained by copying it, since there is no remote to track.'''
        if os.path.isdir(path):
            shutil.rmtree(path)
        shutil.copytree(local_path, path, dirs_exist_ok=True, symlinks=True)
        with open(os.path.join(path, ORIGIN_FILENAME), 'w') as fp:
            fp.write(location)

    @staticmethod
    def validate_local_source(source):
        '''
        The local path a source lives at, refused here rather than deep inside a
        copy or a clone. None when the source is not local.
        '''
        local_path = source.get_local_path()
        if local_path is None:
            return None

        if not os.path.exists(local_path):
            raise RuntimeError(
                "Can't find local source directory: {}".format(local_path))
        if not os.path.isdir(local_path):
            raise RuntimeError(
                "Local source path is not a directory: {}".format(local_path))

        return local_path
