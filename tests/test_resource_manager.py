from golemcpp.golem import cache_directory
from golemcpp.golem.cache_manager import get_cache_manager
from golemcpp.golem.resource_manager import ResourceManager
from conftest import make_cache_configuration


def test_a_manager_holds_its_cache_manager_and_exposes_its_locations(tmp_path):
    cache_dir = cache_directory.CacheDirectory(location=str(tmp_path / 'cache'))
    cache_manager = get_cache_manager(make_cache_configuration(cache_dir))

    manager = ResourceManager(cache_manager)

    assert manager.cache_manager is cache_manager
    assert manager.locations == cache_manager.locations
