import os
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
        self.locations = [default_cached_dir()]

    def __str__(self):
        return helpers.print_obj(self)
