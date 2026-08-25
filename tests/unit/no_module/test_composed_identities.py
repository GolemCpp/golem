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

An input has to mean the same thing wherever the suite runs. A bare POSIX path
does not: `os.path.abspath` resolves it against the current drive on Windows.
Spell those as `file://` URLs, which never reach `abspath`. The same rules out
a UNC path, which is a relative name on Linux and a share on Windows.

The corpus leans on non-ASCII. Every policy here agrees on ASCII, therefore a
difference between them shows only outside it. A character that reads as an ASCII
neighbour is a named constant written as an escape, because pasting one hides
what it is there for.
'''

import os
import re
from pathlib import Path

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
from golemcpp.golem.source_id import SourceId
from support import make_cache_configuration


# KELVIN SIGN, whose lowercase is an ASCII 'k'. Substituting before folding turns
# it into the marker, but folding first turns it into a plain 'k', so the order a
# function uses shows only here.
KELVIN = '\u212a'

# LATIN CAPITAL LETTER I WITH DOT ABOVE, whose lowercase is 'i' followed by a
# combining dot. It separates the same two orders.
DOTTED_I = '\u0130'

# What an identity may hold once every part of it is spelled: the safe charset,
# the `.` joining parts inside a field, the `@` between fields, and a digest
# bound to any of them. Broad on purpose, this asks whether a filesystem would
# give the name back, not whether it is a well-formed identity, since a revision
# and an advertisement file name are neither.
USABLE_NAME = re.compile(r'[0-9a-z._~@=-]+')


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
    # The forge shape, which the identity is a published contract for. Every
    # spelling of it lands here: no `.git`, a default port written out, any
    # case since a forge treats capitals as one owner, and any scheme, since a
    # scheme is a road to a server rather than a different server.
    ('@json@nlohmann@github.com', [
        'https://github.com/nlohmann/json.git',
        'https://github.com/nlohmann/json',
        'git://github.com/nlohmann/json.git',
        'ssh://git@github.com/nlohmann/json.git',
        'https://github.com:443/nlohmann/json.git',
        'https://GitHub.com/NLohmann/JSON.git',
    ]),
    # Recipes depend on the fold: these two directories exist in the cookbook.
    ('@gsl@microsoft@github.com', ['https://github.com/microsoft/GSL.git']),
    ('@sdl@sdl-mirror@github.com', ['https://github.com/SDL-mirror/SDL.git']),
    # Self-hosted on a three-label host is no different: the host is one field
    # however many labels it holds.
    ('@repo@org@git.company.com', [
        'https://git.company.com/org/repo.git',
        'ssh://git.company.com/org/Repo.git',
    ]),

    # A path of any depth stays readable.
    ('@git@pub.scm.git@git.kernel.org',
     ['git://git.kernel.org/pub/scm/git/git.git']),
    ('@proj@group.subgroup@gitlab.com',
     ['https://gitlab.com/group/subgroup/proj.git']),
    ('@repo@@host.xz', [
        'ftps://host.xz/repo.git',
        'ssh://host.xz/repo.git',
        # The path is absolute, so who authenticates does not change which
        # repository it names.
        'ssh://alice@host.xz/repo.git',
        'ssh://bob@host.xz/repo.git',
        # A transport helper whose address is a URL names what the URL names.
        'hg::https://host.xz/repo',
    ]),

    # The boundary is spelled now, so these two need no digest to stay apart.
    ('@repo@c@a.b', ['https://a.b/c/repo.git']),
    ('@repo@a.c@b', ['https://b/a/c/repo.git']),

    # A literal dot in an owner spells what a path separator spells, so only the
    # digest keeps the two apart.
    ('@proj@group~subgroup=75085152@gitlab.com',
     ['https://gitlab.com/group.subgroup/proj.git']),

    # An scp path is relative to the named user's home, so the user is part of
    # the root rather than someone who authenticates.
    ('@repo@@host.xz@scp.alice', ['alice@host.xz:repo.git']),
    ('@repo@@host.xz@scp.bob', ['bob@host.xz:repo.git']),
    ('@repo@@host.xz@scp', ['host.xz:repo.git']),
    # Which is why the forge collapse is gone: golem cannot tell a forge from a
    # plain git server serving two different paths over the two transports.
    ('@json@nlohmann@github.com@scp.git', ['git@github.com:nlohmann/json.git']),
    ('@repo@deep.path@host.xz@scp.git', ['git@host.xz:deep/path/repo.git']),

    # Two ports on one host are two servers, and the readable half cannot say
    # so. Digested over the host and the port that were read: the userinfo an
    # absolute URL discards cannot come back in, the case folds as everywhere
    # else, and a leading zero is not a different port.
    ('@repo@o@host.xz=62c09d99', [
        'https://host.xz:8443/o/repo.git',
        'https://HOST.XZ:8443/o/repo.git',
        'https://host.xz:08443/o/repo.git',
        'https://alice@host.xz:8443/o/repo.git',
        'https://bob@host.xz:8443/o/repo.git',
    ]),
    # A port urlparse cannot read is carried as text rather than dropped, or it
    # merges onto the no-port spelling below.
    ('@repo@o@host.example.com=d15741ed',
     ['ssh://host.example.com:99999/o/repo.git']),
    ('@repo@o@host.example.com', ['ssh://host.example.com/o/repo.git']),

    # A name may hold a dot, so these two stay legible and stay apart.
    ('@socket.io@org@github.com', ['https://github.com/org/socket.io.git']),
    ('@socketio@org@github.com', ['https://github.com/org/socketio.git']),

    # On a remote, `.git` is a server convention and a trailing slash is not a
    # segment.
    ('@repo@org@github.com', [
        'https://github.com/org/repo.git',
        'https://github.com/org/repo',
        'https://github.com/org/repo.git/',
    ]),
    # Only one suffix comes off, so a repository really called `repo.git` keeps
    # its name, and the comparison folds case like every other one.
    ('@repo.git@org@github.com', ['https://github.com/org/repo.git.git']),
    ('@x@org@github.com', [
        'https://github.com/org/x.git',
        'https://github.com/org/x.GIT',
    ]),
    # A whole `.git` segment is the git directory of the worktree above it, so
    # it names that repository. A fact about git, not a convention.
    ('@org@@github.com', [
        'https://github.com/org/.git',
        'https://github.com/org',
    ]),

    # Substituted before the case is folded: the Kelvin sign becomes the marker
    # rather than the 'k' it lowercases to.
    ('@~elvin=4a274a98@org@github.com',
     ['https://github.com/org/' + KELVIN + 'elvin.git']),
    ('@kelvin@org@github.com', ['https://github.com/org/kelvin.git']),
    ('@repo@~stanbul=24ec8f72@github.com',
     ['https://github.com/' + DOTTED_I + 'stanbul/repo.git']),
    ('@stra~e=58a3778c@org@github.com', ['https://github.com/org/Straße.git']),
    # Non-ASCII in a host is substituted, not dropped, and the digest is the
    # host field's own.
    ('@x@@h~llo=3c48591d', ['https://héllo/x.git']),
    ('@x@@hllo', ['https://hllo/x.git']),
    # A bracketed host is what NETLOC_BREAKING exists for.
    ('@r@o@~~1=eff8e7ca', ['https://[::1]/o/r.git']),

    # On a filesystem `.git` is a suffix golem may not assume away: two entries
    # may both exist, and merging them is not golem's to do.
    ('@mylib.git@srv.git@_local_', ['file:///srv/git/mylib.git']),
    ('@mylib@srv.git@_local_', ['file:///srv/git/mylib']),
    ('@c.git@a.b@_local_', ['file:///a/b/c.git']),
    # The whole segment still drops, on a filesystem as on a server.
    ('@c@a.b@_local_', ['file:///a/b/c/.git', 'file:///a/b/c']),

    # A local locator says so in the field answering "which host", rather than
    # putting its whole path there.
    ('@mylib@tmp@_local_', ['file:///tmp/mylib']),
    ('@my~lib=4c0e2565@tmp@_local_', ['file:///tmp/my lib']),
    # A host really spelled like a sentinel says it is not one.
    ('@mylib@tmp@_local_=dc7e35f8', ['https://_local_/tmp/mylib']),
    ('@repo@@_nohost_=068275a3', ['https://_nohost_/repo.git']),

    # A Windows drive is a root beside the others rather than a directory under
    # one, so `C:/proj` is not the POSIX path `/c/proj`.
    ('@mylib@proj@_local_@drive.c', ['C:/proj/mylib', 'C:\\proj\\mylib']),
    ('@mylib@c.proj@_local_', ['file:///c/proj/mylib']),
    ('@weird~name=42741819@proj@_local_@drive.c', ['C:\\proj\\weird#name']),

    # An address that is not a URL has no hierarchy to read, so the rooting
    # field is a bare digest: the escape hatch, with nothing readable in front.
    ('@ext@@_nohost_@=3c7d39aa', ['ext::sh -c foo']),
    ('@bzr@@_nohost_@=ad1b9067', ['bzr::lp:project']),
    # Naming neither a host nor a path: the name is what is left, and it is
    # lossy, so it carries the digest.
    ('@~repo=84b8d7b2@@_nohost_', [':repo']),
    ('@a~=bfc622d4@@_nohost_', ['a:']),
]


# Locators that name no repository at all. `https://host.xz` used to read the
# TLD as the host and the domain as the repository name, answering with
# something nobody asked for.
LOCATORS_NAMING_NO_REPOSITORY = ['https://host.xz', 'git://host.xz/', 'ssh://']


@pytest.mark.parametrize('locator, identity', composes(LOCATOR_IDENTITIES))
def test_a_locator_composes_its_identity(locator, identity):
    assert generate_id(locator) == identity


def test_no_two_locators_share_an_identity():
    assert_no_two_groups_share_an_identity(LOCATOR_IDENTITIES)


@pytest.mark.parametrize('identity', [i for i, _ in LOCATOR_IDENTITIES])
def test_a_locator_identity_is_a_usable_name(identity):
    assert_is_a_usable_name(identity)


def test_a_bare_path_composes_the_identity_of_the_file_url_it_becomes():
    # A path is made absolute and spelled as a `file://` URL, so the two reach
    # one identity. Asserted against what `os` makes of the path rather than
    # against a golden: an absolute POSIX path picks up the current drive on
    # Windows, so it is not the same locator there.
    bare = os.path.join(os.sep, 'srv', 'git', 'mylib.git')

    assert generate_id(bare) == generate_id(Path(os.path.abspath(bare)).as_uri())


@pytest.mark.parametrize('locator', LOCATORS_NAMING_NO_REPOSITORY)
def test_a_locator_naming_no_repository_is_refused(locator):
    with pytest.raises(ValueError) as error:
        generate_id(locator)

    assert 'names no repository' in str(error.value)


@pytest.mark.parametrize('identity', [i for i, _ in LOCATOR_IDENTITIES])
def test_a_locator_identity_reads_back_as_it_was_spelled(identity):
    # What turns the corpus from a list of spellings into a check that the
    # grammar round-trips, and what gives `parse` a caller of its own.
    assert str(SourceId.parse(identity)) == identity


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


# An identity long enough to be cut, and the longest one that is not. A local
# locator spells a whole path, which has no bound where a file name does.
AT_THE_LIMIT = 'https://a.io/o/' + 'x' * (
    safe_part.READABLE_LENGTH - len('@') - len('@o@a.io'))
PAST_THE_LIMIT = AT_THE_LIMIT + 'x'


ADVERTISEMENT_IDENTITIES = [
    # One file for both, since a `.git` suffix on a remote is a server
    # convention and generate_id composes one identity from them.
    ('@json@nlohmann@github.com', ['https://github.com/nlohmann/json.git',
                                   'https://github.com/nlohmann/json']),
    # The scp spelling is its own file. It costs a second `ls-remote`, which is
    # the right price: golem cannot prove the two transports serve one store.
    ('@json@nlohmann@github.com@scp.git', ['git@github.com:nlohmann/json.git']),
    ('@ext@@_nohost_@=3c7d39aa', ['ext::sh -c foo']),
    ('@mylib.git@very-long-directory-name.very=b75b73c2',
     ['file:///' + 'very-long-directory-name/' * 4 + 'mylib.git']),
    # Exactly at the limit passes through; one character past it is cut, and the
    # digest of the whole identity takes over from there. What is left is no
    # longer a well-formed identity, and needs not be: a file name is all it is.
    ('@' + 'x' * 32 + '@o@a.io', [AT_THE_LIMIT]),
    ('@' + 'x' * 33 + '@o@a.i=b9462845', [PAST_THE_LIMIT]),
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
    (ResourceKind.DEPENDENCY, '@json@nlohmann@github.com#65ee684',
     'a1427f16', 'a1427f162264de1a'),
    (ResourceKind.COOKBOOK, '@recipes@golemcpp@github.com#main=0d6e4079',
     '21ddbafa', '21ddbafa6fd3a184'),
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
    key = '@same@org@github.com'

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
