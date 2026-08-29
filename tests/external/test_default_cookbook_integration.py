'''
Whether the cookbook Golem ships as its default is still there to be fetched.

What that cookbook holds is the cookbook's own business, therefore nothing here
reads a recipe, lists a directory or composes an identity to look up.

This is the one place a remote being unreachable is asserted rather than skipped.
'''

import pytest

from golemcpp.golem import cache_directory
from golemcpp.golem.cookbook_manager import get_cookbook_manager
from host import can_access_git_remote
from support import default_setting
from support import make_cache_configuration


def default_cookbook_sources():
    '''
    What Golem resolves `cookbooks.locations` to with nothing configured.

    Read through the setting rather than from `settings.DEFAULT_COOKBOOK_LOCATION`,
    so the spelling and its deserialization are covered too and neither can drift
    from what a run actually uses.
    '''
    return default_setting('GOLEM_COOKBOOKS_LOCATIONS')


def test_the_default_names_one_cookbook_git_can_reach():
    sources = default_cookbook_sources()

    assert sources, 'no default cookbook is configured'

    for source in sources:
        assert can_access_git_remote(str(source.locator)), (
            'the default cookbook is unreachable: {}. The constant may have '
            'rotted, or the repository was renamed or made private.'.format(
                source.locator
            )
        )


def test_the_default_cookbook_is_fetched_into_a_cache(tmp_path, resolving):
    manager = get_cookbook_manager(
        make_cache_configuration(cache_directory.CacheDirectory(location=str(tmp_path)))
    )

    cookbooks = [manager.get_cookbook(source) for source in default_cookbook_sources()]
    for cookbook in cookbooks:
        cookbook.resolve()

    for cached in manager.make_available_all(cookbooks):
        assert cached.is_installed

        # Golem's own record of the fetch, read back from the root rather than
        # from the object that wrote it.
        source = manager.cache_manager.read_manifest_source(cached)

        # The cookbook's content isn't exercised because what a cookbook holds
        # is the cookbook's business.

        assert source is not None, 'the fetch left no manifest'
        assert source.resolved.revision, 'the manifest records no commit'
