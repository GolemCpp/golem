import pytest

from golemcpp.golem.build_slug import BuildSlug


def make_slug(**overrides):
    values = dict(
        osystem='linux',
        arch='x86_64',
        compiler='gcc-13.4.0',
        runtime_link='shared',
        runtime_variant='release',
        link='shared',
        variant='release',
    )
    values.update(overrides)
    return BuildSlug(**values)


def test_a_slug_reads_as_the_configuration_it_names():
    assert str(make_slug()) == 'linux~x86_64~gcc-13.4.0~sh~r~sh~r'


@pytest.mark.parametrize(
    'overrides',
    [
        {},
        # An architecture whose ABI is part of its name, so the field itself
        # carries the character `-` would have separated fields with.
        {'arch': 'armv7-eabihf'},
        {'arch': 'riscv64-lp64d'},
        # clang-cl puts two hyphens in the compiler field, which is why no
        # positional split on `-` could have recovered these.
        {'osystem': 'windows', 'compiler': 'clang-cl-19.0.0'},
        {'osystem': 'macos', 'compiler': 'clang-17.0.0', 'arch': 'aarch64'},
        {'runtime_link': 'static', 'link': 'static'},
        {'runtime_variant': 'debug', 'variant': 'debug'},
        # The four short fields are two independent pairs, so a slug has to keep
        # them apart by position.
        {
            'runtime_link': 'static',
            'link': 'shared',
            'runtime_variant': 'release',
            'variant': 'debug',
        },
    ],
)
def test_a_slug_survives_being_read_back(overrides):
    slug = make_slug(**overrides)

    assert BuildSlug.parse(str(slug)) == slug


def test_the_short_fields_stay_in_their_own_pairs():
    slug = make_slug(
        runtime_link='static', link='shared', runtime_variant='release', variant='debug'
    )

    assert str(slug) == 'linux~x86_64~gcc-13.4.0~st~r~sh~d'


def test_a_value_that_could_not_be_read_back_is_refused():
    # Parseability is a property of the type rather than one that usually
    # holds, so the name is never written in the first place.
    with pytest.raises(ValueError, match=r"separates a slug's fields"):
        make_slug(compiler='gcc~13.4.0')


def test_a_field_nobody_named_is_refused():
    # An absent field would name two different builds the same.
    with pytest.raises(ValueError, match=r'needs arch'):
        make_slug(arch='')


@pytest.mark.parametrize(
    'overrides',
    [
        {'variant': 'dev'},
        {'runtime_variant': 'profile'},
        {'link': 'dynamic'},
        {'runtime_link': ''},
    ],
)
def test_a_word_outside_a_closed_vocabulary_is_refused(overrides):
    # These four axes are enumerated. Passing an unknown word through is how
    # an arbitrary string used to reach the slug's last field.
    with pytest.raises(ValueError):
        make_slug(**overrides)


@pytest.mark.parametrize(
    'name',
    [
        # An older format, which is exactly what has to be recognisable: nothing
        # else tells an orphaned directory from a current build.
        'w64mshrshd',
        'linux-x86_64-gcc-13.4.0-sh-r-sh-r',
        # Right shape, wrong words.
        'linux~x86_64~gcc-13.4.0~sh~r~sh~maybe',
        'linux~x86_64~gcc-13.4.0~shared~r~sh~r',
        # Right words, wrong count.
        'linux~x86_64~gcc-13.4.0~sh~r~sh',
        'linux~x86_64~gcc-13.4.0~sh~r~sh~r~r',
        '',
    ],
)
def test_a_name_this_format_did_not_write_is_not_a_slug(name):
    with pytest.raises(ValueError, match=r'is not a build slug'):
        BuildSlug.parse(name)


def test_two_configurations_differing_anywhere_are_named_differently():
    # The contract: the slug names every input that decides whether one
    # artifact can substitute for another.
    slug = make_slug()
    elsewhere = [
        make_slug(osystem='windows'),
        make_slug(arch='i686'),
        make_slug(compiler='gcc-13.4.1'),
        make_slug(runtime_link='static'),
        make_slug(runtime_variant='debug'),
        make_slug(link='static'),
        make_slug(variant='debug'),
    ]

    names = {str(slug)} | {str(other) for other in elsewhere}
    assert len(names) == len(elsewhere) + 1
