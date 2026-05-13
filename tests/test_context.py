import pytest
from types import SimpleNamespace
import json

from golemcpp.golem import context as golem_context, helpers, qt_discovery
from golemcpp.golem.context import Context


def make_configure_context(project_qt=True, project_qtdir=''):
    context = Context.__new__(Context)
    context.project = SimpleNamespace(
        qt=project_qt,
        qtdir=project_qtdir,
        enable_qt=lambda: None,
    )
    context.context = SimpleNamespace(
        options=SimpleNamespace(
            qtdir='',
            force_version=None,
            runtime_link='shared',
            runtime_variant=None,
            variant='debug',
            link='shared',
            arch='x64',
        ),
        want_qt6=False,
        env=SimpleNamespace(),
        setenv=lambda _: None,
        load=lambda _: None,
    )
    context.version = SimpleNamespace(force_version=lambda _: None)
    context.make_cache_conf = lambda: None
    context.load_recipe = lambda: None
    context.get_tasks_and_targets_to_process = lambda: []
    context.ensures_qt_is_installed = lambda: None
    context.configure_compiler = lambda: None
    context.save_options = lambda: None
    context.is_windows = lambda: False
    context.get_arch = lambda: 'x64'
    return context


def test_configure_autodiscovers_qtdir_when_qt_is_enabled_and_other_sources_are_missing(monkeypatch):
    context = make_configure_context()
    context.get_tasks_and_targets_to_process = lambda: [(SimpleNamespace(features=['QT6CORE'], wfeatures=[]), None)]

    monkeypatch.delenv('QT5_ROOT', raising=False)
    monkeypatch.delenv('QT6_ROOT', raising=False)
    monkeypatch.setattr(context, 'is_qmake_available_on_path', lambda wants_qt6=False: False)
    monkeypatch.setattr(
        qt_discovery,
        'search_for_qt_root_in_default_dirs',
        lambda _, wants_qt6=False: '/opt/Qt/6.7.2/gcc_64' if wants_qt6 else '/opt/Qt/5.15.2/gcc_64',
    )

    context.configure()

    assert context.context.options.qtdir == '/opt/Qt/6.7.2/gcc_64'


def test_configure_skips_qtdir_autodiscovery_when_qmake_or_qt_roots_are_available(monkeypatch):
    test_cases = [
        {'env': {'QT5_ROOT': '/opt/Qt/5.15.2/gcc_64'}, 'qmake': False, 'wants_qt6': False},
        {'env': {'QT6_ROOT': '/opt/Qt/6.7.2/gcc_64'}, 'qmake': False, 'wants_qt6': True},
        {'env': {}, 'qmake': True, 'wants_qt6': False},
    ]

    for test_case in test_cases:
        context = make_configure_context()
        called = {'search': False}
        context.get_tasks_and_targets_to_process = lambda: [(
            SimpleNamespace(
                features=['QT6CORE'] if test_case['wants_qt6'] else ['QT5CORE'],
                wfeatures=['qt6'] if test_case['wants_qt6'] else [],
            ),
            None,
        )]

        monkeypatch.delenv('QT5_ROOT', raising=False)
        monkeypatch.delenv('QT6_ROOT', raising=False)
        for name, value in test_case['env'].items():
            monkeypatch.setenv(name, value)

        monkeypatch.setattr(
            context,
            'is_qmake_available_on_path',
            lambda wants_qt6=False: test_case['qmake'],
        )

        def fake_search(_, wants_qt6=False):
            called['search'] = True
            return '/opt/Qt/6.7.2/gcc_64' if wants_qt6 else '/opt/Qt/5.15.2/gcc_64'

        monkeypatch.setattr(qt_discovery, 'search_for_qt_root_in_default_dirs', fake_search)

        context.configure()

        assert called['search'] is False
        assert context.context.options.qtdir == ''


def test_configure_autodiscovers_qtdir_when_only_other_qt_major_root_is_set(monkeypatch):
    context = make_configure_context()

    monkeypatch.delenv('QT5_ROOT', raising=False)
    monkeypatch.delenv('QT6_ROOT', raising=False)
    monkeypatch.setenv('QT6_ROOT', '/opt/Qt/6.7.2/gcc_64')
    monkeypatch.setattr(context, 'is_qmake_available_on_path', lambda wants_qt6=False: False)

    called = {'search': False}

    def fake_search(_, wants_qt6=False):
        called['search'] = True
        assert wants_qt6 is False
        return '/opt/Qt/5.15.2/gcc_64'

    monkeypatch.setattr(qt_discovery, 'search_for_qt_root_in_default_dirs', fake_search)

    context.configure()

    assert called['search'] is True
    assert context.context.options.qtdir == '/opt/Qt/5.15.2/gcc_64'


