import os
import re
from enum import Enum
from golemcpp.golem import helpers


class CacheDir:
    def __init__(self, location, is_static=False, regex=None):
        self._location = location
        self._is_static = is_static
        self._regex = regex

    def __str__(self):
        return self._location

    @property
    def location(self):
        return self._location

    @property
    def is_static(self):
        return self._is_static

    @property
    def regex(self):
        return self._regex


def default_cached_dir():
    return CacheDir(os.path.join(os.path.expanduser("~"), '.cache', 'golem'))


class CacheConf:
    def __init__(self):
        self.remote = ''
        self.locations = []

    def __str__(self):
        return helpers.print_obj(self)

class CacheResolutionPolicy(Enum):
    STRICT = "strict" # Only the first matching cache is considered to find the resource.
    WEAK = "weak" # Every valid matching cache is considered to find the resource.


class CachedResourceResolver:
    def __init__(self,
                 identifier,
                 cache_conf,
                 policy,
                 exists_in_cache=None):
        self._identifier = identifier
        self._cache_conf = cache_conf
        self._policy = policy
        self._exists_in_cache = exists_in_cache

    def _find_matching_caches(self, is_read_only, with_regex):
        found_caches = []

        for cache_dir in self._cache_conf.locations:
            if with_regex and not cache_dir.regex:
                continue
            if not with_regex and cache_dir.regex:
                continue
            if is_read_only and not cache_dir.is_static:
                continue
            if with_regex:
                pattern = re.compile(cache_dir.regex)
                if not pattern.match(self._identifier):
                    continue
            found_caches.append(cache_dir)

        return found_caches

    def _select_cache(self, candidates):
        if not candidates:
            return None

        if self._policy == CacheResolutionPolicy.STRICT:
            return candidates[0]

        if self._exists_in_cache is not None:
            for cache_dir in candidates:
                if self._exists_in_cache(cache_dir):
                    return cache_dir

        return None

    def resolve(self):
        read_only_caches_with_regex = self._find_matching_caches(
            is_read_only=True,
            with_regex=True)
        cache_dir = self._select_cache(read_only_caches_with_regex)
        if cache_dir is not None:
            return cache_dir

        read_only_caches_without_regex = self._find_matching_caches(
            is_read_only=True,
            with_regex=False)
        cache_dir = self._select_cache(read_only_caches_without_regex)
        if cache_dir is not None:
            return cache_dir

        writable_caches_with_regex = self._find_matching_caches(
            is_read_only=False,
            with_regex=True)
        cache_dir = self._select_cache(writable_caches_with_regex)
        if cache_dir is not None:
            return cache_dir

        writable_caches_without_regex = self._find_matching_caches(
            is_read_only=False,
            with_regex=False)
        cache_dir = self._select_cache(writable_caches_without_regex)
        if cache_dir is not None:
            return cache_dir

        if writable_caches_with_regex:
            return writable_caches_with_regex[0]
        if writable_caches_without_regex:
            return writable_caches_without_regex[0]

        raise RuntimeError("Can't find any writable cache location")