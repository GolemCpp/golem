import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import absolute_path, ROOT
from golemcpp.golem import config_store
from golemcpp.golem import settings
from golemcpp.golem.cache_resolution_policy import CacheResolutionPolicy
from golemcpp.golem.setting_descriptor import SettingDescriptor
from golemcpp.golem import helpers
from golemcpp.golem.fetch_policy import FetchMode


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


def test_settings_are_reachable_from_every_name():
    for setting in settings.SETTINGS:
        assert settings.get_setting(setting.env_name) is setting
        assert settings.get_setting(setting.key) is setting
        assert settings.get_setting_by_env(setting.env_name) is setting
        assert settings.get_setting_by_key(setting.key) is setting
        if setting.option_name:
            assert settings.get_setting(setting.option_name) is setting

    assert set(settings.known_keys()) == {setting.key for setting in settings.SETTINGS}
    assert all(settings.is_known_key(key) for key in settings.known_keys())


def test_get_setting_returns_none_for_unknown_name():
    assert settings.get_setting('GOLEM_UNKNOWN') is None


def read_clean_env(name, prefix=''):
    lines = (ROOT / 'examples' / name).read_text(encoding='utf-8').splitlines()
    return [line[len(prefix):].split('=', 1)[0]
            for line in lines if line.startswith(prefix + 'GOLEM_')]


def test_the_clean_env_scripts_clear_every_setting():
    # They exist to hand a project a session no variable is answering for, which
    # only holds while they list every variable a setting reads.
    expected = [setting.env_name for setting in settings.SETTINGS]

    assert read_clean_env('clean-env') == expected
    assert read_clean_env('clean-env.bat', prefix='set ') == expected


def test_falls_back_to_builtin_default(monkeypatch, tmp_path):
    _isolate_home(monkeypatch, tmp_path)
    monkeypatch.delenv('GOLEM_CACHE_MINIMIZATION_LENGTH', raising=False)

    assert settings.get_settings().get('GOLEM_CACHE_MINIMIZATION_LENGTH') == 8


def test_prefers_option_then_environment_then_store(monkeypatch, tmp_path):
    _isolate_home(monkeypatch, tmp_path)
    project_dir = str(tmp_path / 'project')
    store_cache = absolute_path('store', 'cache')
    env_cache = absolute_path('env', 'cache')
    cli_cache = absolute_path('cli', 'cache')
    config_store.set_value('cache.directory', store_cache, config_store.GLOBAL_SCOPE, project_dir)
    monkeypatch.delenv('GOLEM_CACHE_DIRECTORY', raising=False)

    def resolve(options=None):
        return settings.get_settings(
            options=options, project_dir=project_dir).get('GOLEM_CACHE_DIRECTORY').location

    assert resolve() == store_cache

    monkeypatch.setenv('GOLEM_CACHE_DIRECTORY', env_cache)
    assert resolve() == env_cache

    assert resolve(options=SimpleNamespace(cache_directory=cli_cache)) == cli_cache


def test_local_store_wins_over_global_store(monkeypatch, tmp_path):
    _isolate_home(monkeypatch, tmp_path)
    project_dir = str(tmp_path / 'project')
    global_overlays = absolute_path('global', 'overrides')
    local_overlays = absolute_path('local', 'overrides')
    monkeypatch.delenv('GOLEM_OVERLAYS_LOCATIONS', raising=False)
    manager = settings.get_settings(project_dir=project_dir)

    config_store.set_value('overlays.locations', global_overlays, config_store.GLOBAL_SCOPE, project_dir)
    assert [source.location for source in manager.get('GOLEM_OVERLAYS_LOCATIONS')] == \
        [Path(global_overlays).as_uri()]

    config_store.set_value('overlays.locations', local_overlays, config_store.LOCAL_SCOPE, project_dir)
    assert [source.location for source in manager.get('GOLEM_OVERLAYS_LOCATIONS')] == \
        [Path(local_overlays).as_uri()]


