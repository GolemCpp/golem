from types import SimpleNamespace

from golemcpp.golem import qt_discovery
from golemcpp.golem.context import Context


def make_configure_context(project_qt=True, project_qtdir=''):
    context = Context.__new__(Context)
    context.project = SimpleNamespace(
        qt=project_qt,
        qtdir=project_qtdir,
        enable_qt=lambda: None,
    )
    context.context = SimpleNamespace(
        options=SimpleNamespace(qtdir='', force_version=None),
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

    monkeypatch.delenv('QT5_ROOT', raising=False)
    monkeypatch.delenv('QT6_ROOT', raising=False)
    monkeypatch.setattr(context, 'is_qmake_available_on_path', lambda: False)
    monkeypatch.setattr(qt_discovery, 'search_for_qt_root_in_default_dirs', lambda _: '/opt/Qt/6.7.2/gcc_64')

    context.configure()

    assert context.context.options.qtdir == '/opt/Qt/6.7.2/gcc_64'


def test_configure_skips_qtdir_autodiscovery_when_qmake_or_qt_roots_are_available(monkeypatch):
    test_cases = [
        {'env': {'QT5_ROOT': '/opt/Qt/5.15.2/gcc_64'}, 'qmake': False},
        {'env': {'QT6_ROOT': '/opt/Qt/6.7.2/gcc_64'}, 'qmake': False},
        {'env': {}, 'qmake': True},
    ]

    for test_case in test_cases:
        context = make_configure_context()
        called = {'search': False}

        monkeypatch.delenv('QT5_ROOT', raising=False)
        monkeypatch.delenv('QT6_ROOT', raising=False)
        for name, value in test_case['env'].items():
            monkeypatch.setenv(name, value)

        monkeypatch.setattr(context, 'is_qmake_available_on_path', lambda: test_case['qmake'])

        def fake_search(_):
            called['search'] = True
            return '/opt/Qt/6.7.2/gcc_64'

        monkeypatch.setattr(qt_discovery, 'search_for_qt_root_in_default_dirs', fake_search)

        context.configure()

        assert called['search'] is False
        assert context.context.options.qtdir == ''