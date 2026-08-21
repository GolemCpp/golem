'''
How Golem composes every identity today, out of safe parts.

Golem names a directory or a file after the value it holds: the locator a
resource came from, the revision it resolved to, the dependencies a build was
configured with. That name has to identify the value, so two of them never land
on one name. It is composed of parts, and a part is spelled from something that
came from outside, into something safe on every platform. Spelling is lossy,
therefore a digest follows it when two values would otherwise spell the same.

This is the index of what can happen: every case Golem has to get right, one
corpus per kind of identity. A corpus reads as *(identity, the inputs that
compose it)*, so a group holding several inputs is a merge Golem means, and the
reason a shape comes out as it does sits beside the group it explains.

Three things are asserted over each corpus. Every input composes its group's
identity. No two groups share one, which covers every pair rather than the ones
someone thought to write down. And every identity is a name a filesystem takes.

A case belongs here even when another module already exercises it for its own
reasons: `test_locator.py` keeps the arguments, this keeps the index.

The corpus leans on non-ASCII. Every policy here agrees on ASCII, therefore a
difference between them shows only outside it. A character that reads as an ASCII
neighbour is a named constant written as an escape, because pasting one hides
what it is there for.
'''

import os
import re

import pytest

from golemcpp.golem import advertisement_store
from golemcpp.golem import cache_directory
from golemcpp.golem import cache_manager
from golemcpp.golem import safe_part
from golemcpp.golem.context import Context
from golemcpp.golem.dependency import Dependency
from golemcpp.golem.locator import generate_id
from golemcpp.golem.resource import Resource
from golemcpp.golem.resource_manifest import ResourceKind
from golemcpp.golem.resource_manager import make_revision_part
from golemcpp.golem.source import Source
from conftest import make_cache_configuration


# KELVIN SIGN, whose lowercase is an ASCII 'k'. Substituting before folding turns
# it into the marker, but folding first turns it into a plain 'k', so the order a
# function uses shows only here.
KELVIN = '\u212a'

# LATIN CAPITAL LETTER I WITH DOT ABOVE, whose lowercase is 'i' followed by a
# combining dot. It separates the same two orders.
DOTTED_I = '\u0130'

# What an identity may hold once every part of it is spelled: the safe charset,
# the `.` joining parts, the `@` between the halves, and a digest.
USABLE_NAME = re.compile(r'[0-9a-z._~@-]+(=[0-9a-f]{8})?')


def composes(corpus):
    '''Every input paired with the identity it composes, ready to parametrize.'''
    return [(one, identity) for identity, inputs in corpus for one in inputs]


def assert_no_two_groups_share_an_identity(corpus):
    '''Refuse a corpus where two groups meet, naming both.'''
    seen = {}
    for identity, inputs in corpus:
        assert identity not in seen, '{!r} and {!r} both compose {}'.format(
            inputs, seen[identity], identity)
        seen[identity] = inputs


def assert_is_a_usable_name(identity):
    '''Refuse an identity a filesystem would not give back.'''
    assert USABLE_NAME.fullmatch(identity), identity
    assert identity == identity.lower(), identity
    # Windows strips a trailing dot or space, so a name ending in one is a name
    # golem would not find again.
    assert not identity.endswith('.') and not identity.endswith(' '), identity


# -- locator.generate_id ----------------------------------------------------


