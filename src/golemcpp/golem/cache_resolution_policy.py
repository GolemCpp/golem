from enum import Enum


class CacheResolutionPolicy(Enum):
    STRICT = (
        "strict"  # Only the first matching cache is considered to find the resource.
    )
    WEAK = "weak"  # Every valid matching cache is considered to find the resource.


# The functors the cache.resolution-policy setting is read and written through
# (see setting_descriptor.SettingDescriptor).


def parse_policy(text, context):
    '''The policy a configured name stands for. Raises on an unknown name.'''
    return CacheResolutionPolicy(text)


def format_policy(resolution_policy, context):
    return resolution_policy.value
