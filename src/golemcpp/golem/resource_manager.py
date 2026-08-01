'''
Per-kind resource managers.

Every resource kind (dependency, cookbook, overlay, tool) is cached the same way
— resolve which configured cache it belongs to, compute its on-disk location,
read/write its manifest, install/remove it. That shared plumbing lives once in
`cache_manager.CacheManager`; each kind only knows how to turn its own object
into a `Resource` (via `resource_for`) and delegates every cache access to the
CacheManager it holds.

Fetching a source into the cache is shared the same way. The mechanism here is
the richest one any kind needs — shallow clones, submodules, cleaning,
checkout-then-reset — and a kind asks for what it wants through the FetchPolicy
it builds. A kind that wants more of it later turns a field on rather than
writing its own git.

Installing is a lifecycle rather than a single step: `install` brackets the fetch
with `pre_install`, `pre_install_refresh` and `post_install`, which is how a kind
that makes something from its source — a tool builds its binary there — says so
without owning the fetch.
'''

import os
import shutil
import subprocess
from dataclasses import dataclass

from golemcpp.golem import helpers
from golemcpp.golem.cache_configuration import SOURCE_DIRNAME
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
    # Fetch and reset the submodules along with the resource itself.
    submodules: bool = False
    # Discard local changes before refreshing an already-cached resource.
    clean: bool = False
    # Whether refreshing consults the remote. A pinned resource cannot move, so
    # it has nothing to fetch.
    fetch_remote: bool = True


class ResourceManager:
    '''A per-kind manager holds the shared CacheManager and delegates to it.'''

    def __init__(self, cache_manager):
        self.cache_manager = cache_manager

    @property
    def locations(self):
        return self.cache_manager.locations

    def resolve_cached_resource(self, item):
        '''
        Where an item lives in the caches: which cache it belongs to, where it
        sits there and whether it is already fetched, resolved in one go. The
        version comes first, since what it resolves to identifies the resource.
        '''
        return self.cache_manager.resolve_cached_resource(
            self.resource_for(self.resolve_version(item)))

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
        '''
        Where a resource keeps its fetched content under its root. Never the root
        itself: that is the resource, and it also holds the manifest naming it and
        whatever gets built from the source.
        '''
        return os.path.join(root, SOURCE_DIRNAME)

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

    def install(self, cached_resource, item, fetch=True, refresh=True) -> str:
        '''
        The resource root, with its content materialized when asked. Fresh: the
        whole root and its manifest are staged and swapped in one step. Existing:
        refreshed in place, keeping the cache root.
        '''
        if not fetch:
            return cached_resource.path

        if os.path.isdir(self.source_path(cached_resource.path)):
            if not refresh:
                self.cache_manager.touch_last_used(cached_resource.path)
                return cached_resource.path

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
        return cached_resource.path

    def populate(self, path, item):
        '''Materialize a source freshly into `path`, writing no manifest.'''
        source = self.source_for(item)
        local_path = self.validate_local_source(source)

        if source.type == SOURCE_TYPE_DIRECTORY:
            print("Copying directory {} into {}".format(source.location, path))
            self.copy_directory(source.location, local_path, path)
            return

        print("Cloning repository {} into {}".format(source.location, path))
        os.makedirs(path, exist_ok=True)
        self.clone_source(path, source, self.policy_for(item))

    def refresh_source(self, path, item):
        '''Bring an already-fetched source up to date in place, without re-cloning.'''
        source = self.source_for(item)
        local_path = self.validate_local_source(source)

        if source.type == SOURCE_TYPE_DIRECTORY:
            print("Copying directory {} into {}".format(source.location, path))
            self.copy_directory(source.location, local_path, path)
            return

        self.update_source(path, source, self.policy_for(item))

    # -- the mechanism itself ----------------------------------------------

    @staticmethod
    def clone_source(path, source, policy):
        '''A source obtained fresh from its remote, as much of it as asked for.'''
        if policy.shallow:
            helpers.run_git(['init'], cwd=path)
            helpers.run_git(['remote', 'add', 'origin', source.location], cwd=path)
            helpers.run_git(['fetch', '--depth=1', 'origin', policy.reference], cwd=path)
            helpers.run_git(['reset', '--hard', 'FETCH_HEAD'], cwd=path)
        else:
            helpers.run_git(['clone', '--', source.location, '.'], cwd=path)
            if policy.checkout:
                helpers.run_git(['checkout', policy.checkout], cwd=path)
            helpers.run_git(['reset', '--hard'] + ([policy.reference] if policy.reference else []),
                            cwd=path)

        if policy.submodules:
            helpers.run_git(
                ['submodule', 'update', '--init', '--recursive', '--depth=1'], cwd=path)

    @staticmethod
    def update_source(path, source, policy):
        '''An already-cloned source brought back to what it should be.'''
        if policy.clean:
            helpers.run_git(['clean', '-ffxd'], cwd=path, stdout=subprocess.DEVNULL)
            if policy.submodules:
                helpers.run_git(
                    ['submodule', 'foreach', '--recursive', 'git', 'clean', '-ffxd'],
                    cwd=path, stdout=subprocess.DEVNULL)

        if policy.fetch_remote:
            helpers.run_git(['fetch', 'origin'], cwd=path)

        helpers.run_git(['reset', '--hard'] + ([policy.reference] if policy.reference else []),
                        cwd=path, stdout=subprocess.DEVNULL if policy.clean else None)

        if policy.submodules:
            helpers.run_git(
                ['submodule', 'foreach', '--recursive', 'git', 'reset', '--hard'],
                cwd=path, stdout=subprocess.DEVNULL if policy.clean else None)
            helpers.run_git(
                ['submodule', 'update', '--init', '--recursive'],
                cwd=path, stdout=subprocess.DEVNULL if policy.clean else None)

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
