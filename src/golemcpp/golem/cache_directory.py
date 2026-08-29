import re

from golemcpp.golem import helpers


class CacheDirectory:
    def __init__(self, location, is_read_only=False, regex=None):
        self._location = location
        self._is_read_only = is_read_only
        self._regex = regex

    def __str__(self):
        return self._location

    @property
    def location(self):
        return self._location

    @property
    def is_read_only(self):
        return self._is_read_only

    @property
    def regex(self):
        return self._regex


# The functors the cache directory settings are read and written through (see
# setting_descriptor.SettingDescriptor). Keeping the `PATH[=URL_REGEX]` grammar
# here means a value is parsed and a forwarded flag is written by the same code.


def parse_location(entry, context):
    '''
    The primary cache directory: the whole value is a path, never split, so a
    directory name may contain an `=`.
    '''
    return CacheDirectory(
        location=helpers.make_absolute_path(entry, context.project_dir),
        is_read_only=False,
    )


def parse_writable_entry(entry, context):
    return _parse_entry(entry, context, is_read_only=False)


def parse_read_only_entry(entry, context):
    return _parse_entry(entry, context, is_read_only=True)


def _parse_entry(entry, context, is_read_only):
    '''
    An additional cache directory, written `PATH[=URL_REGEX]` where the regex
    selects the resources the cache holds. Raises on an entry Golem cannot use.
    '''
    location, _, regex = entry.partition('=')
    if not location:
        raise RuntimeError("Bad cache definition: {}".format(entry))

    if regex:
        re.compile(regex)
    else:
        regex = None

    return CacheDirectory(
        location=helpers.make_absolute_path(location, context.project_dir),
        is_read_only=is_read_only,
        regex=regex,
    )


def format_entry(cache_directory, context):
    '''The `PATH[=URL_REGEX]` spelling of a cache directory.'''
    if cache_directory.regex:
        return '{}={}'.format(cache_directory.location, cache_directory.regex)
    return cache_directory.location
