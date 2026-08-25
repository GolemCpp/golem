import os
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


def test_remove_tree_handles_a_name_a_command_line_would_split(tmp_path):
    # What a cache root is called: the reference it holds, spelled with the '='
    # cmd breaks a bare command line on.
    directory = tmp_path / '@r@@host#main=0d6e4079'
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
    assert helpers.is_network_git_command(params) is True


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
    assert helpers.is_network_git_command(params) is False


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

    assert 'stdout' not in git_task


def test_run_git_keeps_the_stdout_a_caller_asked_for(tmp_path, git_task):
    helpers.run_git(['reset', '--hard'], cwd=make_git_repository(tmp_path),
                    quiet=True, stdout=None)

    assert git_task['stdout'] is None


# -- how golem runs git, which is not what it validates ---------------------


def test_a_git_command_line_carries_the_options_golem_runs_git_with():
    # Detached is where every resource golem checks out lands, on purpose, so the
    # advice about it is noise.
    assert helpers.git_command_line(['reset', '--hard']) == [
        'git', '-c', 'advice.detachedHead=false', 'reset', '--hard']


def test_the_options_are_not_what_a_command_is_validated_as(tmp_path, monkeypatch):
    # Read from the command itself: an option in front of it would answer for it.
    ran = []
    monkeypatch.setattr(helpers, 'run_task', lambda args, cwd=None, **kwargs: ran.append(args))

    with pytest.raises(RuntimeError, match='Run golem resolve first'):
        helpers.run_git(['fetch', 'origin'], cwd=make_git_repository(tmp_path))

    assert ran == []


# -- what reaches a remote is worth running twice ---------------------------


@pytest.fixture
def no_waiting(monkeypatch):
    '''Every backoff waited out at once, so a test reads what it asserts about.'''
    waited = []
    monkeypatch.setattr(helpers.time, 'sleep', waited.append)
    return waited


def failing_task(failures, attempts):
    '''A command that fails its first `failures` attempts and then succeeds.'''
    def run_task(args, cwd=None, **kwargs):
        attempts.append(args)
        if len(attempts) <= failures:
            raise RuntimeError('early EOF')
    return run_task


def test_a_network_command_is_run_again_after_it_fails(tmp_path, monkeypatch, no_waiting):
    attempts = []
    monkeypatch.setattr(helpers, 'run_task', failing_task(1, attempts))

    with network.allowed():
        helpers.run_git(['fetch', 'origin'], cwd=make_git_repository(tmp_path))

    assert len(attempts) == 2
    assert no_waiting == [helpers.GIT_RETRY_DELAYS[0]]


def test_a_network_command_that_keeps_failing_says_so(tmp_path, monkeypatch, no_waiting):
    # Waited out as many times as there are delays, and no further: a remote that
    # is not answering is an answer.
    attempts = []
    monkeypatch.setattr(helpers, 'run_task', failing_task(99, attempts))

    with network.allowed(), pytest.raises(RuntimeError, match='early EOF'):
        helpers.run_git(['fetch', 'origin'], cwd=make_git_repository(tmp_path))

    assert len(attempts) == len(helpers.GIT_RETRY_DELAYS) + 1
    assert no_waiting == list(helpers.GIT_RETRY_DELAYS)


def test_a_local_command_is_only_run_once(tmp_path, monkeypatch, no_waiting):
    # It failed for what it was asked, and asking again does not change that.
    attempts = []
    monkeypatch.setattr(helpers, 'run_task', failing_task(99, attempts))

    with pytest.raises(RuntimeError, match='early EOF'):
        helpers.run_git(['reset', '--hard'], cwd=make_git_repository(tmp_path))

    assert len(attempts) == 1
    assert no_waiting == []


# -- git is never left waiting for someone to type ---------------------------


def test_git_is_not_allowed_to_ask_for_credentials(monkeypatch):
    # A prompt nobody is watching reads as a hang. An empty GIT_ASKPASS is not an
    # unset one: it is what keeps git from reaching for another asker instead.
    monkeypatch.setattr(helpers, '_git_prompt_allowed', False)

    environment = helpers.git_environment()

    assert environment['GIT_TERMINAL_PROMPT'] == '0'
    assert environment['GIT_ASKPASS'] == ''


