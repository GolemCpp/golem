from golemcpp.golem.helpers import get_environ


def test_get_environ_returns_none_for_missing_variable(monkeypatch):
    monkeypatch.delenv('GOLEM_TEST_ENV', raising=False)

    assert get_environ('GOLEM_TEST_ENV') is None


def test_get_environ_returns_none_for_empty_variable(monkeypatch):
    monkeypatch.setenv('GOLEM_TEST_ENV', '')

    assert get_environ('GOLEM_TEST_ENV') is None


def test_get_environ_returns_value_for_populated_variable(monkeypatch):
    monkeypatch.setenv('GOLEM_TEST_ENV', 'configured')

    assert get_environ('GOLEM_TEST_ENV') == 'configured'