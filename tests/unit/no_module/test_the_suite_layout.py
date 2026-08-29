'''
Where a unit test lives says what it is about.

`tests/unit/test_<name>.py` is a promise that `<name>.py` exists. Keeping that
promise checkable is what turns a module renamed in `src` into a failing test
rather than a filename that quietly lies about its subject.
'''

from support import ROOT

# A directory under `tests/unit` names the tree its modules come from. The tree
# is searched rather than mirrored path for path, because the vendored one is
# nested four deep and nobody would write that out.
MODULE_TREES = {
    '': ROOT / 'src' / 'golemcpp' / 'golem',
    'waflib': ROOT / 'waflib',
    'tests': ROOT / 'tests',
}

# The one directory holding tests no module owns: a behaviour several modules
# decide together, or a subject that is not Python at all.
NO_MODULE = 'no_module'

UNIT_DIR = ROOT / 'tests' / 'unit'


def unit_test_files():
    return sorted(UNIT_DIR.rglob('test_*.py'))


def tree_of(test_file):
    '''The directory under `tests/unit` a test file sits in, `''` for none.'''
    relative = test_file.relative_to(UNIT_DIR).parent
    return '' if relative.name == '' else str(relative)


def module_named(name, tree):
    return next(MODULE_TREES[tree].rglob(name + '.py'), None)


def test_every_directory_under_unit_names_a_tree_of_modules():
    trees = {tree_of(f) for f in unit_test_files()}
    unknown = trees - set(MODULE_TREES) - {NO_MODULE}

    assert not unknown, (
        'unknown directories under tests/unit: {}. A directory there names the '
        'tree its modules come from, so add it to MODULE_TREES, or put the '
        'tests in {}/ if no module owns them.'.format(sorted(unknown), NO_MODULE)
    )


def test_every_test_module_is_named_after_a_module_that_exists():
    orphans = []
    for test_file in unit_test_files():
        tree = tree_of(test_file)
        if tree == NO_MODULE:
            continue
        name = test_file.stem[len('test_') :]
        if module_named(name, tree) is None:
            orphans.append(
                '{} wants {}.py under {}'.format(
                    test_file.relative_to(ROOT),
                    name,
                    MODULE_TREES[tree].relative_to(ROOT),
                )
            )

    assert not orphans, (
        'test modules naming a module that does not exist:\n  {}\nRename the '
        'test with the module, or move it to {}/ if nothing owns it.'.format(
            '\n  '.join(orphans), NO_MODULE
        )
    )


def test_no_module_holds_only_tests_no_module_owns():
    misplaced = []
    for test_file in sorted((UNIT_DIR / NO_MODULE).rglob('test_*.py')):
        name = test_file.stem[len('test_') :]
        for tree, root in MODULE_TREES.items():
            found = module_named(name, tree)
            if found is not None:
                misplaced.append(
                    '{} belongs beside {}'.format(
                        test_file.relative_to(ROOT), found.relative_to(ROOT)
                    )
                )

    assert not misplaced, 'tests in {}/ that a module does own:\n  {}'.format(
        NO_MODULE, '\n  '.join(misplaced)
    )


def test_no_two_test_files_share_a_basename():
    # pytest imports a test file by its basename alone, so two of them anywhere
    # in the suite collide. The error it raises names an import mismatch rather
    # than the duplicate, therefore this says which files.
    seen = {}
    collisions = []
    for test_file in sorted((ROOT / 'tests').rglob('test_*.py')):
        first = seen.setdefault(test_file.name, test_file)
        if first != test_file:
            collisions.append(
                '{} and {}'.format(first.relative_to(ROOT), test_file.relative_to(ROOT))
            )

    assert not collisions, 'test files sharing a basename:\n  {}'.format(
        '\n  '.join(collisions)
    )
