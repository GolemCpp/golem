'''
Per-kind resource managers.

Every resource kind (dependency, cookbook, overlay, tool) is cached the same way
— resolve which configured cache it belongs to, compute its on-disk location,
read/write its manifest, install/remove it. That shared plumbing lives once in
`cache_manager.CacheManager`; each kind only knows how to turn its own object
into a `Resource` (via `resource_for`) and delegates every cache access to the
CacheManager it holds.

Fetching is shared the same way, and owned elsewhere: a kind says what it wants
through the `FetchPolicy` it builds, and `fetcher` picks whatever knows how to
obtain that source. What comes back is a `Fetched` naming what the cache root
ended up holding.

Installing is a lifecycle rather than a single step: `install` brackets the fetch
with `pre_install`, `pre_install_refresh` and `post_install`, which is how a kind
that makes something from its source — a tool builds its binary there — says so
without owning the fetch.
'''

import os

from golemcpp.golem import cache_configuration
from golemcpp.golem import fetcher
from golemcpp.golem import network
from golemcpp.golem.fetch_policy import FetchPolicy


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

    @property
    def fetch_mode(self):
        '''
        How much of a source to obtain. Configured once for every kind: each has
        to be refreshable in place, and some follow a branch, so none of them is
        in a position to want something different.
        '''
        return self.cache_manager.cache_configuration.fetch_mode

    @property
    def fetch_jobs(self):
        '''How many submodules to obtain at once, configured for every kind.'''
        return self.cache_manager.cache_configuration.fetch_jobs

    def policy_for(self, item):
        '''
        How to fetch this item.

        See GitFetcher.resolved_reset_reference to know how the reference is interpreted.
        '''
        return FetchPolicy(
            fetch_mode=self.fetch_mode,
            fetch_jobs=self.fetch_jobs,
            reference=self.source_for(item).reference)

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

    @staticmethod
    def may_migrate(cached_resource) -> bool:
        '''
        Whether this is a moment to change what a root holds.

        Converting one may have to reach a remote, so it belongs to resolve, the
        command allowed to; and it writes, so a read-only location keeps whatever
        it was given. Everywhere else a root is used in the shape it is in, and
        changes shape the next time it is resolved.
        '''
        return network.is_allowed() and not cached_resource.is_read_only

    def install(self, item, refresh=True, cached_resource=None):
        '''
        Installs the item in cache and returns the cached resource associated.

        Fresh install: the whole root and its manifest are staged and swapped
        in one step.

        Existing install: refreshed in place, keeping the cache root.

        An installed resource is handed back untouched without `refresh`, as long
        as it already is in the fetch mode asked for.
        
        If the asked fetch mode and the detected one are different, the resource
        is migrated. This can involve obtaining it again, whether or not anything
        only wanted it refreshed.

        Installing into a read-only cache location is refused. Nothing is written
        there, whether the resource has to be populated or refreshed.

        `cached_resource` skips the resolution when the caller already did it.
        '''
        if cached_resource is None:
            cached_resource = self.resolve_cached_resource(item)

        installed = self.is_installed(cached_resource)

        if installed and self.may_migrate(cached_resource) \
                and not self.migrate(cached_resource, item):
            # What the root holds is not what is asked for any more, and cannot be
            # turned into it. Obtaining it again always can.
            installed = False

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

    def fetcher_for(self, path, item):
        '''
        What will obtain this item into `path`. The kind says which source and
        under which policy; how that source is obtained is the source's own
        business.
        '''
        return fetcher.fetcher_for(path, self.source_for(item), self.policy_for(item))

    def migrate(self, cached_resource, item) -> bool:
        '''
        Whether the root can keep being used, given what the manifest says it was
        fetched as and what is asked for now. What it then holds is written back,
        so a conversion is done once rather than on every resolve.

        A conversion that fails leaves a root nobody has read yet, so the answer
        is simply no and the caller obtains it again.
        '''
        recorded = self.cache_manager.read_manifest_fetched(cached_resource)
        try:
            fetched = self.fetcher_for(
                self.source_path(cached_resource.path), item).migrate(recorded)
        except RuntimeError as error:
            print("Cannot migrate {}, fetching it again: {}".format(
                cached_resource.path, error))
            return False

        if fetched is None:
            return False

        if fetched != recorded:
            self.cache_manager.write_manifest(cached_resource, fetched=fetched)
        return True

    def populate(self, path, item):
        '''Materialize a source freshly into `path`, writing no manifest.'''
        return self.fetcher_for(path, item).populate()

    def refresh_source(self, path, item):
        '''Bring an already-fetched source up to date in place, without re-cloning.'''
        return self.fetcher_for(path, item).refresh()