def test_reads_persisted_configure_options(monkeypatch, tmp_path):
    _isolate_home(monkeypatch, tmp_path)
    configured_cache = absolute_path('configured', 'cache')
    cli_cache = absolute_path('cli', 'cache')
    monkeypatch.setenv('GOLEM_CACHE_DIRECTORY', absolute_path('env', 'cache'))
    monkeypatch.setattr(
        settings, 'get_persisted_configure_options',
        lambda build_dir: {'cache_directory': configured_cache})
    build_dir = str(tmp_path / 'build')

    # The persisted option loses to an explicit CLI option but wins over the
    # environment, so a command reached through --build-dir uses the cache the
    # project was configured with.
    assert settings.get_settings(
        build_dir=build_dir).get('GOLEM_CACHE_DIRECTORY').location == configured_cache
    assert settings.get_settings(
        options=SimpleNamespace(cache_directory=cli_cache),
        build_dir=build_dir).get('GOLEM_CACHE_DIRECTORY').location == cli_cache


def test_converts_to_the_setting_type(monkeypatch, tmp_path):
    _isolate_home(monkeypatch, tmp_path)
    monkeypatch.setenv('GOLEM_CACHE_MINIMIZATION_ENABLED', 'off')
    monkeypatch.setenv('GOLEM_CACHE_MINIMIZATION_LENGTH', '16')
    first = absolute_path('first')
    second = absolute_path('second')
    monkeypatch.setenv('GOLEM_ADDITIONAL_CACHE_DIRECTORIES', '{}|{}=github'.format(first, second))
    manager = settings.get_settings()

    assert manager.get('GOLEM_CACHE_MINIMIZATION_ENABLED') is False
    assert manager.get('GOLEM_CACHE_MINIMIZATION_LENGTH') == 16
    assert [(entry.location, entry.regex, entry.is_read_only)
            for entry in manager.get('GOLEM_ADDITIONAL_CACHE_DIRECTORIES')] == [
        (first, None, False), (second, 'github', False)]


def test_reports_an_unparsable_value_with_the_source_it_comes_from(monkeypatch, tmp_path):
    _isolate_home(monkeypatch, tmp_path)
    monkeypatch.setenv('GOLEM_CACHE_MINIMIZATION_LENGTH', 'not-a-number')

    with pytest.raises(ValueError) as error:
        settings.get_settings().get('GOLEM_CACHE_MINIMIZATION_LENGTH')

    assert str(error.value) == (
        "cache.minimization.length expects an integer, got 'not-a-number' "
        '(from environment variable GOLEM_CACHE_MINIMIZATION_LENGTH)')


def test_reports_the_option_and_the_store_an_unparsable_value_comes_from(monkeypatch, tmp_path):
    _isolate_home(monkeypatch, tmp_path)
    monkeypatch.delenv('GOLEM_CACHE_MINIMIZATION_LENGTH', raising=False)
    monkeypatch.delenv('GOLEM_CACHE_MINIMIZATION_ENABLED', raising=False)
    project_dir = str(tmp_path / 'project')
    config_store.set_value(
        'cache.minimization.enabled', 'maybe', config_store.LOCAL_SCOPE, project_dir)

    with pytest.raises(ValueError, match='from option --cache-minimization-length'):
        settings.get_settings(
            options=SimpleNamespace(cache_minimization_length='not-a-number')).get(
                'cache.minimization.length')

    with pytest.raises(ValueError, match='from local configuration key cache.minimization.enabled'):
        settings.get_settings(project_dir=project_dir).get('cache.minimization.enabled')


def test_honors_a_stored_boolean(monkeypatch, tmp_path):
    _isolate_home(monkeypatch, tmp_path)
    monkeypatch.delenv('GOLEM_CACHE_MINIMIZATION_ENABLED', raising=False)
    project_dir = str(tmp_path / 'project')
    config_store.set_value(
        'cache.minimization.enabled', False, config_store.LOCAL_SCOPE, project_dir)

    # A stored False is an answer, not an unset value falling back to the default.
    assert settings.get_settings(
        project_dir=project_dir).get('cache.minimization.enabled') is False


def test_unknown_name_returns_none(monkeypatch, tmp_path):
    _isolate_home(monkeypatch, tmp_path)

    assert settings.get_settings(project_dir=str(tmp_path)).get('GOLEM_UNKNOWN') is None


def test_one_manager_answers_every_setting(monkeypatch, tmp_path):
    _isolate_home(monkeypatch, tmp_path)
    project_dir = str(tmp_path / 'project')
    monkeypatch.delenv('GOLEM_CACHE_DIRECTORY', raising=False)
    monkeypatch.setenv('GOLEM_COOKBOOKS_LOCATIONS', 'https://recipes.git')
    config_store.set_value(
        'cache.resolution-policy', 'weak', config_store.LOCAL_SCOPE, project_dir)

    manager = settings.get_settings(
        options=SimpleNamespace(cache_minimization_length=16), project_dir=project_dir)

    assert manager.get('GOLEM_CACHE_MINIMIZATION_LENGTH') == 16
    assert manager.get('GOLEM_CACHE_RESOLUTION_POLICY') == CacheResolutionPolicy.WEAK
    assert [source.location for source in manager.get('GOLEM_COOKBOOKS_LOCATIONS')] == \
        ['https://recipes.git']
    assert manager.get('GOLEM_CACHE_DIRECTORY').location == settings.get_default_cache_directory_path()


