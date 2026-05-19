
import os
from types import SimpleNamespace
from golemcpp.golem import tools_cache

def make_options(**kwargs):
    defaults = {
        'tools_cache_directory': '',
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)

def test_cache_defaults_under_home_cache(tmp_path, monkeypatch):
    home_dir = tmp_path / 'home'
    home_dir.mkdir()
    monkeypatch.setenv('HOME', str(home_dir))

    tools_cache_directory = tools_cache.get_cache_directory(
        project_dir=str(tmp_path),
        options=make_options(),
    )

    assert tools_cache_directory == os.path.join(str(home_dir), '.cache', 'golem', 'tools')
    
def test_get_cache_directory_prefers_environment_variable(tmp_path, monkeypatch):
    monkeypatch.setenv('GOLEM_TOOLS_CACHE_DIRECTORY', '/tmp/env-tools-cache')

    tools_cache_directory = tools_cache.get_cache_directory(
        project_dir=str(tmp_path),
        options=make_options(),
    )

    assert tools_cache_directory == '/tmp/env-tools-cache'


def test_get_cache_directory_prefers_explicit_option(tmp_path, monkeypatch):
    monkeypatch.setenv('GOLEM_TOOLS_CACHE_DIRECTORY', '/tmp/env-tools-cache')

    tools_cache_directory = tools_cache.get_cache_directory(
        project_dir=str(tmp_path),
        options=make_options(tools_cache_directory='relative-tools-cache'),
    )

    assert tools_cache_directory == str(tmp_path / 'relative-tools-cache')