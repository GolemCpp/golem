from golemcpp.golem import command_version


def test_handle_version_command_prints_golem_version(monkeypatch, capsys):
    monkeypatch.setattr(command_version, 'get_golem_version', lambda: '1.2.3')

    result = command_version.handle_version_command()

    assert result is True
    assert capsys.readouterr().out == 'Golem 1.2.3\n'


def test_get_golem_version_returns_package_metadata(monkeypatch):
    monkeypatch.setattr(command_version, 'package_version', lambda _: '2.3.4')

    assert command_version.get_golem_version() == '2.3.4'


def test_get_golem_version_falls_back_to_default_version(monkeypatch):
    def fail_package_lookup(_: str) -> str:
        raise command_version.PackageNotFoundError()

    monkeypatch.setattr(command_version, 'package_version', fail_package_lookup)

    assert command_version.get_golem_version() == '0.0.0'