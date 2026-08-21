'''
How Golem composes every identity today, out of safe parts.

Golem names a directory or a file after the value it holds: the locator a
resource came from, the revision it resolved to, the dependencies a build was
configured with. That name has to identify the value, so two of them never
land on one name. It is composed of parts, and a part is spelled from something
that came from outside, into something safe on every platform.
Spelling is lossy, therefore a digest follows it when two values would otherwise
spell the same.

Several places do that today, each with its own charset, its own truncation and
its own digest policy. They are about to move onto one primitive, so what they
produce now is pinned here.

The assertions run against the functions their callers reach for, never against
the primitive being extracted. A test written against internals has to be
rewritten at each step of the migration, so it cannot say whether behaviour
changed.

The corpus leans on non-ASCII. Every policy here agrees on ASCII, therefore a
difference between them shows only outside it. A character that reads as an ASCII
neighbour is a named constant written as an escape, because pasting one hides
what it is there for.
'''

import os

import pytest

from golemcpp.golem import advertisement_store
from golemcpp.golem import cache_directory
from golemcpp.golem import cache_manager
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


# -- locator.generate_id ----------------------------------------------------


@pytest.mark.parametrize('locator, spelled', [
    # The forge shape, which the id is a published contract for.
    ('https://github.com/nlohmann/json.git', 'json@com.github.nlohmann'),
    # scp-style reaching that shape lands on the id the https spelling does.
    ('git@github.com:nlohmann/json.git', 'json@com.github.nlohmann'),

    # Off the forge shape the readable half is not enough, so the whole
    # normalized URL is digested behind it.
    ('git://git.kernel.org/pub/scm/git/git.git',
     'git@org.kernel.git.pub.scm.git=a88a8ab3'),
    ('https://gitlab.com/group/subgroup/proj.git',
     'proj@com.gitlab.group.subgroup=bafa7263'),
    ('ftps://host.xz/repo.git', 'repo@xz.host=e824d735'),

    # A literal dot in an owner spells what a path separator spells, so only the
    # digest keeps the two apart.
    ('https://gitlab.com/group.subgroup/proj.git',
     'proj@com.gitlab.group~subgroup=43745eb8'),

    # An scp path is relative to the named user's home, so a different user is a
    # different repository, and only the digest says so.
    ('alice@host.xz:repo.git', 'repo@xz.host=5e0e9b06'),
    ('bob@host.xz:repo.git', 'repo@xz.host=e9bc533c'),
    ('ssh://host.xz/repo.git', 'repo@xz.host=a68c1f4a'),

    # A port off the default is a second server on one host.
    ('https://host.xz:8443/org/repo.git', 'repo@xz.host.org=ec38cc3a'),

    # A name may hold a dot, so these two stay legible and stay apart.
    ('https://github.com/org/socket.io.git', 'socket.io@com.github.org'),
    ('https://github.com/org/socketio.git', 'socketio@com.github.org'),

    # `.git` is stripped, so a repository reads one way however it was cloned.
    # A trailing slash is not a segment.
    ('https://github.com/org/repo.git', 'repo@com.github.org'),
    ('https://github.com/org/repo', 'repo@com.github.org'),
    ('https://github.com/org/repo.git/', 'repo@com.github.org'),
    # Only one suffix is stripped, so a repository really called `repo.git`
    # keeps its name.
    ('https://github.com/org/repo.git.git', 'repo.git@com.github.org'),
    # The suffix is the one comparison that does not fold case, so these two
    # spellings of one repository do not meet.
    ('https://github.com/org/x.git', 'x@com.github.org'),
    ('https://github.com/org/x.GIT', 'x.git@com.github.org'),
    # A segment that is only the suffix strips to nothing and the level drops to
    # the owner, which names the repository `<path>/.git` belongs to. In such a
    # case, the owner is the repository.
    ('https://github.com/org/.git', 'org@com.github'),

    # Substituted before the case is folded: the Kelvin sign becomes the marker
    # rather than the 'k' it lowercases to.
    ('https://github.com/org/' + KELVIN + 'elvin.git',
     '~elvin@com.github.org=b62edad8'),
    ('https://github.com/org/kelvin.git', 'kelvin@com.github.org'),
    ('https://github.com/' + DOTTED_I + 'stanbul/repo.git',
     'repo@com.github.~stanbul=03e8e4d7'),
    ('https://github.com/org/Straße.git', 'stra~e@com.github.org=33ec1575'),

    # A local locator has no host to reverse, so its path stands in for one.
    ('file:///srv/git/mylib.git', 'mylib@fsys.srv.git'),
    ('/srv/git/mylib.git', 'mylib@fsys.srv.git'),

    # A transport helper whose address is a URL names what the URL names.
    ('hg::https://host.xz/repo', 'repo@xz.host=db8fcede'),
    # An address that is not a URL is opaque, so only the digest identifies it.
    ('ext::sh -c foo', 'ext@_no_host_=3c7d39aa'),
])
def test_generate_id_spells(locator, spelled):
    assert generate_id(locator) == spelled