LOCATOR_IDENTITIES = [
    # The forge shape, which the id is a published contract for. Every spelling
    # of it lands here: scp-style, no `.git`, a default port written out, and
    # any case, since a forge treats capitals as one owner.
    ('json@com.github.nlohmann', [
        'https://github.com/nlohmann/json.git',
        'https://github.com/nlohmann/json',
        'git@github.com:nlohmann/json.git',
        'ssh://git@github.com/nlohmann/json.git',
        'https://github.com:443/nlohmann/json.git',
        'https://GitHub.com/NLohmann/JSON.git',
    ]),
    # Recipes depend on the fold: these two directories exist in the cookbook.
    ('gsl@com.github.microsoft', ['https://github.com/microsoft/GSL.git']),
    ('sdl@com.github.sdl-mirror', ['https://github.com/SDL-mirror/SDL.git']),
    # Self-hosted on a three-label host is still the forge shape.
    ('repo@com.company.git.org', [
        'https://git.company.com/org/repo.git',
        'ssh://git.company.com/org/Repo.git',
    ]),

    # Off the forge shape the readable half is not enough, so the whole
    # normalized URL is digested behind it.
    ('git@org.kernel.git.pub.scm.git=a88a8ab3',
     ['git://git.kernel.org/pub/scm/git/git.git']),
    ('proj@com.gitlab.group.subgroup=bafa7263',
     ['https://gitlab.com/group/subgroup/proj.git']),
    ('repo@xz.host=e824d735', ['ftps://host.xz/repo.git']),

    # The host/path boundary is not encoded, so a fixed segment count fixes it.
    # Without one, these two would spell the same.
    ('repo@b.a.c', ['https://a.b/c/repo.git']),
    ('repo@b.a.c=39348460', ['https://b/a/c/repo.git']),

    # A literal dot in an owner spells what a path separator spells, so only the
    # digest keeps the two apart.
    ('proj@com.gitlab.group~subgroup=43745eb8',
     ['https://gitlab.com/group.subgroup/proj.git']),

    # An scp path is relative to the named user's home, so a different user is a
    # different repository, and only the digest says so.
    ('repo@xz.host=5e0e9b06', ['alice@host.xz:repo.git']),
    ('repo@xz.host=e9bc533c', ['bob@host.xz:repo.git']),
    ('repo@xz.host=a68c1f4a', ['ssh://host.xz/repo.git']),
    # On an absolute path the user is who authenticates, not what is named — yet
    # the whole-URL digest sweeps it up, so these two are told apart today.
    ('repo@xz.host=0d22d66d', ['ssh://alice@host.xz/repo.git']),
    ('repo@xz.host=70ad7430', ['ssh://bob@host.xz/repo.git']),

    # Two ports on one host are two servers, and the readable half cannot say so.
    ('repo@xz.host.org=ec38cc3a', ['https://host.xz:8443/org/repo.git']),

    # A name may hold a dot, so these two stay legible and stay apart.
    ('socket.io@com.github.org', ['https://github.com/org/socket.io.git']),
    ('socketio@com.github.org', ['https://github.com/org/socketio.git']),

    # `.git` is stripped, so a repository reads one way however it was cloned,
    # and a trailing slash is not a segment.
    ('repo@com.github.org', [
        'https://github.com/org/repo.git',
        'https://github.com/org/repo',
        'https://github.com/org/repo.git/',
    ]),
    # Only one suffix is stripped, so a repository really called `repo.git`
    # keeps its name.
    ('repo.git@com.github.org', ['https://github.com/org/repo.git.git']),
    # The suffix is the one comparison that does not fold case, so these two
    # spellings of one repository do not meet.
    ('x@com.github.org', ['https://github.com/org/x.git']),
    ('x.git@com.github.org', ['https://github.com/org/x.GIT']),
    # A segment that is only the suffix strips to nothing and the level drops to
    # the owner, which names the repository `<path>/.git` belongs to. So these
    # two are one repository wearing two identities, and are meant to meet: what
    # holds them apart is the digest the second carries for missing the forge
    # shape by a segment.
    ('org@com.github', ['https://github.com/org/.git']),
    ('org@com.github=7c22aaa7', ['https://github.com/org']),

    # Substituted before the case is folded: the Kelvin sign becomes the marker
    # rather than the 'k' it lowercases to.
    ('~elvin@com.github.org=b62edad8',
     ['https://github.com/org/' + KELVIN + 'elvin.git']),
    ('kelvin@com.github.org', ['https://github.com/org/kelvin.git']),
    ('repo@com.github.~stanbul=03e8e4d7',
     ['https://github.com/' + DOTTED_I + 'stanbul/repo.git']),
    ('stra~e@com.github.org=33ec1575',
     ['https://github.com/org/Straße.git']),
    # Non-ASCII in a host is substituted, not dropped.
    ('x@h~llo=0671acbf', ['https://héllo/x.git']),
    ('x@hllo=d1b13d6a', ['https://hllo/x.git']),
    # A bracketed host is what NETLOC_BREAKING exists for.
    ('r@~~1.o=7a8f4037', ['https://[::1]/o/r.git']),

    # A local locator has no host to reverse, so its path stands in for one.
    ('mylib@fsys.srv.git', [
        'file:///srv/git/mylib.git',
        '/srv/git/mylib.git',
    ]),
    ('mylib@fsys.tmp', ['file:///tmp/mylib']),
    ('my~lib@fsys.tmp=b3d4d31e', ['file:///tmp/my lib']),
    # `fsys` is not reserved on a remote host, so a real one carries a digest.
    ('mylib@fsys.tmp=120f7f08', ['https://fsys/tmp/mylib']),
    # A Windows drive is a root beside the others, not a directory under one, so
    # `C:/proj` is not the POSIX path `/c/proj`.
    ('mylib@fsys.c.proj=0845cb2c', ['C:/proj/mylib', 'C:\\proj\\mylib']),
    ('mylib@fsys.c.proj', ['file:///c/proj/mylib']),
    ('weird~name@fsys.c.proj=977e0ab8', ['C:\\proj\\weird#name']),

    # A transport helper whose address is a URL names what the URL names.
    ('repo@xz.host=db8fcede', ['hg::https://host.xz/repo']),
    # An address that is not a URL is opaque, so only the digest identifies it.
    ('ext@_no_host_=3c7d39aa', ['ext::sh -c foo']),
    ('bzr@_no_host_=ad1b9067', ['bzr::lp:project']),
    # Naming neither a host nor a path: the name is absent, or lossy.
    ('~repo@_no_host_=d5ef5ee4', [':repo']),
    ('a~@_no_host_=57c327f7', ['a:']),
    # A scheme and a host with no path at all. The last host label is read as the
    # repository name, which names nothing anyone asked for.
    ('host@xz=6c12b139', ['https://host.xz']),
]


