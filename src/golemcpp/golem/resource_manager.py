'''
Per-kind resource managers.

Every resource kind (dependency, cookbook, overlay, tool) is cached the same way:
find which configured cache it belongs to, compute its on-disk location, read
and write its manifest, install and remove it. That shared plumbing lives once
in `cache_manager.CacheManager`. A manager turns its kind's object into a
`Resource` with `resource_for`, then delegates every cache access to the
CacheManager it holds.

Two declarations say what a kind is: the `ResourceKind` naming the subdir its
roots go under, and the `Pinning` naming what one takes its identity from. The cache
key and whether a refresh consults the remote both follow from the `Pinning`.
Therefore a manager with nothing else to say is those two lines and no more.

Fetching is shared the same way, and owned elsewhere. A kind builds a
`FetchPolicy` saying what it wants, and `fetcher` picks the fetcher that knows
how to obtain that source. A `Fetched` comes back, naming what the cache root
ended up holding.

Installing is a lifecycle rather than a single step. `install` brackets the
fetch with `pre_install`, `pre_install_refresh` and `post_install`. A kind that
builds something from its source, such as a tool building its binary, does it
in those hooks and leaves the fetch alone.
'''

import os
import re
from enum import Enum

from golemcpp.golem import cache_configuration
from golemcpp.golem import fetcher
from golemcpp.golem import locator
from golemcpp.golem import network
from golemcpp.golem import safe_part
from golemcpp.golem.fetch_policy import FetchPolicy
from golemcpp.golem.resource import Resource
from golemcpp.golem.source import SOURCE_TYPE_GIT


# What separates the major fields of a cache key: `<source id>+<revision>`.
CACHE_KEY_SEPARATOR = '+'

# 40 hex is a SHA-1 object name, 64 a SHA-256 one. Git is migrating to SHA-256 and
# a repository names its objects in one format or the other, so both have to read
# as an object name here.
GIT_OBJECT_NAME = re.compile(r'^([0-9a-f]{40}|[0-9a-f]{64})$')

# What a directory name may hold, on the strictest of the platforms golem runs on.
# Lowercase only: NTFS and APFS are case-insensitive, so case cannot carry meaning
# there the way it does in a git ref name. Anything else becomes
# locator.SUBSTITUTE_MARKER, the same marker an id uses, so `release/1.2.3` reads
# as `release~1.2.3` rather than as a ref that was named `release-1.2.3`.
UNSAFE_IN_COMPONENT = re.compile(r'[^0-9a-z._-]')



def make_revision_component(revision):
    '''
    Makes a revision as one directory-name component.

    It can be a hash: In which case it is abbreviated to 8 characters.

    It can be a reference: In which case it can be abbreviated if it is too long.
    But it will also always be appended with a digest of it since the reference
    is processed to be safe for any filesystem, which can be lossy.
    '''
    if not revision:
        return ''

    if GIT_OBJECT_NAME.match(revision):
        return revision[:safe_part.DIGEST_LENGTH]

    slug = UNSAFE_IN_COMPONENT.sub(locator.SUBSTITUTE_MARKER, revision.lower())

    return safe_part.with_digest(
        slug[:safe_part.READABLE_LENGTH], of=revision)


class Pinning(Enum):
    '''
    What a cache root is named after, and therefore what pins it.

    Three things follow from the pinning: what the cache key is, whether a
    refresh consults the remote, and whether the root can be found without
    resolving anything. Each pinning reads one field, and the three fields are
    three points of the pipeline:

        NAME     -> item.name              the resource itself
        REQUEST  -> item.version           what was asked for
        REVISION -> resolved.revision      what that resolved to

    Only REVISION needs a resolution to name a root. A dependency is the one
    kind that writes its resolution down, in `dependencies.json`, therefore it
    is the one kind that can afford REVISION. The others name their root from
    what was configured, so `golem configure` locates them with the network
    closed.

    The pinning belongs to the kind, not to the item. A dependency asked for at
    a branch still resolves to a commit, so it is REVISION whatever was asked.
    '''

    # One root per resource name, re-pointed at whatever version is asked for
    # next.
    NAME = 'name'
    # One root per request, re-pointed at whatever that request resolves to now.
    # A range and a branch behave alike: `^1.0.0` moves from 1.1.0 to 1.2.0 in
    # place, the way `main` moves from commit to commit.
    REQUEST = 'request'
    # One root per commit. A commit never moves, therefore there is nothing to
    # refresh.
    REVISION = 'revision'