def test_a_location_setting_reads_its_kind(monkeypatch, tmp_path):
    _isolate_home(monkeypatch, tmp_path)
    project_dir = tmp_path / 'project'
    (project_dir / 'my-cookbook').mkdir(parents=True)
    monkeypatch.setenv(
        'GOLEM_COOKBOOKS_LOCATIONS',
        'directory+my-cookbook|git+https://github.com/GolemCpp/recipes.git')

    sources = settings.get_settings(project_dir=str(project_dir)).get(
        'GOLEM_COOKBOOKS_LOCATIONS')

    assert [source.type for source in sources] == ['directory', 'git']
    assert sources[1].location == 'https://github.com/GolemCpp/recipes.git'


def test_a_location_setting_names_the_source_of_a_bad_kind(monkeypatch, tmp_path):
    _isolate_home(monkeypatch, tmp_path)
    monkeypatch.setenv('GOLEM_COOKBOOKS_LOCATIONS', 'gti+https://host/r.git')

    with pytest.raises(ValueError) as error:
        settings.get_settings(project_dir=str(tmp_path)).get('GOLEM_COOKBOOKS_LOCATIONS')

    assert "unknown source kind 'gti'" in str(error.value)
    assert 'environment variable GOLEM_COOKBOOKS_LOCATIONS' in str(error.value)


def test_a_location_setting_forwards_an_explicit_kind(monkeypatch, tmp_path):
    _isolate_home(monkeypatch, tmp_path)
    monkeypatch.setenv('GOLEM_COOKBOOKS_LOCATIONS', 'https://host/r.git')
    monkeypatch.setenv('GOLEM_OVERLAYS_LOCATIONS', 'https://host/o.git')
    manager = settings.get_settings(project_dir=str(tmp_path))

    assert manager.make_flag('GOLEM_COOKBOOKS_LOCATIONS') == \
        ['--cookbook-location=git+https://host/r.git']
    assert manager.make_flag('GOLEM_OVERLAYS_LOCATIONS') == \
        ['--overlay-location=git+https://host/o.git']


def test_parse_value_refuses_a_bad_location_where_it_is_written(monkeypatch, tmp_path):
    _isolate_home(monkeypatch, tmp_path)
    manager = settings.get_settings(project_dir=str(tmp_path))

    with pytest.raises(ValueError):
        manager.parse_value('cookbooks.locations', 'gti+https://host/r.git')

    assert [source.type for source in
            manager.parse_value('cookbooks.locations', 'https://host/r.git')] == ['git']


def test_a_manager_sees_a_value_written_after_it_was_built(monkeypatch, tmp_path):
    _isolate_home(monkeypatch, tmp_path)
    project_dir = str(tmp_path / 'project')
    local_overlays = absolute_path('local', 'overrides')
    monkeypatch.delenv('GOLEM_OVERLAYS_LOCATIONS', raising=False)
    manager = settings.get_settings(project_dir=project_dir)

    assert manager.get('GOLEM_OVERLAYS_LOCATIONS') == []

    config_store.set_value(
        'overlays.locations', local_overlays, config_store.LOCAL_SCOPE, project_dir)

    assert [source.location for source in manager.get('GOLEM_OVERLAYS_LOCATIONS')] == \
        [Path(local_overlays).as_uri()]


def test_legacy_names_keep_resolving(monkeypatch, tmp_path):
    _isolate_home(monkeypatch, tmp_path)
    project_dir = str(tmp_path / 'project')
    setting = SettingDescriptor(
        key='cache.directory',
        env_name='GOLEM_CACHE_DIRECTORY',
        option_name='cache_directory',
        description='',
        legacy_keys=('cache.dir',),
        legacy_env_names=('GOLEM_CACHE_DIR',),
    )
    manager = settings.get_settings(project_dir=project_dir)
    monkeypatch.delenv('GOLEM_CACHE_DIRECTORY', raising=False)
    monkeypatch.setenv('GOLEM_CACHE_DIR', '/legacy/env/cache')

    assert manager.get(setting) == '/legacy/env/cache'

    monkeypatch.delenv('GOLEM_CACHE_DIR', raising=False)
    config_store.set_value('cache.dir', '/legacy/store/cache', config_store.LOCAL_SCOPE, project_dir)
    assert manager.get(setting) == '/legacy/store/cache'

    # The current spelling still wins over the legacy one.
    config_store.set_value('cache.directory', '/current/cache', config_store.LOCAL_SCOPE, project_dir)
    assert manager.get(setting) == '/current/cache'


