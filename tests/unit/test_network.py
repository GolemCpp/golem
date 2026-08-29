from golemcpp.golem import network


def test_reaching_a_remote_is_denied_by_default():
    assert network.is_allowed() is False


def test_allowed_opens_the_scope_and_restores_it_on_the_way_out():
    with network.allowed():
        assert network.is_allowed() is True

    assert network.is_allowed() is False


def test_allowed_restores_the_scope_when_the_block_raises():
    try:
        with network.allowed():
            raise RuntimeError("boom")
    except RuntimeError:
        pass

    assert network.is_allowed() is False


def test_a_nested_scope_leaves_the_outer_one_open():
    with network.allowed():
        with network.allowed():
            assert network.is_allowed() is True

        # A project script opens its own scope inside `golem resolve`, which
        # must still be able to fetch once the script is done.
        assert network.is_allowed() is True

    assert network.is_allowed() is False
