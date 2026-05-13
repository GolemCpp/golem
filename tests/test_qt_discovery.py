from pathlib import Path

from golemcpp.golem import qt_discovery
from golemcpp.golem.context import Context


def make_context_for_platform(platform_name):
    context = Context.__new__(Context)
    context.is_windows = lambda: platform_name == 'windows'
    context.is_darwin = lambda: platform_name == 'darwin'
    context.is_linux = lambda: platform_name == 'linux'
    return context


def create_qt_sdk_root(path: Path, core_library_name: str, is_invalid: bool = False) -> None:
    (path / 'bin').mkdir(parents=True)
    (path / 'include' / 'QtCore').mkdir(parents=True)
    (path / 'lib').mkdir(parents=True)
    (path / 'mkspecs').mkdir(parents=True)
    if not is_invalid:
        (path / 'lib' / core_library_name).write_text('')


def test_search_for_qt_root_in_default_dirs_returns_most_recent_valid_sdk(tmp_path, monkeypatch):
    qt_base_dir = tmp_path / 'Qt'
    qt5_root = qt_base_dir / '5.15.2' / 'gcc_64'
    qt6_root = qt_base_dir / '6.7.2' / 'gcc_64'

    create_qt_sdk_root(qt5_root, 'libQt5Core.so')
    create_qt_sdk_root(qt6_root, 'libQt6Core.so')

    context = make_context_for_platform('linux')
    monkeypatch.setattr(
        qt_discovery,
        'list_default_qt_root_installation_dirs',
        lambda _: [str(qt_base_dir)],
    )

    assert qt_discovery.search_for_qt_root_in_default_dirs(context, wants_qt6=False) == str(qt5_root)
    assert qt_discovery.search_for_qt_root_in_default_dirs(context, wants_qt6=True) == str(qt6_root)


def test_search_for_qt_root_in_default_dirs_ignores_invalid_existing_dirs(tmp_path, monkeypatch):
    qt_base_dir = tmp_path / 'Qt'
    invalid_root = qt_base_dir / '6.7.2' / 'gcc_64'

    create_qt_sdk_root(invalid_root, 'libQt6Core.so', is_invalid=True)

    context = make_context_for_platform('linux')
    monkeypatch.setattr(
        qt_discovery,
        'list_default_qt_root_installation_dirs',
        lambda _: [str(qt_base_dir)],
    )

    assert qt_discovery.search_for_qt_root_in_default_dirs(context, wants_qt6=True) is None


def test_search_for_qt_root_in_default_dirs_filters_other_qt_major_versions(tmp_path, monkeypatch):
    qt_base_dir = tmp_path / 'Qt'
    qt6_root = qt_base_dir / '6.7.2' / 'gcc_64'

    create_qt_sdk_root(qt6_root, 'libQt6Core.so')

    context = make_context_for_platform('linux')
    monkeypatch.setattr(
        qt_discovery,
        'list_default_qt_root_installation_dirs',
        lambda _: [str(qt_base_dir)],
    )

    assert qt_discovery.search_for_qt_root_in_default_dirs(context, wants_qt6=False) is None