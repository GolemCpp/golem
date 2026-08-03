from types import SimpleNamespace

import pytest

from golemcpp.golem import helpers
from golemcpp.golem import network
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


@pytest.mark.parametrize('params', [
    ['clone', '--', 'https://example.test/repo.git', '.'],
    ['fetch', 'origin'],
    ['fetch', '--depth=1', 'origin', 'abcdef'],
    ['pull'],
    ['push', 'origin', 'main'],
    ['ls-remote', '--tags', 'https://example.test/repo.git'],
    ['submodule', 'update', '--init', '--recursive'],
])
def test_is_network_git_command_recognizes_what_reaches_a_remote(params):
    assert helpers.is_network_git_command(['git'] + params) is True


@pytest.mark.parametrize('params', [
    ['init'],
    ['remote', 'add', 'origin', 'https://example.test/repo.git'],
    ['checkout', 'v1.0.0'],
    ['reset', '--hard'],
    ['clean', '-ffxd'],
    ['submodule', 'foreach', '--recursive', 'git', 'clean', '-ffxd'],
    ['describe', '--long', '--tags'],
    ['config', '--get', 'remote.origin.url'],
])
def test_is_network_git_command_leaves_local_commands_alone(params):
    assert helpers.is_network_git_command(['git'] + params) is False


def test_validate_git_command_refuses_a_remote_outside_a_network_scope(tmp_path):
    with pytest.raises(RuntimeError, match='Run golem resolve first'):
        helpers.validate_git_command(
            ['git', 'ls-remote', '--tags', 'https://example.test/repo.git'],
            cwd=str(tmp_path))


def test_validate_git_command_allows_a_remote_inside_a_network_scope(tmp_path):
    with network.allowed():
        helpers.validate_git_command(
            ['git', 'ls-remote', '--tags', 'https://example.test/repo.git'],
            cwd=str(tmp_path))