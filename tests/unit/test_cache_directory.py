import os

import pytest

from support import absolute_path
from golemcpp.golem import cache_directory
from golemcpp.golem.setting_descriptor import SettingProcessingContext

PROJECT_DIR = absolute_path("home", "me", "app")
CACHE_DIR = absolute_path("opt", "cache")


def _context(project_dir=PROJECT_DIR):
    return SettingProcessingContext(project_dir=project_dir)


def test_parse_location_keeps_the_whole_value_as_a_path():
    # The primary cache directory is never split, so a directory name may
    # contain an '=' without turning into a regex.
    parsed = cache_directory.parse_location(CACHE_DIR + "=v2", _context())

    assert parsed.location == CACHE_DIR + "=v2"
    assert parsed.regex is None
    assert parsed.is_read_only is False


def test_parse_location_resolves_a_relative_path_against_the_project():
    assert cache_directory.parse_location(
        "local-cache", _context()
    ).location == os.path.join(PROJECT_DIR, "local-cache")


def test_parse_entry_splits_the_url_regex():
    parsed = cache_directory.parse_writable_entry(CACHE_DIR + "=github", _context())

    assert parsed.location == CACHE_DIR
    assert parsed.regex == "github"
    assert parsed.is_read_only is False


def test_parse_entry_resolves_a_relative_path_and_marks_read_only():
    parsed = cache_directory.parse_read_only_entry("shared=github", _context())

    assert parsed.location == os.path.join(PROJECT_DIR, "shared")
    assert parsed.regex == "github"
    assert parsed.is_read_only is True


def test_parse_entry_without_a_regex():
    parsed = cache_directory.parse_writable_entry(CACHE_DIR, _context())

    assert parsed.location == CACHE_DIR
    assert parsed.regex is None


def test_parse_entry_rejects_a_missing_path():
    with pytest.raises(RuntimeError):
        cache_directory.parse_writable_entry("=github", _context())


def test_parse_entry_rejects_an_uncompilable_regex():
    with pytest.raises(Exception):
        cache_directory.parse_writable_entry(CACHE_DIR + "=[unclosed", _context())


def test_format_entry_is_the_reverse_of_parse_entry():
    context = _context()

    for entry in (CACHE_DIR, CACHE_DIR + "=github"):
        parsed = cache_directory.parse_writable_entry(entry, context)
        assert cache_directory.format_entry(parsed, context) == entry

    # A relative entry comes back absolute, which is the point: a forwarded flag
    # must not depend on the directory the reading command runs in.
    parsed = cache_directory.parse_writable_entry("shared=github", context)
    assert (
        cache_directory.format_entry(parsed, context)
        == os.path.join(PROJECT_DIR, "shared") + "=github"
    )