@pytest.mark.parametrize('locator, identity', composes(LOCATOR_IDENTITIES))
def test_a_locator_composes_its_identity(locator, identity):
    assert generate_id(locator) == identity


def test_no_two_locators_share_an_identity():
    assert_no_two_groups_share_an_identity(LOCATOR_IDENTITIES)


@pytest.mark.parametrize('identity', [i for i, _ in LOCATOR_IDENTITIES])
def test_a_locator_identity_is_a_usable_name(identity):
    assert_is_a_usable_name(identity)


def test_generate_id_strips_git_without_asking_who_reads_the_path():
    # As a suffix, `.git` names a bare repository by convention. On a filesystem
    # `/a/b/c.git` and `/a/b/c` are two directory entries, so meeting is wrong
    # and this assertion is meant to flip.
    assert generate_id('/a/b/c.git') == generate_id('/a/b/c')

    # As a whole segment it is the git directory of the worktree above it, so
    # these two name one repository and meeting is right.
    assert generate_id('/a/b/c/.git') == generate_id('/a/b/c')


def test_generate_id_collapses_scp_onto_https_on_a_forge():
    # The shape of the locator decides whether the scheme may be discarded: two
    # path segments, a multi-label host, verbatim, a default port. On that shape
    # the scp spelling and the https spelling are one id. Off it, as
    # `host.xz/repo` is, the digest separates them.
    #
    # The collapse says how one server behaves, which nothing here can read: a
    # forge maps both spellings onto one store, but a plain git server with the
    # same layout serves `/home/git/team/proj.git` over scp and
    # `/srv/git/team/proj.git` over https. The first assertion is meant to flip.
    assert (generate_id('git@github.com:nlohmann/json.git')
            == generate_id('https://github.com/nlohmann/json.git'))
    assert (generate_id('git@host.xz:repo.git')
            != generate_id('ssh://host.xz/repo.git'))


