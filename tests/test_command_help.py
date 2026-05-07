from golemcpp.golem import command_help


def test_handle_help_command_prints_command_summary(capsys):
    command_help.handle_help_command()

    stdout = capsys.readouterr().out

    assert 'Run `golem <command>` from your project root.' in stdout
    assert 'Useful commands:' in stdout
    assert 'init' in stdout
    assert 'configure' in stdout
    assert 'resolve' in stdout
    assert 'dependencies' in stdout
    assert 'build' in stdout
    assert 'package' in stdout
    assert 'clean' in stdout
    assert 'distclean' in stdout
    assert 'Documentation: https://golemcpp.org/docs/' in stdout