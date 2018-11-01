import os
import helpers


def default_cached_dir():
    return os.path.join(os.path.expanduser("~"), '.cache', 'golem')


class CacheConf:
    def __init__(self):
        self.remote = ''
        self.location = default_cached_dir()

    def __str__(self):
        return helpers.print_obj(self)