def test_generate_id_keeps_a_user_out_of_an_absolute_path():
    # Who authenticates does not change which repository an absolute path names,
    # so these are one repository wearing two ids. The merge is deliberate and
    # this assertion is meant to flip.
    assert (generate_id('ssh://alice@host.xz/repo.git')
            != generate_id('ssh://bob@host.xz/repo.git'))


# -- resource_manager.make_revision_part ------------------------------------


REVISION_IDENTITIES = [
    # An object name is abbreviated and nothing else. It carries no digest,
    # because the revisions of one repository cached side by side are few enough
    # that a prefix tells them apart.
    ('aaaaaaa', ['a' * 40]),
    ('bbbbbbb', ['b' * 64]),

    # Everything else is a reference, always digested, because the spelling is
    # lossy and the readable half is cut at 40.
    ('main=0d6e4079', ['main']),
    ('v1.0.0=2485f4d5', ['v1.0.0']),
    ('release~1.2.3=88ded651', ['release/1.2.3']),
    # Spelled like a short object name, but a reference, so it is digested.
    ('deadbeef=2baf1f40', ['deadbeef']),
    ('caf~=850f7dc4', ['café']),
    ('stra~e=58a3778c', ['Straße']),
    ('x' * 40 + '=aa20c23e', ['x' * 200]),

    # Substituted before the case is folded, as generate_id does: the Kelvin sign
    # and the dotted I become the marker rather than the ASCII letters they
    # lowercase to, so the readable halves already differ.
    ('~elvin=4a274a98', [KELVIN + 'elvin']),
    ('kelvin=03105d50', ['kelvin']),
    ('~stanbul=24ec8f72', [DOTTED_I + 'stanbul']),
]


@pytest.mark.parametrize('revision, identity', composes(REVISION_IDENTITIES))
def test_a_revision_composes_its_identity(revision, identity):
    assert make_revision_part(revision) == identity


def test_no_two_revisions_share_an_identity():
    assert_no_two_groups_share_an_identity(REVISION_IDENTITIES)


@pytest.mark.parametrize('identity', [i for i, _ in REVISION_IDENTITIES])
def test_a_revision_identity_is_a_usable_name(identity):
    assert_is_a_usable_name(identity)


def test_make_revision_part_substitutes_before_folding():
    # The Kelvin sign becomes the marker rather than the ASCII 'k' it lowercases
    # to, so the readable halves differ and the digest is no longer the only
    # thing holding the two apart.
    kelvin = make_revision_part(KELVIN + 'elvin')
    ascii_k = make_revision_part('kelvin')

    assert kelvin.split('=')[0] == '~elvin'
    assert ascii_k.split('=')[0] == 'kelvin'
    assert kelvin != ascii_k


# -- advertisement_store.path_for -------------------------------------------


# An id long enough to be cut, and the longest one that is not. A local locator
# spells a whole path, which has no bound where a file name does.
AT_THE_LIMIT = 'https://a.io/o/' + 'x' * (safe_part.READABLE_LENGTH - len('@io.a.o'))
PAST_THE_LIMIT = AT_THE_LIMIT + 'x'


ADVERTISEMENT_IDENTITIES = [
    # One file for both spellings, since generate_id composes one id from them.
    ('json@com.github.nlohmann', ['https://github.com/nlohmann/json.git',
                                  'git@github.com:nlohmann/json.git']),
    ('ext@_no_host_=3c7d39aa', ['ext::sh -c foo']),
    ('mylib@fsys.very-long-directory-name.very=dda64374',
     ['file:///' + 'very-long-directory-name/' * 4 + 'mylib.git']),
    # Exactly at the limit passes through; one character past it is cut, and the
    # digest of the whole id takes over from there.
    ('x' * 33 + '@io.a.o', [AT_THE_LIMIT]),
    ('x' * 34 + '@io.a.=73558728', [PAST_THE_LIMIT]),
]


@pytest.mark.parametrize('url, identity', composes(ADVERTISEMENT_IDENTITIES))
def test_an_advertisement_composes_its_identity(tmp_path, url, identity):
    with advertisement_store.shared(str(tmp_path / 'resolve')):
        assert os.path.basename(advertisement_store.path_for(url)) == identity


