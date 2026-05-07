from golemcpp.golem import command_version


def test_handle_version_command_prints_golem_version(monkeypatch, capsys):
    monkeypatch.setattr(command_version, 'get_golem_version', lambda: '1.2.3')

    result = command_version.handle_version_command()

    assert result is True
    assert capsys.readouterr().out == 'golem 1.2.3\n'


def test_get_golem_version_falls_back_to_repo_version(monkeypatch):
    def fail_package_lookup(_: str) -> str:
        raise command_version.PackageNotFoundError()

    class DummyVersion:
        def __init__(self, working_dir=None):
            self.semver = '9.8.7'

    monkeypatch.setattr(command_version, 'package_version', fail_package_lookup)
    monkeypatch.setattr(command_version, 'Version', DummyVersion)

    assert command_version.get_golem_version() == '9.8.7'