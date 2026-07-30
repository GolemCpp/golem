import json
import os

from golemcpp.golem import config_store


def _isolate_home(monkeypatch, tmp_path):
    '''
    Points every location get_config_home() may consult at a temporary
    directory, so the tests stay isolated on Windows (%APPDATA%) as well as on
    the other platforms (HOME / XDG_CONFIG_HOME).
    '''
    home = tmp_path / 'home'
    home.mkdir()
    monkeypatch.setenv('HOME', str(home))
    monkeypatch.setenv('APPDATA', str(home / 'AppData' / 'Roaming'))
    monkeypatch.delenv('XDG_CONFIG_HOME', raising=False)
    return home


def test_global_config_path_honors_xdg_config_home(monkeypatch, tmp_path):
    monkeypatch.setattr(config_store.sys, 'platform', 'linux')
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'xdg'))

    assert config_store.get_global_config_path() == str(tmp_path / 'xdg' / 'golem' / 'config.json')


def test_global_config_path_falls_back_to_home(monkeypatch, tmp_path):
    monkeypatch.setattr(config_store.sys, 'platform', 'linux')
    home = _isolate_home(monkeypatch, tmp_path)

    assert config_store.get_global_config_path() == str(home / '.config' / 'golem' / 'config.json')


def test_global_config_path_uses_appdata_on_windows(monkeypatch, tmp_path):
    monkeypatch.setattr(config_store.sys, 'platform', 'win32')
    monkeypatch.setenv('APPDATA', r'C:\Users\Alice\AppData\Roaming')
    # An XDG variable must not win over %APPDATA% on Windows.
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'xdg'))

    assert config_store.get_global_config_path() == os.path.join(
        r'C:\Users\Alice\AppData\Roaming', 'golem', 'config.json')


def test_global_config_path_without_appdata_on_windows_falls_back(monkeypatch, tmp_path):
    monkeypatch.setattr(config_store.sys, 'platform', 'win32')
    monkeypatch.delenv('APPDATA', raising=False)
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'xdg'))

    assert config_store.get_global_config_path() == str(tmp_path / 'xdg' / 'golem' / 'config.json')


def test_global_config_path_ignores_appdata_off_windows(monkeypatch, tmp_path):
    monkeypatch.setattr(config_store.sys, 'platform', 'linux')
    home = _isolate_home(monkeypatch, tmp_path)
    monkeypatch.setenv('APPDATA', r'C:\Users\Alice\AppData\Roaming')

    assert config_store.get_global_config_path() == str(home / '.config' / 'golem' / 'config.json')


def test_local_config_path(tmp_path):
    project_dir = tmp_path / 'demo-project'

    assert config_store.get_local_config_path(str(project_dir)) == str(project_dir / '.golem' / 'config.json')


def test_read_config_missing_file_returns_empty(tmp_path):
    assert config_store.read_config(str(tmp_path / 'nope.json')) == {}


def test_read_config_invalid_file_returns_empty(tmp_path):
    path = tmp_path / 'config.json'
    path.write_text('not json', encoding='utf-8')

    assert config_store.read_config(str(path)) == {}


def test_write_then_read_round_trip(tmp_path):
    path = str(tmp_path / 'nested' / 'config.json')

    config_store.write_config(path, {'overrides.repository': '/opt/overrides'})

    assert os.path.exists(path)
    assert config_store.read_config(path) == {'overrides.repository': '/opt/overrides'}
    with open(path, 'r', encoding='utf-8') as fp:
        assert json.load(fp) == {'overrides.repository': '/opt/overrides'}


def test_write_config_empty_removes_file(tmp_path):
    path = str(tmp_path / 'config.json')
    config_store.write_config(path, {'overrides.repository': '/opt/overrides'})

    config_store.write_config(path, {})

    assert not os.path.exists(path)


def test_set_and_get_local_value(monkeypatch, tmp_path):
    _isolate_home(monkeypatch, tmp_path)
    project_dir = str(tmp_path / 'project')

    config_store.set_value('overrides.repository', '/local/overrides', config_store.LOCAL_SCOPE, project_dir)

    assert config_store.get_scoped_value('overrides.repository', config_store.LOCAL_SCOPE, project_dir) == '/local/overrides'
    assert config_store.get_value('overrides.repository', project_dir) == '/local/overrides'


def test_local_overrides_global(monkeypatch, tmp_path):
    _isolate_home(monkeypatch, tmp_path)
    project_dir = str(tmp_path / 'project')

    config_store.set_value('overrides.repository', '/global/overrides', config_store.GLOBAL_SCOPE, project_dir)
    assert config_store.get_value('overrides.repository', project_dir) == '/global/overrides'

    config_store.set_value('overrides.repository', '/local/overrides', config_store.LOCAL_SCOPE, project_dir)
    assert config_store.get_value('overrides.repository', project_dir) == '/local/overrides'


def test_unset_removes_value_and_reports(monkeypatch, tmp_path):
    _isolate_home(monkeypatch, tmp_path)
    project_dir = str(tmp_path / 'project')

    config_store.set_value('overrides.repository', '/local/overrides', config_store.LOCAL_SCOPE, project_dir)

    assert config_store.unset_value('overrides.repository', config_store.LOCAL_SCOPE, project_dir) is True
    assert config_store.get_scoped_value('overrides.repository', config_store.LOCAL_SCOPE, project_dir) is None
    # File is cleaned up once empty.
    assert not os.path.exists(config_store.get_local_config_path(project_dir))
    # Unsetting again reports nothing removed.
    assert config_store.unset_value('overrides.repository', config_store.LOCAL_SCOPE, project_dir) is False


def test_set_local_without_project_dir_raises(monkeypatch, tmp_path):
    _isolate_home(monkeypatch, tmp_path)

    try:
        config_store.set_value('overrides.repository', '/x', config_store.LOCAL_SCOPE, '')
    except ValueError:
        return
    raise AssertionError('expected ValueError when setting a local value without a project directory')


def test_list_merged_combines_scopes(monkeypatch, tmp_path):
    _isolate_home(monkeypatch, tmp_path)
    project_dir = str(tmp_path / 'project')

    config_store.set_value('cache.directory', '/global/cache', config_store.GLOBAL_SCOPE, project_dir)
    config_store.set_value('overrides.repository', '/global/overrides', config_store.GLOBAL_SCOPE, project_dir)
    config_store.set_value('overrides.repository', '/local/overrides', config_store.LOCAL_SCOPE, project_dir)

    merged = config_store.list_merged(project_dir)

    assert merged == {'cache.directory': '/global/cache', 'overrides.repository': '/local/overrides'}