def test_a_path_setting_resolves_against_the_project(monkeypatch, tmp_path):
    _isolate_home(monkeypatch, tmp_path)
    project_dir = str(tmp_path / 'project')
    monkeypatch.setenv('GOLEM_CACHE_DIRECTORY', 'local-cache')
    monkeypatch.setenv('GOLEM_OVERRIDES_CONFIGURATION', 'overrides.json')
    manager = settings.get_settings(project_dir=project_dir)

    assert manager.get('GOLEM_CACHE_DIRECTORY').location == os.path.join(project_dir, 'local-cache')
    assert manager.get('GOLEM_OVERRIDES_CONFIGURATION') == os.path.join(project_dir, 'overrides.json')


def test_a_malformed_entry_raises_where_it_is_read(monkeypatch, tmp_path):
    _isolate_home(monkeypatch, tmp_path)
    monkeypatch.setenv('GOLEM_ADDITIONAL_CACHE_DIRECTORIES', '=github')
    manager = settings.get_settings(project_dir=str(tmp_path))

    with pytest.raises(RuntimeError):
        manager.get('GOLEM_ADDITIONAL_CACHE_DIRECTORIES')


def test_make_flag_spells_a_value_the_way_a_command_reads_it(monkeypatch, tmp_path):
    _isolate_home(monkeypatch, tmp_path)
    cache_dir = absolute_path('opt', 'cache')
    monkeypatch.setenv('GOLEM_CACHE_DIRECTORY', cache_dir)
    monkeypatch.setenv('GOLEM_CACHE_MINIMIZATION_ENABLED', 'off')
    monkeypatch.setenv('GOLEM_CACHE_MINIMIZATION_LENGTH', '16')
    manager = settings.get_settings(project_dir=str(tmp_path))

    assert manager.make_flag('GOLEM_CACHE_DIRECTORY') == ['--cache-directory={}'.format(cache_dir)]
    assert manager.make_flag('GOLEM_CACHE_MINIMIZATION_ENABLED') == ['--cache-minimization-enabled=off']
    assert manager.make_flag('GOLEM_CACHE_MINIMIZATION_LENGTH') == ['--cache-minimization-length=16']
    assert manager.make_flag('GOLEM_CACHE_RESOLUTION_POLICY') == ['--cache-resolution-policy=strict']


def test_make_flag_repeats_a_list_setting_and_absolutizes_it(monkeypatch, tmp_path):
    _isolate_home(monkeypatch, tmp_path)
    project_dir = str(tmp_path / 'project')
    cache_dir = absolute_path('opt', 'cache')
    monkeypatch.setenv(
        'GOLEM_ADDITIONAL_READ_ONLY_CACHE_DIRECTORIES', 'shared=github|{}'.format(cache_dir))
    manager = settings.get_settings(project_dir=project_dir)

    assert manager.make_flag('GOLEM_ADDITIONAL_READ_ONLY_CACHE_DIRECTORIES') == [
        '--additional-read-only-cache-directory={}=github'.format(os.path.join(project_dir, 'shared')),
        '--additional-read-only-cache-directory={}'.format(cache_dir),
    ]


def test_make_flag_yields_nothing_without_an_option_or_a_value(monkeypatch, tmp_path):
    _isolate_home(monkeypatch, tmp_path)
    monkeypatch.delenv('GOLEM_OVERRIDES_CONFIGURATION', raising=False)
    monkeypatch.delenv('GOLEM_ADDITIONAL_CACHE_DIRECTORIES', raising=False)
    manager = settings.get_settings(project_dir=str(tmp_path))

    assert manager.make_flag('GOLEM_UNKNOWN') == []
    # Unset settings must not be forwarded as empty flags.
    assert manager.make_flag('GOLEM_OVERRIDES_CONFIGURATION') == []
    assert manager.make_flag('GOLEM_ADDITIONAL_CACHE_DIRECTORIES') == []


