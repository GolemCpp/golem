from golemcpp.golem import main


def test_main_version_flag_prints_golem_version(monkeypatch, capsys):
    monkeypatch.setattr(main.sys, 'argv', ['golem', '--version'])
    monkeypatch.setattr(main.version_command, 'get_golem_version', lambda: '1.2.3')

    def fail_if_called(*args, **kwargs):
        raise AssertionError('Waf entry point should not run for --version')

    monkeypatch.setattr(main.Scripting, 'waf_entry_point', fail_if_called)

    result = main.main()

    assert result == 0

    stdout = capsys.readouterr().out
    assert '=== Golem C++ Build System ===' in stdout
    assert 'golem 1.2.3' in stdout