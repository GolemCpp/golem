import glob
import os
import re
from collections import OrderedDict
from pathlib import Path


def list_subdirectories(path):
    if not os.path.isdir(path):
        return []

    try:
        return [entry.path for entry in os.scandir(path) if entry.is_dir()]
    except OSError:
        return []


def extract_qt_version_from_path(path):
    versions = []

    for part in Path(path).parts:
        normalized_part = part.lower()

        if re.fullmatch(r'\d+(?:\.\d+)+', normalized_part):
            versions.append(tuple(int(value) for value in normalized_part.split('.')))
            continue

        version_match = re.fullmatch(r'qt[-_]?(\d+(?:\.\d+)*)', normalized_part)
        if version_match:
            versions.append(
                tuple(int(value) for value in version_match.group(1).split('.'))
            )

    if not versions:
        return None

    return max(versions)


def is_valid_qt_sdk_root(path):
    required_directories = ['bin', 'include', 'lib', 'mkspecs']
    required_paths = [os.path.join(path, directory) for directory in required_directories]

    if not all(os.path.isdir(required_path) for required_path in required_paths):
        return False

    if not os.path.isdir(os.path.join(path, 'include', 'QtCore')):
        return False

    library_patterns = [
        'Qt5Core*',
        'Qt6Core*',
        'libQt5Core*',
        'libQt6Core*',
        'QtCore.framework',
    ]

    for pattern in library_patterns:
        if glob.glob(os.path.join(path, 'lib', pattern)):
            return True

    return False


def list_default_qt_root_installation_dirs(context):
    dirs = []
    if context.is_windows():
        dirs += ['C:\\Qt', 'C:\\Program Files\\Qt', 'C:\\Program Files (x86)\\Qt']
    elif context.is_darwin():
        dirs += [
            '/Applications/Qt',
            '/usr/local/opt/qt',
            '/usr/local/opt/qt5',
            '/usr/local/opt/qt6',
            '/opt/homebrew/opt/qt',
            '/opt/homebrew/opt/qt5',
            '/opt/homebrew/opt/qt6',
        ]
    elif context.is_linux():
        dirs += [
            '/opt/Qt',
            '/opt/qt',
            '/usr/local/qt',
            '/usr/local/qt5',
            '/usr/local/qt6',
            '/usr/local/opt/qt',
            '/usr/local/opt/qt5',
            '/usr/local/opt/qt6',
            '/usr/lib/qt5',
            '/usr/lib/qt6',
        ]
    return dirs


def list_default_qt_sdk_root_candidates(context):
    candidates = []

    for root_dir in list_default_qt_root_installation_dirs(context):
        candidates.append(root_dir)
        for child_dir in list_subdirectories(root_dir):
            candidates.append(child_dir)
            candidates += list_subdirectories(child_dir)

    return list(OrderedDict.fromkeys(candidates))


def make_qt_sdk_sort_key(path):
    version = extract_qt_version_from_path(path)
    if version is None:
        return (0, tuple(), path)
    return (1, version, path)


def search_for_qt_root_in_default_dirs(context):
    valid_qt_roots = []

    for directory in list_default_qt_sdk_root_candidates(context):
        if is_valid_qt_sdk_root(directory):
            valid_qt_roots.append(directory)

    if valid_qt_roots:
        valid_qt_roots.sort(key=make_qt_sdk_sort_key)
        return valid_qt_roots[-1]

    return None