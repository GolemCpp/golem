import pytest

from golemcpp.golem import helpers
from golemcpp.golem import fetch_policy
from golemcpp.golem.fetch_policy import FetchMode
from golemcpp.golem.fetch_policy import FetchPolicy


def test_every_kind_fetches_the_same_way_unless_told_otherwise():
    # Refreshing is what settles it: every kind has to be refreshable in place,
    # and some follow a branch, so none of them is in a position to want less.
    assert FetchPolicy().fetch_mode == FetchMode.BLOBLESS


def test_a_mode_survives_the_trip_through_a_setting():
    for mode in FetchMode:
        assert fetch_policy.parse_fetch_mode(
            fetch_policy.format_fetch_mode(mode, None), None) == mode


def test_an_unknown_mode_is_refused_rather_than_guessed():
    with pytest.raises(ValueError):
        fetch_policy.parse_fetch_mode('sparse', None)


def test_blobless_needs_a_git_that_can_also_be_told_not_to_phone_home(monkeypatch):
    # Filtering alone is not enough: a git that cannot be told to refuse a lazy
    # fetch cannot keep the boundary the cache is built on, so it takes full.
    monkeypatch.setattr(helpers, 'git_version', lambda: (2, 36, 0))
    assert fetch_policy.supports_blobless() is False
    assert fetch_policy.default_fetch_mode() == FetchMode.FULL

    monkeypatch.setattr(
        helpers, 'git_version', lambda: fetch_policy.BLOBLESS_MINIMUM_GIT_VERSION)
    assert fetch_policy.supports_blobless() is True
    assert fetch_policy.default_fetch_mode() == FetchMode.BLOBLESS


def test_an_unreadable_git_version_takes_the_safe_mode(monkeypatch):
    monkeypatch.setattr(helpers, 'git_version', lambda: (0, 0, 0))

    assert fetch_policy.default_fetch_mode() == FetchMode.FULL


def test_how_many_submodules_at_once_by_default(monkeypatch):
    # One per processor, capped: past a point the remote is the bottleneck.
    monkeypatch.setattr(fetch_policy.os, 'cpu_count', lambda: 4)
    assert fetch_policy.default_fetch_jobs() == 4

    monkeypatch.setattr(fetch_policy.os, 'cpu_count', lambda: 64)
    assert fetch_policy.default_fetch_jobs() == 8

    monkeypatch.setattr(fetch_policy.os, 'cpu_count', lambda: None)
    assert fetch_policy.default_fetch_jobs() == 1
