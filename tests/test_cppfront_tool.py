import os

from golemcpp.golem import cppfront_tool


def test_find_cppfront_cache_uses_cache_directory(tmp_path):
    cache_directory = tmp_path / 'tools-cache'
    cache_dir = cache_directory / cppfront_tool.CPPFRONT_NAME
    repository_dir = cache_dir / 'repository' / 'include'
    executable_path = cache_dir / 'bin' / cppfront_tool.get_cppfront_binary_name()

    repository_dir.mkdir(parents=True)
    executable_path.parent.mkdir(parents=True)
    executable_path.write_text('', encoding='utf-8')

    found = cppfront_tool.find_cppfront_cache(
        cache_directory=str(cache_directory),
    )

    assert found is not None
    assert found.cache_root == str(cache_directory / cppfront_tool.CPPFRONT_NAME)


def test_install_cppfront_writes_into_install_root(monkeypatch, tmp_path):
    cache_directory = tmp_path / 'tools-cache'
    install_root = cache_directory / (cppfront_tool.CPPFRONT_NAME + '.tmp')
    install_root.mkdir(parents=True)

    def fake_run_git(params, cwd, **kwargs):
        if params[0] == 'clone':
            repository_dir = install_root / 'repository'
            (repository_dir / 'include').mkdir(parents=True)
            return
        if params[0] == 'checkout':
            return
        raise AssertionError('Unexpected git command: {}'.format(params))

    def fake_build_cppfront_executable(repository_dir, executable_path):
        os.makedirs(os.path.dirname(executable_path), exist_ok=True)
        with open(executable_path, 'w', encoding='utf-8') as fileout:
            fileout.write('')
        return ['c++']

    monkeypatch.setattr(cppfront_tool.helpers, 'run_git', fake_run_git)
    monkeypatch.setattr(cppfront_tool, 'build_cppfront_executable', fake_build_cppfront_executable)

    result = cppfront_tool.install_cppfront(
        version='v0.8.1',
        install_root=str(install_root),
    )

    assert result is None
    assert (install_root / 'repository').is_dir()
    assert (install_root / 'bin' / cppfront_tool.get_cppfront_binary_name()).is_file()