def make_runtime_context(*,
                         variant='debug',
                         runtime_link='shared',
                         runtime_variant=None,
                         link='shared'):
    context = Context.__new__(Context)
    context.context = SimpleNamespace(
        options=SimpleNamespace(
            variant=variant,
            runtime_link=runtime_link,
            runtime_variant=runtime_variant,
            link=link,
            arch='x64',
        ),
        env=SimpleNamespace(
            DEFINES=[],
            CXXFLAGS=[],
            CFLAGS=[],
            LINKFLAGS=[],
            ARFLAGS=[],
        ),
    )
    context.is_windows = lambda: True
    context.get_arch = lambda: 'x64'
    context.osname = lambda: 'windows'
    context.compiler_min = lambda: 'm'
    context.is_msvc_like = lambda: True
    return context


def test_runtime_uses_runtime_link_option_and_runtime_variant_defaults_to_variant():
    context = make_runtime_context(variant='release', runtime_link='static')

    assert context.runtime_link() == 'static'
    assert context.runtime_variant() == 'release'


def test_runtime_link_requires_normalized_dependency():
    context = make_runtime_context()

    with pytest.raises(AttributeError):
        context.runtime_link(SimpleNamespace(runtime_variant=None))


def test_restore_options_env_upgrades_legacy_runtime_option():
    context = make_runtime_context()
    context.context.env = SimpleNamespace(
        OPTIONS=json.dumps({
            'runtime': 'static',
            'targets': '',
            'only_update_dependencies_regex': '',
            'output_file': '',
        })
    )
    context.context.options.targets = ''
    context.context.options.output_file = ''
    context.context.options.only_update_dependencies_regex = ''

    restored = context.restore_options_env(context.context.env)

    assert restored['runtime_link'] == 'static'
    assert 'runtime_variant' in restored


def test_build_path_on_windows_includes_runtime_variant_segment():
    context = make_runtime_context(runtime_variant='release')

    assert context.build_path() == 'w64mshrshd'


def test_configure_debug_keeps_debug_flags_with_release_runtime_variant():
    context = make_runtime_context(runtime_variant='release')

    context.configure_debug()

    assert '/MD' in context.context.env.CXXFLAGS
    assert '/MDd' not in context.context.env.CXXFLAGS
    assert '/Od' in context.context.env.CXXFLAGS
    assert '/RTC1' in context.context.env.CXXFLAGS


def test_run_dep_command_forwards_runtime_link_and_runtime_variant(monkeypatch):
    context = make_runtime_context(runtime_variant='release')
    context.resolved_master_dependencies = '/tmp/master-dependencies.json'
    context.get_dep_location = lambda dep, cache_dir: '/tmp/dep-export'
    context.make_repo_ready = lambda dep, cache_dir, should_clean=False: '/tmp/repo'
    context.get_dep_build_location = lambda dep, cache_dir: '/tmp/repo/build'
    context.get_global_dependencies_configuration_file = lambda: '/tmp/global-dependencies.json'
    context.make_cache_dir_option = lambda: '/tmp/cache'
    context.get_only_update_dependencies_regex = lambda: ''
    context.make_define_cache_directories_option = lambda: ''
    context.make_define_static_cache_directories_option = lambda: ''
    context.make_cache_resolution_policy_option = lambda: 'strict'

    dep = SimpleNamespace(
        name='demo',
        version='1.0.0',
        runtime_link=None,
        runtime_variant=None,
        link=None,
        variant=None,
        shallow=False,
        resolved_version='1.0.0',
    )

    calls = []

    monkeypatch.setattr(golem_context.Logs, 'info', lambda *args, **kwargs: None)
    monkeypatch.setattr(helpers, 'make_golem_command', lambda command: [command])
    monkeypatch.setattr(helpers, 'run_task', lambda args, cwd=None, stdout=None: calls.append(args))

    context.run_dep_command(dep=dep, cache_dir='/tmp/cache', command='resolve')

    assert '--runtime-link=shared' in calls[0]
    assert '--runtime-variant=release' in calls[0]
    assert '--runtime=shared' not in calls[0]