class ResourceManager:
    '''A per-kind manager holds the shared CacheManager and delegates to it.'''

    # What this manager manages. A subclass names its own kind. The base class
    # has none, because it is the shared plumbing and not a kind.
    kind = None

    # What one of its roots takes its identity from. The request by default, so
    # a root follows what was asked for as that moves. A kind that needs
    # something else says so.
    pinning = Pinning.REQUEST

    def __init__(self, cache_manager):
        self.cache_manager = cache_manager

    @property
    def locations(self):
        return self.cache_manager.locations

    def resolve_cached_resource(self, item, compute_size=False, read_manifest=False):
        '''
        Find where an item lives in the caches: which cache it belongs to, where
        it sits there, and whether it is already fetched.

        The version is resolved first, because a kind may be keyed on what it
        resolves to.
        '''
        return self.cache_manager.resolve_cached_resource(
            self.resource_for(self.resolve_version(item)),
            compute_size=compute_size,
            read_manifest=read_manifest)

    def guard_install(self, cached_resource, populate) -> str:
        '''
        Fetch a source into a staging directory, then swap it into place with
        its manifest in one step (see CacheManager.guard_install).
        '''
        return self.cache_manager.guard_install(cached_resource, populate)

    def guard_refresh(self, cached_resource, refresh) -> str:
        '''
        Bring a resource up to date in place and record what it now holds (see
        CacheManager.guard_refresh).
        '''
        return self.cache_manager.guard_refresh(cached_resource, refresh)

    # -- what a kind says for itself: data, not mechanism -------------------

    @classmethod
    def resolve_version(cls, item):
        '''
        Resolve the version of an item, and return that same item.

        Resolving reaches a remote, therefore only `golem resolve` does it.
        Everywhere else the item stands as it arrived:

        - NAME and REQUEST name a root from what the item already carries.
        - REVISION names one from a commit, so an item without one names no
          root. Raise, unless it asks for a directory, which has no commit.
        '''
        if network.is_allowed():
            item.resolve()
            return item

        if cls.pinning is not Pinning.REVISION or item.resolved.revision:
            return item

        requested = item.requested()
        if requested.type == SOURCE_TYPE_GIT:
            raise RuntimeError(
                "'{}' is not resolved, and reaching a remote is a resolve step. "
                "Run golem resolve first.".format(requested.locator))

        return item

    @staticmethod
    def source_for(item):
        '''
        Make the Source of an item, from what it asked for and what that
        resolved to.

        Every kind answers `requested()` and carries a `resolved`, therefore
        none overrides this.
        '''
        return item.requested().resolved_at(item.resolved)

    @classmethod
    def resource_for(cls, item) -> Resource:
        return Resource(
            kind=cls.kind,
            cache_key=cls.cache_key_for(item),
            source=cls.source_for(item))

    @classmethod
    def cache_key_for(cls, item):
        '''
        Make the cache key of an item.

        The key identifies the item in a cache and is safe to use as the name of
        the directory holding it. The kind's pinning decides its shape (see
        Pinning).

            cppfront                                    pinned on the name
            mylib@fsys.tmp                              a source with no version
            recipes@com.github.golemcpp+main=0d6e4079   pinned on the request
            json@com.github.nlohmann+65ee6845           pinned on the commit
        '''
        if cls.pinning is Pinning.NAME:
            # Verbatim, and without asking for anything else. The name is
            # Golem's own, therefore it is already safe as a directory name.
            return item.name

        requested = item.requested()
        component = make_revision_component(
            item.resolved.revision
            if cls.pinning is Pinning.REVISION else requested.version)

        # With no version to name, there is nothing for the separator to join.
        if not component:
            return requested.get_id()

        return requested.get_id() + CACHE_KEY_SEPARATOR + component

    @staticmethod
    def source_path(root):
        '''Make the path where a resource keeps its fetched source, under its root.'''
        return cache_configuration.source_path(root)

    @property
    def fetch_mode(self):
        '''
        How much of a source to obtain.
        
        It is configured once for every kind, because each kind has to be
        refreshable in place and some follow a branch. A single resource may still
        ask for something else, see fetch_mode_for.
        '''
        return self.cache_manager.cache_configuration.fetch_mode

    @property
    def fetch_jobs(self):
        '''How many submodules to obtain at once, configured for every kind.'''
        return self.cache_manager.cache_configuration.fetch_jobs

    def fetch_mode_for(self, item):
        '''
        Choose how much of this item's source to obtain. The configured mode,
        unless the kind knows of a resource that asks for something else.
        '''
        return self.fetch_mode

    def policy_for(self, item):
        '''
        Build the policy for fetching this item.

        When a root is pinned to a REVISION, it is pinned on a commit. Therefore
        there is nothing to fetch when refreshing it. But every other root
        follows what was asked for (e.g. a branch, a version range), so it does
        need fetching on a refresh.

        The revision handed over is the commit the version resolved to, so a
        fetcher never interprets a name.
        '''
        return FetchPolicy(
            fetch_mode=self.fetch_mode_for(item),
            fetch_jobs=self.fetch_jobs,
            revision=self.source_for(item).resolved.revision,
            fetch_remote=self.pinning is not Pinning.REVISION)

    @staticmethod
    def pre_install(item):
        '''
        Do whatever a kind needs before a fresh fetch. It never runs before a
        refresh.

        Do not resolve a version here. That has to happen before the resource is
        located at all, see resolve_version.
        '''

    @staticmethod
    def pre_install_refresh(root, item):
        '''
        Drop whatever the kind built from the previous source, before a refresh
        moves it.
        
        What it built goes stale as soon as the source changes.
        '''

    @staticmethod
    def post_install(root, item):
        '''
        Build whatever the kind makes from the source it now holds.
        
        Most kinds make nothing here, because a later command builds what they
        need.
        '''

    # -- installation ------------------------------------------------------

    def is_installed(self, cached_resource) -> bool:
        '''
        Does the root hold the fetched source?

        CachedResource.exists() asks whether the root directory itself is there,
        which is what resolution matches a resource to.
        '''
        return cached_resource.is_installed

    @staticmethod
    def may_migrate(cached_resource) -> bool:
        '''
        Is this a moment to change what a root holds?

        Migrating requires network access because it may reach a remote, and a
        writable location because it writes into the root.

        Return False when either requirement is missing.
        '''
        return network.is_allowed() and not cached_resource.is_read_only

    def install(self, item, refresh=True, cached_resource=None):
        '''
        Install the item in cache, and return the cached resource holding it.

        - Not installed: staged whole with its manifest, then swapped into
          place in one step.
        - Already installed: refreshed in place, so it keeps its cache root.
        - Already installed and `refresh` is off: handed back untouched, as long
          as it already is in the fetch mode asked for.
        - Fetched in a different mode than the one asked for: migrated first,
          which may mean obtaining it again even when the caller only wanted a
          refresh.
        - In a read-only cache location: refused, whether it has to be populated
          or refreshed.

        Pass `cached_resource` to skip the resolution when the caller already
        did it.
        '''
        if cached_resource is None:
            cached_resource = self.resolve_cached_resource(item)

        installed = self.is_installed(cached_resource)

        if installed and self.may_migrate(cached_resource) \
                and not self.migrate(cached_resource, item):
            # What the root holds is not what is asked for any more, and cannot
            # be turned into it. Obtain it again instead.
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
        Make the item's cached resource ready to read, either by installing it
        or by keeping what a read-only location already holds.

        With `fetch=False`, only resolve where the resource lives and fetch
        nothing.

        Raises when a read-only location does not hold the resource, because
        there is nothing to serve and nothing may be written.
        '''
        cached_resource = self.resolve_cached_resource(item)

        if not fetch:
            return cached_resource

        if cached_resource.is_read_only and self.is_installed(cached_resource):
            return cached_resource

        return self.install(item, refresh=refresh, cached_resource=cached_resource)

    def make_available_all(self, items, fetch=True, refresh=True):
        '''Make every item available, in the order it was given.'''
        return [
            self.make_available(item, fetch=fetch, refresh=refresh)
            for item in items
        ]

    def fetcher_for(self, path, item):
        '''
        Pick the fetcher that will obtain this item into `path`.

        The kind supplies the source and the policy. How that source is obtained
        belongs to the fetcher.
        '''
        return fetcher.fetcher_for(path, self.source_for(item), self.policy_for(item))

    def migrate(self, cached_resource, item) -> bool:
        '''
        Convert what the root holds into what is asked for now, and return
        whether it can keep being used.

        The manifest records what was fetched, therefore it is updated whenever
        the conversion changes that.

        A conversion that fails returns False. Nothing has read the root yet, so
        the caller simply obtains it again.
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
        '''Fetch a source into `path` from scratch, writing no manifest.'''
        return self.fetcher_for(path, item).populate()

    def refresh_source(self, path, item):
        '''Bring a source that is already there up to date, without cloning it again.'''
        return self.fetcher_for(path, item).refresh()
