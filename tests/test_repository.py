from golemcpp.golem.repository import Repository


def test_repository_from_url_normalizes_local_path(tmp_path):
    project_dir = tmp_path / 'project dir'
    recipes_dir = project_dir / 'recipes'
    recipes_dir.mkdir(parents=True)

    repository = Repository.from_url('recipes', str(project_dir))

    assert repository.url == recipes_dir.resolve().as_uri()
    assert repository.reference == 'main'


def test_repository_from_url_preserves_explicit_reference(tmp_path):
    project_dir = tmp_path / 'project'
    project_dir.mkdir()

    repository = Repository.from_url(
        'https://github.com/GolemCpp/recipes.git',
        str(project_dir),
        reference='stable')

    assert repository.url == 'https://github.com/GolemCpp/recipes.git'
    assert repository.reference == 'stable'


def test_repository_parses_encoded_local_directory_path(tmp_path):
    project_dir = tmp_path / 'project dir'
    recipes_dir = project_dir / 'recipes #1?x'
    recipes_dir.mkdir(parents=True)

    repository = Repository.from_url('recipes #1?x', str(project_dir))

    assert repository.get_local_path() == str(recipes_dir.resolve())


def test_repository_non_git_directory_detection_ignores_git_repositories(tmp_path):
    project_dir = tmp_path / 'project'
    recipes_dir = project_dir / 'recipes'
    git_dir = recipes_dir / '.git'
    git_dir.mkdir(parents=True)
    (git_dir / 'HEAD').write_text('ref: refs/heads/main\n', encoding='utf-8')

    repository = Repository.from_url('recipes', str(project_dir))

    assert repository.get_non_git_directory_path() is None


def test_repository_cache_key_uses_recipe_id_and_reference():
    repository = Repository(
        url='https://github.com/GolemCpp/recipes.git',
        reference='main')

    assert repository.get_cache_key() == 'recipes@com.github.golemcpp+main'


def test_repository_get_recipe_id_matches_existing_format():
    repository = Repository(url='https://github.com/GolemCpp/recipes.git')

    assert repository.get_recipe_id() == 'recipes@com.github.golemcpp'