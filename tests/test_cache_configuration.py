import pytest

from golemcpp.golem.cache_configuration import CacheConfiguration
from golemcpp.golem.cache_directory import CacheDirectory
from golemcpp.golem.cache_resolution_policy import CacheResolutionPolicy
from golemcpp.golem.fetch_policy import FetchMode


def _arguments(**overrides):
    arguments = dict(
        locations=[CacheDirectory(location='/opt/cache')],
        resolution_policy=CacheResolutionPolicy.STRICT,
        minimization_enabled=True,
        minimization_length=8,
        fetch_mode=FetchMode.BLOBLESS)
    arguments.update(overrides)
    return arguments


def test_every_setting_is_required():
    for name in _arguments():
        with pytest.raises(ValueError) as error:
            CacheConfiguration(**_arguments(**{name: None}))
        assert name in str(error.value)


def test_a_disabled_or_empty_setting_is_a_value():
    # False and an empty location list are answers, not missing settings.
    configuration = CacheConfiguration(
        **_arguments(locations=[], minimization_enabled=False))

    assert configuration.locations == []
    assert configuration.minimization_enabled is False