def test_make_flag_round_trips_through_a_second_settings(monkeypatch, tmp_path):
    # The flag a parent forwards is read back by the sub-command into the same
    # value, which is what makes the forwarding safe.
    _isolate_home(monkeypatch, tmp_path)
    project_dir = str(tmp_path / 'project')
    monkeypatch.setenv('GOLEM_ADDITIONAL_CACHE_DIRECTORIES', 'shared=github')
    flags = settings.get_settings(project_dir=project_dir).make_flag(
        'GOLEM_ADDITIONAL_CACHE_DIRECTORIES')

    monkeypatch.delenv('GOLEM_ADDITIONAL_CACHE_DIRECTORIES')
    entries = [flag.split('=', 1)[1] for flag in flags]
    sub_build = settings.get_settings(
        options=SimpleNamespace(additional_cache_directory=entries),
        project_dir=str(tmp_path / 'elsewhere'))

    resolved = sub_build.get('GOLEM_ADDITIONAL_CACHE_DIRECTORIES')
    assert [(entry.location, entry.regex) for entry in resolved] == [
        (os.path.join(project_dir, 'shared'), 'github')]


def test_a_length_the_setting_cannot_accept_raises(monkeypatch, tmp_path):
    _isolate_home(monkeypatch, tmp_path)
    manager = settings.get_settings(project_dir=str(tmp_path))

    for length in ('0', '-3'):
        monkeypatch.setenv('GOLEM_CACHE_MINIMIZATION_LENGTH', length)
        # A value the type can hold but the setting refuses names its source too.
        with pytest.raises(ValueError, match='GOLEM_CACHE_MINIMIZATION_LENGTH'):
            manager.get('GOLEM_CACHE_MINIMIZATION_LENGTH')


def test_an_unknown_resolution_policy_raises(monkeypatch, tmp_path):
    _isolate_home(monkeypatch, tmp_path)
    monkeypatch.setenv('GOLEM_CACHE_RESOLUTION_POLICY', 'eventually')

    with pytest.raises(ValueError):
        settings.get_settings(project_dir=str(tmp_path)).get('GOLEM_CACHE_RESOLUTION_POLICY')


def test_the_resolution_policy_resolves_to_its_enum(monkeypatch, tmp_path):
    _isolate_home(monkeypatch, tmp_path)
    project_dir = str(tmp_path / 'project')
    monkeypatch.delenv('GOLEM_CACHE_RESOLUTION_POLICY', raising=False)

    def resolve(options=None):
        return settings.get_settings(
            options=options, project_dir=project_dir).get('GOLEM_CACHE_RESOLUTION_POLICY')

    assert resolve() == CacheResolutionPolicy.STRICT

    config_store.set_value(
        'cache.resolution-policy', 'weak', config_store.LOCAL_SCOPE, project_dir)
    assert resolve() == CacheResolutionPolicy.WEAK

    monkeypatch.setenv('GOLEM_CACHE_RESOLUTION_POLICY', 'strict')
    assert resolve() == CacheResolutionPolicy.STRICT

    assert resolve(options=SimpleNamespace(cache_resolution_policy='weak')) == CacheResolutionPolicy.WEAK
    # And it goes back out as the text a sub-build parses.
    assert settings.get_settings(
        options=SimpleNamespace(cache_resolution_policy='weak'),
        project_dir=project_dir).make_flag('GOLEM_CACHE_RESOLUTION_POLICY') == [
            '--cache-resolution-policy=weak']


def test_get_default_processes_the_built_in_default(monkeypatch, tmp_path):
    # Whatever the environment says, the built-in default comes back typed.
    _isolate_home(monkeypatch, tmp_path)
    monkeypatch.setenv('GOLEM_CACHE_RESOLUTION_POLICY', 'weak')
    monkeypatch.setenv('GOLEM_CACHE_MINIMIZATION_LENGTH', '16')
    manager = settings.get_settings(project_dir=str(tmp_path))

    assert manager.get_default('GOLEM_CACHE_RESOLUTION_POLICY') == CacheResolutionPolicy.STRICT
    assert manager.get_default('GOLEM_CACHE_MINIMIZATION_LENGTH') == 8
    assert manager.get_default('GOLEM_CACHE_MINIMIZATION_ENABLED') is True
    assert manager.get_default('GOLEM_UNKNOWN') is None


