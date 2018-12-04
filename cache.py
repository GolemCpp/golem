import os
import helpers


class CacheDir:
    def __init__(self, location, is_static=False):
        self._location = location
        self._is_static = is_static

    @property
    def location(self):
        return self._location

    @property
    def is_static(self):
        return self._is_static

    def __str__(self):
        return _location


def default_cached_dir():
    return CacheDir(os.path.join(os.path.expanduser("~"), '.cache', 'golem'))


class CacheConf:
    def __init__(self):
        self.remote = ''
        self.locations = [default_cached_dir()]

    def __str__(self):
        return helpers.print_obj(self)