@pytest.mark.parametrize('one, other', [
    # The pairs the readable half alone would merge.
    ('alice@host.xz:repo.git', 'bob@host.xz:repo.git'),
    ('git@host.xz:repo.git', 'ssh://host.xz/repo.git'),
    ('https://github.com/org/' + KELVIN + 'elvin.git',
     'https://github.com/org/kelvin.git'),
    ('https://github.com/' + DOTTED_I + 'stanbul/repo.git',
     'https://github.com/istanbul/repo.git'),
    ('https://gitlab.com/group.subgroup/proj.git',
     'https://gitlab.com/group/subgroup/proj.git'),
    ('https://host.xz:8443/org/repo.git', 'https://host.xz/org/repo.git'),
    ('https://github.com/org/socket.io.git',
     'https://github.com/org/socketio.git'),
    ('https://github.com/org/repo.git.git', 'https://github.com/org/repo.git'),
    ('https://github.com/org/.git', 'https://github.com/org'),
])
def test_generate_id_keeps_two_repositories_apart(one, other):
    assert generate_id(one) != generate_id(other)


def test_generate_id_strips_git_without_asking_who_reads_the_path():
    # As a suffix, `.git` names a bare repository by convention. On a filesystem
    # `/a/b/c.git` and `/a/b/c` are two directory entries, so meeting is wrong
    # and this assertion is meant to flip.
    assert generate_id('/a/b/c.git') == generate_id('/a/b/c')

    # As a whole segment it is the git directory of the worktree above it, so
    # these two name one repository and meeting is right.
    assert generate_id('/a/b/c/.git') == generate_id('/a/b/c')


def test_generate_id_folds_case_everywhere_except_the_git_suffix():
    # Every field folds case, but `without_git_suffix` compares the suffix as it
    # stands, so `x.GIT` keeps what `x.git` loses and one repository gets two
    # ids. That is a split rather than a collision. The second assertion is meant
    # to flip.
    assert (generate_id('https://GitHub.com/NLohmann/JSON.git')
            == generate_id('https://github.com/nlohmann/json.git'))
    assert (generate_id('https://github.com/org/x.GIT')
            != generate_id('https://github.com/org/x.git'))


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


# -- resource_manager.make_revision_part -------------------------------


@pytest.mark.parametrize('revision, spelled', [
    # An object name is abbreviated and nothing else: it identifies itself.
    ('a' * 40, 'aaaaaaa'),
    ('b' * 64, 'bbbbbbb'),

    # Everything else is a reference, always digested, because the spelling is
    # lossy and the slug is cut at 40.
    ('main', 'main=0d6e4079'),
    ('v1.0.0', 'v1.0.0=2485f4d5'),
    ('release/1.2.3', 'release~1.2.3=88ded651'),
    # Spelled like a short object name, but a reference, so it is digested.
    ('deadbeef', 'deadbeef=2baf1f40'),
    ('café', 'caf~=850f7dc4'),
    ('Straße', 'stra~e=58a3778c'),
    ('x' * 200, 'x' * 40 + '=aa20c23e'),

    # Substituted before the case is folded, as generate_id does: the Kelvin sign
    # and the dotted I become the marker rather than the ASCII letters they
    # lowercase to, so the readable halves already differ.
    (KELVIN + 'elvin', '~elvin=4a274a98'),
    ('kelvin', 'kelvin=03105d50'),
    (DOTTED_I + 'stanbul', '~stanbul=24ec8f72'),
])
def test_make_revision_part_spells(revision, spelled):
    assert make_revision_part(revision) == spelled


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


@pytest.mark.parametrize('url, named', [
    ('https://github.com/nlohmann/json.git', 'json@com.github.nlohmann'),
    # One file for both spellings, since generate_id collapses them.
    ('git@github.com:nlohmann/json.git', 'json@com.github.nlohmann'),
    ('ext::sh -c foo', 'ext@_no_host_=3c7d39aa'),
    # A local locator spells a whole path, which has no bound where a file name
    # does, so past 40 characters the rest is a digest.
    ('file:///' + 'very-long-directory-name/' * 4 + 'mylib.git',
     'mylib@fsys.very-long-directory-name.very=dda64374'),
])
def test_path_for_names(tmp_path, url, named):
    with advertisement_store.shared(str(tmp_path / 'resolve')):
        assert os.path.basename(advertisement_store.path_for(url)) == named


# -- cache_manager.make_minimized_resource_name -----------------------------


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


def make_dependency(name, repository, version):
    return Dependency(name=name, repository=repository, version=version)


JSON = ('json', 'https://github.com/nlohmann/json.git', '^3.0.0')
SPDLOG = ('spdlog', 'https://github.com/gabime/spdlog.git', '1.12.0')


@pytest.mark.parametrize('dependencies, slug', [
    ([], 'da39a3ee'),
    ([JSON], '5214c986'),
    ([JSON, SPDLOG], 'f4d5f384'),
    # Order is part of the slug: the strings are concatenated, not sorted.
    ([SPDLOG, JSON], '1710cca8'),
])
def test_make_dependencies_slug_names(dependencies, slug):
    context = Context.__new__(Context)

    assert context.make_dependencies_slug(
        [make_dependency(*each) for each in dependencies]) == slug