def test_the_fetch_mode_reads_back_as_a_mode(monkeypatch):
    monkeypatch.setenv('GOLEM_GIT_FETCH_MODE', 'shallow')

    assert settings.get_settings().get('GOLEM_GIT_FETCH_MODE') == FetchMode.SHALLOW


def test_an_unknown_fetch_mode_is_refused(monkeypatch):
    monkeypatch.setenv('GOLEM_GIT_FETCH_MODE', 'sparse')

    with pytest.raises(ValueError):
        settings.get_settings().get('GOLEM_GIT_FETCH_MODE')


def test_the_fetch_mode_default_follows_what_git_can_do(monkeypatch):
    # Asked for explicitly, any mode is honoured; the capability gate only decides
    # what nobody asking gets.
    monkeypatch.delenv('GOLEM_GIT_FETCH_MODE', raising=False)
    monkeypatch.setattr(helpers, 'git_version', lambda: (2, 36, 0))

    assert settings.get_settings().get_default('GOLEM_GIT_FETCH_MODE') == FetchMode.FULL

    monkeypatch.setenv('GOLEM_GIT_FETCH_MODE', 'blobless')
    assert settings.get_settings().get('GOLEM_GIT_FETCH_MODE') == FetchMode.BLOBLESS


def test_the_job_count_reads_back_from_every_source(monkeypatch, tmp_path):
    _isolate_home(monkeypatch, tmp_path)
    monkeypatch.delenv('GOLEM_GIT_JOBS', raising=False)
    project_dir = str(tmp_path / 'project')

    def resolve(options=None):
        return settings.get_settings(
            options=options, project_dir=project_dir).get('GOLEM_GIT_JOBS')

    # Counted from the processors, so what it is worth asserting is the shape.
    assert 1 <= resolve() <= 8

    config_store.set_value('git.jobs', 3, config_store.LOCAL_SCOPE, project_dir)
    assert resolve() == 3

    monkeypatch.setenv('GOLEM_GIT_JOBS', '5')
    assert resolve() == 5

    assert resolve(options=SimpleNamespace(git_jobs=12)) == 12
    # And it goes back out as the text a sub-build parses.
    assert settings.get_settings(
        options=SimpleNamespace(git_jobs=12),
        project_dir=project_dir).make_flag('GOLEM_GIT_JOBS') == ['--git-jobs=12']


def test_a_job_count_that_would_fetch_nothing_is_refused(monkeypatch):
    monkeypatch.setenv('GOLEM_GIT_JOBS', '0')

    with pytest.raises(ValueError, match='positive'):
        settings.get_settings().get('GOLEM_GIT_JOBS')


def test_whether_git_may_prompt_reads_back_from_every_source_it_has(monkeypatch, tmp_path):
    _isolate_home(monkeypatch, tmp_path)
    monkeypatch.delenv('GOLEM_GIT_PROMPT_ENABLED', raising=False)
    project_dir = str(tmp_path / 'project')

    def resolve():
        return settings.get_settings(
            project_dir=project_dir).get('GOLEM_GIT_PROMPT_ENABLED')

    # A prompt nobody is watching looks like a hang, so nobody gets one by default.
    assert resolve() is False

    config_store.set_value(
        'git.prompt.enabled', True, config_store.LOCAL_SCOPE, project_dir)
    assert resolve() is True

    monkeypatch.setenv('GOLEM_GIT_PROMPT_ENABLED', 'off')
    assert resolve() is False


def test_whether_git_may_prompt_is_not_carried_on_a_command_line(monkeypatch, tmp_path):
    # It describes a machine, not a build, and it is read where no options are in
    # hand (see helpers.allow_git_prompt). Having no flag is the decision.
    _isolate_home(monkeypatch, tmp_path)
    monkeypatch.setenv('GOLEM_GIT_PROMPT_ENABLED', 'on')

    assert settings.get_settings().make_flag('GOLEM_GIT_PROMPT_ENABLED') == []


def test_an_unreadable_prompt_setting_is_refused(monkeypatch):
    monkeypatch.setenv('GOLEM_GIT_PROMPT_ENABLED', 'maybe')

    with pytest.raises(ValueError):
        settings.get_settings().get('GOLEM_GIT_PROMPT_ENABLED')


def test_every_git_setting_is_one_golem_config_lists(monkeypatch):
    # `golem config` lists what known_keys answers, so a setting missing from it is
    # a setting nobody can find.
    assert set(settings.known_keys()) >= {
        'git.fetch-mode', 'git.jobs', 'git.prompt.enabled'}
