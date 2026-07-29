from golemcpp.golem.source import Source


def test_detect_normalizes_and_classifies_local_directory(tmp_path):
    project_dir = tmp_path / 'project dir'
    recipes_dir = project_dir / 'recipes'
    recipes_dir.mkdir(parents=True)

    source = Source.detect('recipes', str(project_dir))

    assert source.location == recipes_dir.resolve().as_uri()
    assert source.type == 'directory'


def test_for_repository_preserves_location_and_reference():
    source = Source.for_repository(
        'https://github.com/GolemCpp/recipes.git', reference='stable')

    assert source.location == 'https://github.com/GolemCpp/recipes.git'
    assert source.reference == 'stable'
    assert source.type == 'git'


def test_detect_parses_encoded_local_directory_path(tmp_path):
    project_dir = tmp_path / 'project dir'
    recipes_dir = project_dir / 'recipes #1'
    recipes_dir.mkdir(parents=True)

    source = Source.detect('recipes #1', str(project_dir))

    assert source.get_local_path() == str(recipes_dir.resolve())


def test_detect_normalizes_local_path_under_non_ascii_parent(tmp_path):
    project_dir = tmp_path / '日本 語 project'
    recipes_dir = project_dir / 'recipes'
    recipes_dir.mkdir(parents=True)

    source = Source.detect('recipes', str(project_dir))

    assert source.location == recipes_dir.resolve().as_uri()
    assert source.get_local_path() == str(recipes_dir.resolve())


def test_generate_recipe_id_accepts_local_path_under_non_ascii_parent(tmp_path):
    project_dir = tmp_path / '日本 語 project'
    recipes_dir = project_dir / 'recipes'
    recipes_dir.mkdir(parents=True)

    recipe_id = Source.generate_recipe_id(str(recipes_dir))

    assert recipe_id.startswith('recipes@fsys.')
    assert 'project' in recipe_id


def test_generate_recipe_id_uses_hash_for_local_path_uniqueness(tmp_path):
    parent_one = tmp_path / 'alpha' / 'recipes'
    parent_two = tmp_path / 'beta' / 'recipes'
    parent_one.mkdir(parents=True)
    parent_two.mkdir(parents=True)

    recipe_id_one = Source.generate_recipe_id(str(parent_one))
    recipe_id_two = Source.generate_recipe_id(str(parent_two))

    assert recipe_id_one != recipe_id_two
    assert recipe_id_one.startswith('recipes@fsys.')
    assert recipe_id_two.startswith('recipes@fsys.')


def test_detect_classifies_local_non_git_directory(tmp_path):
    project_dir = tmp_path / 'project'
    lib_dir = project_dir / 'lib'
    lib_dir.mkdir(parents=True)

    source = Source.detect('lib', str(project_dir))

    assert source.type == 'directory'
    assert source.location == lib_dir.resolve().as_uri()


def test_detect_classifies_git_directory_as_git(tmp_path):
    project_dir = tmp_path / 'project'
    recipes_dir = project_dir / 'recipes'
    git_dir = recipes_dir / '.git'
    git_dir.mkdir(parents=True)
    (git_dir / 'HEAD').write_text('ref: refs/heads/main\n', encoding='utf-8')

    source = Source.detect('recipes', str(project_dir))

    assert source.type == 'git'


def test_for_directory_is_directory_type():
    source = Source.for_directory('/tmp/mylib')
    assert source.type == 'directory'
    assert source.location == '/tmp/mylib'


def test_cache_key_uses_recipe_id_and_reference():
    source = Source.for_repository(
        'https://github.com/GolemCpp/recipes.git', reference='main')

    assert source.get_cache_key() == 'recipes@com.github.golemcpp+main'


def test_get_recipe_id_matches_existing_format():
    source = Source.for_repository('https://github.com/GolemCpp/recipes.git')

    assert source.get_recipe_id() == 'recipes@com.github.golemcpp'


# -- Source as a resource identity (recorded in a manifest) -----------------


def test_to_dict_round_trips_canonical_keys():
    source = Source(
        type='git', location='https://github.com/nlohmann/json.git',
        reference='v3.12.0')

    data = source.to_dict()
    assert data == {'type': 'git', 'location': 'https://github.com/nlohmann/json.git',
                    'reference': 'v3.12.0'}
    assert Source.from_dict(data) == source


def test_from_manifest_reads_source_dict():
    from golemcpp.golem import resource_manifest

    manifest = resource_manifest.ResourceManifest.create(
        kind=resource_manifest.ResourceKind.TOOL,
        cache_key='cppfront',
        source={'type': 'git', 'location': 'u', 'reference': 'v0.8.1'})
    source = Source.from_manifest(manifest)
    assert source.location == 'u'
    assert source.reference == 'v0.8.1'


def test_label_prefers_location_and_reference():
    assert Source(location='https://x/json.git', reference='v3.12.0').label == \
        'https://x/json.git v3.12.0'
    assert Source.for_directory('/tmp/mylib').label == '/tmp/mylib'
    assert Source(location='').label == ''
