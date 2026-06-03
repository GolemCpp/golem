from types import SimpleNamespace

from golemcpp.golem import helpers
from golemcpp.golem.helpers import get_environ


def test_get_environ_returns_none_for_missing_variable(monkeypatch):
    monkeypatch.delenv('GOLEM_TEST_ENV', raising=False)

    assert get_environ('GOLEM_TEST_ENV') is None


def test_get_environ_returns_none_for_empty_variable(monkeypatch):
    monkeypatch.setenv('GOLEM_TEST_ENV', '')

    assert get_environ('GOLEM_TEST_ENV') is None


def test_get_environ_returns_value_for_populated_variable(monkeypatch):
    monkeypatch.setenv('GOLEM_TEST_ENV', 'configured')

    assert get_environ('GOLEM_TEST_ENV') == 'configured'


def test_decode_output_uses_preferred_encoding_when_stdout_encoding_is_missing(monkeypatch):
    monkeypatch.setattr(helpers.sys, 'stdout', SimpleNamespace(encoding=None))
    monkeypatch.setattr(helpers.locale, 'getpreferredencoding', lambda do_setlocale=False: 'utf-8')

    assert helpers.decode_output('café'.encode('utf-8')) == 'café'


def test_remove_tree_handles_windows_style_paths_with_spaces_and_non_ascii(tmp_path):
    directory = tmp_path / 'build 日本 dir'
    directory.mkdir()
    (directory / 'artifact.txt').write_text('content', encoding='utf-8')

    helpers.remove_tree(str(directory))

    assert not directory.exists()