def test_nothing_else_about_the_environment_is_golem_s_to_change(monkeypatch):
    # A command inherits everything else it needs, and how it authenticates where
    # git is not the one asking is none of golem's business. Naming what golem
    # adds is what keeps that list from growing quietly.
    monkeypatch.setattr(helpers, '_git_prompt_allowed', False)
    for name in ('GIT_NO_LAZY_FETCH', 'GIT_TERMINAL_PROMPT', 'GIT_ASKPASS'):
        monkeypatch.delenv(name, raising=False)

    inherited = dict(os.environ)
    environment = helpers.git_environment()

    assert {name for name, value in environment.items()
            if inherited.get(name) != value} == {
        'GIT_NO_LAZY_FETCH', 'GIT_TERMINAL_PROMPT', 'GIT_ASKPASS'}
    # Added to, never taken from.
    assert set(environment) >= set(inherited)


def test_git_may_ask_when_a_setting_says_so(monkeypatch):
    # What is asserted is an absence, so the session golem inherits must not be
    # the one answering for it.
    monkeypatch.setattr(helpers, '_git_prompt_allowed', False)
    monkeypatch.delenv('GIT_TERMINAL_PROMPT', raising=False)
    helpers.allow_git_prompt(True)

    assert helpers.is_git_prompt_allowed() is True
    assert 'GIT_TERMINAL_PROMPT' not in helpers.git_environment()


def test_a_git_command_may_not_fetch_what_it_is_missing_on_its_own(monkeypatch):
    # A partial clone completes itself as it goes, and no command name says so.
    monkeypatch.setattr(helpers, '_git_prompt_allowed', False)

    assert helpers.git_environment()['GIT_NO_LAZY_FETCH'] == '1'

    with network.allowed():
        assert 'GIT_NO_LAZY_FETCH' not in helpers.git_environment()


def test_validate_git_command_refuses_a_remote_outside_a_network_scope(tmp_path):
    with pytest.raises(RuntimeError, match='Run golem resolve first'):
        helpers.validate_git_command(
            ['ls-remote', '--tags', 'https://example.test/repo.git'],
            cwd=str(tmp_path))


def test_validate_git_command_allows_a_remote_inside_a_network_scope(tmp_path):
    with network.allowed():
        helpers.validate_git_command(
            ['ls-remote', '--tags', 'https://example.test/repo.git'],
            cwd=str(tmp_path))


# -- and whether there is a repository to run it in -------------------------


def test_a_clone_needs_ground_git_has_nothing_on(tmp_path):
    # Free ground, so there is nothing to refuse.
    with network.allowed():
        helpers.validate_git_command(['clone', '--', 'url', '.'], cwd=str(tmp_path))

        (tmp_path / '.git').mkdir()

        with pytest.raises(RuntimeError, match='Already a git repository'):
            helpers.validate_git_command(['clone', '--', 'url', '.'], cwd=str(tmp_path))


def test_everything_else_needs_a_repository_to_work_in(tmp_path):
    with pytest.raises(RuntimeError, match='Not a git repository'):
        helpers.validate_git_command(['reset', '--hard'], cwd=str(tmp_path))

    helpers.validate_git_command(
        ['reset', '--hard'], cwd=make_git_repository(tmp_path))


def test_every_shape_git_recognises_is_a_repository(tmp_path):
    # One predicate, one clause per shape. A checkout holds `.git` as a
    # directory; a worktree and a submodule checkout hold it as a file naming the
    # git directory they borrow; a bare repository has no `.git` because it is
    # one. Reaching for `.git/HEAD` would answer for the first alone.
    checkout = tmp_path / 'checkout'
    (checkout / '.git').mkdir(parents=True)
    (checkout / '.git' / 'HEAD').write_text('ref: refs/heads/main\n', encoding='utf-8')

    borrowed = tmp_path / 'borrowed'
    borrowed.mkdir()
    (borrowed / '.git').write_text('gitdir: /elsewhere/.git/worktrees/wt\n',
                                   encoding='utf-8')

    bare = tmp_path / 'bare.git'
    bare.mkdir()
    (bare / 'HEAD').write_text('ref: refs/heads/main\n', encoding='utf-8')
    (bare / 'objects').mkdir()
    (bare / 'refs').mkdir()

    for path in (checkout, borrowed, bare):
        assert helpers.is_git_repository(str(path)) is True

    assert helpers.is_git_repository(str(tmp_path)) is False


def test_a_directory_git_started_in_and_left_is_still_a_repository(tmp_path):
    # `.git` without a HEAD, from a clone that died halfway. Enough to refuse the
    # ground for a fresh one; whatever tries to work in it is left to git, which
    # names the path it could not read.
    (tmp_path / '.git').mkdir()

    assert helpers.is_git_repository(str(tmp_path)) is True