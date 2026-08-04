import os

import pytest

from golemcpp.golem import cache_lock


def lock_path(tmp_path, name='r.lock'):
    return str(tmp_path / 'dependencies' / name)


def test_a_root_nobody_holds_is_walked_into(tmp_path):
    path = lock_path(tmp_path)

    with cache_lock.held(path) as held:
        assert held == path
        # The directory the root will live in, made on the way: a fresh install
        # locks a root before there is anything at it.
        assert os.path.isfile(path)


def test_a_root_somebody_holds_is_waited_for(tmp_path):
    # Two open files, which is what two golem processes are to the kernel.
    path = lock_path(tmp_path)

    with cache_lock.held(path):
        with pytest.raises(RuntimeError, match='Gave up'):
            with cache_lock.held(path, timeout=0):
                pass


def test_a_root_is_let_go_of_when_the_work_raises(tmp_path):
    path = lock_path(tmp_path)

    with pytest.raises(ValueError):
        with cache_lock.held(path):
            raise ValueError('the fetch failed')

    # Taken again straight away: a failure is not a reason to keep a root.
    with cache_lock.held(path, timeout=0):
        pass


def test_the_file_is_left_behind_for_the_next_golem(tmp_path):
    # Removing it is what makes a lock file racy, and an empty file costs nothing:
    # the cache inventory only looks at directories.
    path = lock_path(tmp_path)

    with cache_lock.held(path):
        pass

    assert os.path.isfile(path)

    with cache_lock.held(path, timeout=0):
        pass


def test_two_roots_are_not_waited_for_each_other(tmp_path):
    # Per root: two resources installed at once are two processes doing unrelated
    # work, and there is nothing to protect them from.
    with cache_lock.held(lock_path(tmp_path, 'first.lock')):
        with cache_lock.held(lock_path(tmp_path, 'second.lock'), timeout=0):
            pass
