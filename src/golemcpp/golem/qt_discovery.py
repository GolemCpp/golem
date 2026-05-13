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


def matches_required_qt_major_version(path, wants_qt6=False):
    version = extract_qt_version_from_path(path)
    if version is None:
        return True

    required_major_version = 6 if wants_qt6 else 5
    return version[0] == required_major_version


def is_valid_qt_sdk_root(path, wants_qt6=False):
    required_directories = ['bin', 'include', 'lib', 'mkspecs']
    required_paths = [os.path.join(path, directory) for directory in required_directories]

    if not all(os.path.isdir(required_path) for required_path in required_paths):
        return False

    if not os.path.isdir(os.path.join(path, 'include', 'QtCore')):
        return False

    if not matches_required_qt_major_version(path, wants_qt6=wants_qt6):
        return False

    library_patterns = ['QtCore.framework']
    if wants_qt6:
        library_patterns = ['Qt6Core*', 'libQt6Core*'] + library_patterns
    else:
        library_patterns = ['Qt5Core*', 'libQt5Core*'] + library_patterns

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


def search_for_qt_root_in_default_dirs(context, wants_qt6=False):
    valid_qt_roots = []

    for directory in list_default_qt_sdk_root_candidates(context):
        if is_valid_qt_sdk_root(directory, wants_qt6=wants_qt6):
            valid_qt_roots.append(directory)

    if valid_qt_roots:
        valid_qt_roots.sort(key=make_qt_sdk_sort_key)
        return valid_qt_roots[-1]

    return None