def test_no_two_advertisements_share_an_identity():
    assert_no_two_groups_share_an_identity(ADVERTISEMENT_IDENTITIES)


@pytest.mark.parametrize('identity', [i for i, _ in ADVERTISEMENT_IDENTITIES])
def test_an_advertisement_identity_is_a_usable_name(identity):
    assert_is_a_usable_name(identity)


# -- cache_manager.make_minimized_resource_name -----------------------------
#
# Not read as a corpus of groups: a pure hash read at two lengths is two
# queries rather than one identity two inputs compose.


def make_manager(tmp_path):
    '''A manager over one writable cache, since the name is all that is read.'''
    return cache_manager.get_cache_manager(make_cache_configuration(
        cache_directory.CacheDirectory(location=str(tmp_path), is_read_only=False)))


@pytest.mark.parametrize('kind, cache_key, at_eight, at_sixteen', [
    (ResourceKind.DEPENDENCY, 'json@com.github.nlohmann+65ee6845',
     '94291280', '942912806ef94545'),
    (ResourceKind.COOKBOOK, 'recipes@com.github.golemcpp+main=0d6e4079',
     '5202c34e', '5202c34e0a52a4f1'),
    (ResourceKind.TOOL, 'cppfront', '0a9ecbb3', '0a9ecbb3def8025f'),
])
def test_make_minimized_resource_name_names(tmp_path, kind, cache_key,
                                            at_eight, at_sixteen):
    manager = make_manager(tmp_path)
    resource = Resource(kind=kind, cache_key=cache_key, source=Source())

    # A pure hash, so the length says how much of it is kept rather than which
    # hash it is.
    assert manager.make_minimized_resource_name(resource, 8) == at_eight
    assert manager.make_minimized_resource_name(resource, 16) == at_sixteen
    assert at_sixteen.startswith(at_eight)


def test_make_minimized_resource_name_separates_kinds(tmp_path):
    # The subdir is hashed with the key, which is what keeps two kinds apart
    # once the per-kind directory is dropped.
    manager = make_manager(tmp_path)
    key = 'same@com.github.org'

    names = {manager.make_minimized_resource_name(
        Resource(kind=kind, cache_key=key, source=Source()), 8)
        for kind in ResourceKind}

    assert len(names) == len(ResourceKind)


# -- context.make_dependencies_slug -----------------------------------------


JSON = ('json', 'https://github.com/nlohmann/json.git', '^3.0.0')
SPDLOG = ('spdlog', 'https://github.com/gabime/spdlog.git', '1.12.0')


def make_dependencies(*declared):
    '''The dependencies a corpus entry declares, each name/repository/version
    optionally followed by what it is built as.'''
    made = []
    for name, repository, version, *built_as in declared:
        made.append(Dependency(name=name, repository=repository,
                               version=version,
                               **(built_as[0] if built_as else {})))
    return made


SLUG_IDENTITIES = [
    ('e3b0c442', [()]),
    ('2d1c519b', [(JSON,)]),
    ('6c475ef9', [(JSON, SPDLOG)]),
    # Order is part of the slug: the strings are concatenated, not sorted.
    ('73adb607', [(SPDLOG, JSON)]),
    # The slug names a build, so what a dependency is built as belongs in it.
    # Two lists differing only in linkage are two builds, and `bin-<slug>` has
    # to hold them apart.
    ('94023ed6', [(JSON + ({'link': 'shared'},),)]),
    ('4a57854f', [(JSON + ({'link': 'static'},),)]),
]


@pytest.mark.parametrize('dependencies, identity', composes(SLUG_IDENTITIES))
def test_a_dependency_list_composes_its_identity(dependencies, identity):
    context = Context.__new__(Context)

    assert context.make_dependencies_slug(
        make_dependencies(*dependencies)) == identity


def test_no_two_dependency_lists_share_an_identity():
    assert_no_two_groups_share_an_identity(SLUG_IDENTITIES)


@pytest.mark.parametrize('identity', [i for i, _ in SLUG_IDENTITIES])
def test_a_slug_identity_is_a_usable_name(identity):
    assert_is_a_usable_name(identity)
