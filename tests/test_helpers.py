import subprocess
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
    # Told to work from the objects already here and to fail rather than go looking.
    ['submodule', 'update', '--init', '--recursive', '--no-fetch'],
    ['describe', '--long', '--tags'],
    ['config', '--get', 'remote.origin.url'],
])
def test_is_network_git_command_leaves_local_commands_alone(params):
    assert helpers.is_network_git_command(['git'] + params) is False


def make_git_repository(tmp_path):
    '''Enough of a repository for validate_git_command to let a command through.'''
    git_dir = tmp_path / '.git'
    git_dir.mkdir()
    (git_dir / 'HEAD').write_text('ref: refs/heads/main\n', encoding='utf-8')
    return str(tmp_path)


@pytest.fixture
def git_task(monkeypatch):
    '''What run_git hands to run_task, once it decided about stdout.'''
    recorded = {}
    monkeypatch.setattr(
        helpers, 'run_task',
        lambda args, cwd=None, **kwargs: recorded.update(kwargs))
    return recorded


def test_run_git_drops_stdout_when_asked_to_be_quiet(tmp_path, git_task):
    helpers.run_git(['reset', '--hard'], cwd=make_git_repository(tmp_path), quiet=True)

    assert git_task['stdout'] == subprocess.DEVNULL
    # Only stdout: a failure still has somewhere to be read.
    assert 'stderr' not in git_task


def test_run_git_leaves_a_command_speaking_by_default(tmp_path, git_task):
    helpers.run_git(['reset', '--hard'], cwd=make_git_repository(tmp_path))

    assert git_task == {}


def test_run_git_keeps_the_stdout_a_caller_asked_for(tmp_path, git_task):
    helpers.run_git(['reset', '--hard'], cwd=make_git_repository(tmp_path),
                    quiet=True, stdout=None)

    assert git_task == {'stdout': None}


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