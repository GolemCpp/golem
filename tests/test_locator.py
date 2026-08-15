import os

import pytest

from golemcpp.golem.locator import (DIGEST_SEPARATOR, NO_HOST, Locator,
                                    generate_id, is_bare_path)


# -- what counts as a path, which is git's question to answer ---------------


@pytest.mark.parametrize('value', [
    'mylib',
    './mylib',
    '../mylib',
    '/srv/git/mylib.git',
    './weird:name',
    r'\\server\share\mylib.git',
])
def test_a_path_written_as_one_is_a_path(value):
    assert is_bare_path(value) is True


@pytest.mark.parametrize('value', [
    'https://github.com/org/repo.git',
    'ssh://git@github.com/org/repo.git',
    'git://host/repo.git',
    'file:///srv/git/mylib.git',
    # scp-style, the form a host hands you by default.
    'git@github.com:org/repo.git',
    # A transport helper, dispatched to `git-remote-hg`.
    'hg::https://host/repo',
    # An alias only the user's git config knows how to rewrite.
    'gh:org/repo',
])
def test_everything_git_takes_as_it_stands_is_not_a_path(value):
    assert is_bare_path(value) is False


@pytest.mark.parametrize('value', ['C:/proj/mylib', r'C:\proj\mylib'])
def test_a_windows_drive_is_a_path_not_a_host(value):
    # `C:` reads as an scp-style host by the colon rule, and as a URL scheme to
    # urlparse. Git makes the same exception, and golem has to make it wherever
    # it runs, since a cache is shared between platforms.
    assert is_bare_path(value) is True


# -- the type itself --------------------------------------------------------


def test_a_path_is_refused_as_a_settled_locator():
    # `./mylib` means nothing without the project it was written in.
    with pytest.raises(ValueError) as error:
        Locator('./mylib')

    assert 'resolved against a project first' in str(error.value)


def test_an_empty_locator_names_nothing():
    assert not Locator()
    assert Locator() == Locator('')
    assert str(Locator()) == ''


def test_a_remote_locator_keeps_its_exact_spelling():
    # Rewriting scp-style to ssh:// would not be lossless -- `host:foo.git` is
    # relative to the login user's home where `ssh://host/foo.git` is absolute --
    # so what git was handed is what the user wrote.
    scp = 'git@github.com:org/repo.git'

    assert str(Locator(scp)) == scp
    assert Locator(scp).get_local_path() is None
    assert Locator(scp).is_local() is False


def test_equality_is_between_locators_only():
    # Deliberately not comparing equal to the string spelling it: the boundaries
    # where a locator becomes text are the ones this type exists to make visible.
    assert Locator('https://host/r.git') == Locator('https://host/r.git')
    assert Locator('https://host/r.git') != 'https://host/r.git'


def test_a_file_url_names_a_local_path(tmp_path):
    locator = Locator(tmp_path.resolve().as_uri())

    assert locator.is_local() is True
    assert locator.get_local_path() == str(tmp_path.resolve())
    assert locator.is_existing_directory() is True


def test_a_local_path_that_is_not_there_names_no_directory(tmp_path):
    locator = Locator((tmp_path / 'absent').resolve().as_uri())

    assert locator.get_local_path() == str(tmp_path / 'absent')
    assert locator.is_existing_directory() is False


def test_a_percent_encoded_path_reads_back_as_it_was_written(tmp_path):
    directory = tmp_path / 'weird#name'
    directory.mkdir()
    locator = Locator(directory.resolve().as_uri())

    # as_uri percent-encodes the separator, which is what keeps a `#` in a name
    # from reading as a version.
    assert '%23' in str(locator)
    assert locator.get_local_path() == str(directory)


def test_a_repository_is_recognised_through_the_locator(tmp_path):
    checkout = tmp_path / 'mylib'
    (checkout / '.git').mkdir(parents=True)
    (checkout / '.git' / 'HEAD').write_text('ref: refs/heads/main\n', encoding='utf-8')

    assert Locator(checkout.resolve().as_uri()).is_git_repository() is True
    assert Locator(tmp_path.resolve().as_uri()).is_git_repository() is False
    assert Locator('https://host/r.git').is_git_repository() is False


def test_get_id_is_the_recipe_directory_name():
    # A published contract: this is the directory a cookbook holds the recipe in.
    assert Locator('https://github.com/nlohmann/json.git').get_id() == \
        'json@com.github.nlohmann'


def test_one_repository_has_one_id_however_it_is_spelled():
    # A recipe is looked up by this id, so a project cloned over ssh has to find
    # the same recipe as one cloned over https.
    assert generate_id('git@github.com:nlohmann/json.git') == 'json@com.github.nlohmann'
    assert generate_id('ssh://git@github.com/nlohmann/json.git') == 'json@com.github.nlohmann'
    assert generate_id('git://github.com/nlohmann/json.git') == 'json@com.github.nlohmann'
    assert generate_id('https://github.com/nlohmann/json.git') == 'json@com.github.nlohmann'


def test_an_id_is_asked_of_shapes_golem_cannot_enumerate():
    # A transport helper with a URL address is named by that address; anything
    # else golem has never heard of gets an id from what it holds rather than
    # raising. None of them is the forge shape, so all of them carry a digest.
    assert generate_id('hg::https://host/repo').startswith('repo@host=')
    assert '@_no_host_=' in generate_id('ext::sh -c foo')
    assert generate_id('') == ''


def test_a_helper_address_golem_cannot_read_is_not_read_as_a_url():
    # `sh -c foo` is a command and `lp:project` is a bzr alias. Read as locations
    # they became a path under the current directory and a host named `lp` --
    # a hierarchy invented out of a string that has none.
    assert generate_id('ext::sh -c foo').startswith('ext@_no_host_=')
    assert generate_id('bzr::lp:project').startswith('bzr@_no_host_=')

    # Named by the transport, told apart by the digest, since nothing else in
    # them is golem's to read.
    assert generate_id('ext::sh -c foo') != generate_id('ext::sh -c bar')

    # The exception, and the documented common case.
    assert generate_id('hg::https://hg.example.com/repo').startswith(
        'repo@com.example.hg=')


def test_a_relative_path_is_absolute_by_the_time_it_is_an_id(tmp_path, monkeypatch):
    # A relative path means relative to the current directory -- that is what it
    # says -- so following it there is right. It names a local directory, and an
    # id claiming it names no host at all would be the wrong answer.
    monkeypatch.chdir(tmp_path)

    assert generate_id('mylib') == generate_id(str(tmp_path / 'mylib'))
    assert generate_id('mylib') == generate_id('./mylib')
    assert generate_id('mylib').startswith('mylib@fsys.')


def test_a_settled_locator_carries_no_fragment(tmp_path):
    # What a `#` in a local path becomes, so nothing downstream has to know the
    # version separator exists.
    directory = tmp_path / 'weird#name'
    directory.mkdir()

    assert Locator(directory.resolve().as_uri()).get_local_path() == str(directory)


# -- shapes that used to crash rather than be reported ----------------------


@pytest.mark.parametrize('value', ['ssh://', 'http://', 'file://'])
def test_a_scheme_on_its_own_is_refused_where_it_is_written(value):
    # It used to reach generate_id and index an empty list, so what a typo in a
    # location produced was an IndexError traceback out of cache-key building.
    with pytest.raises(ValueError) as error:
        Locator(value)

    assert 'names nothing' in str(error.value)


def test_a_locator_no_url_parser_can_read_is_named_by_the_error():
    # A bad setting is reported as `ERROR: <message>` and nothing else, so
    # urlparse's own `Invalid IPv6 URL` would name neither the locator nor the
    # setting it was written in.
    with pytest.raises(ValueError) as error:
        Locator('http://[')

    assert "'http://['" in str(error.value)
    assert 'cannot be read as a URL' in str(error.value)


def test_a_port_golem_cannot_read_is_gits_to_refuse_not_golems():
    # Whether a locator is well formed is settled against the server. Golem only
    # has to get an id out of it, and an unconfirmable shape is what the digest
    # is for.
    malformed = 'ssh://host.example.com:notaport/org/repo.git'

    assert generate_id(malformed).startswith('repo@com.example.host.org')
    assert DIGEST_SEPARATOR in generate_id(malformed)
    assert Locator(malformed).get_id() == generate_id(malformed)


def test_generate_id_reports_a_locator_naming_no_repository():
    # Reached with a raw remote.origin.url, so it answers for itself too.
    with pytest.raises(ValueError) as error:
        generate_id('ssh://')

    assert 'names no repository' in str(error.value)


def test_a_windows_drive_identifies_as_the_path_it_is():
    # is_bare_path makes this exception, so as_url has to make it too: read as
    # an scp host, `C:` gave two different ids for one directory.
    assert generate_id('C:/proj/mylib') == generate_id(r'C:\proj\mylib')
    # The drive's colon is punctuation, not content, so it comes off rather than
    # reading as a substitution -- and all three spellings converge here, since a
    # path normalized on Windows arrives as a plain `file://` URL.
    assert generate_id('C:/proj/mylib').startswith('mylib@fsys.c.proj=')
    assert generate_id('file:///C:/proj/mylib') == generate_id('C:/proj/mylib')


def test_a_trimmed_drive_is_not_the_directory_spelled_without_it():
    # Trimming is lossy, and a cache is shared between platforms, so the digest is
    # what keeps a Windows drive apart from an ordinary POSIX path of that name.
    #
    # The POSIX path is spelled as the URL it normalizes to: a bare `/c/proj` is
    # not absolute on Windows, where it would pick up the current drive and name
    # a third thing again.
    assert generate_id('C:/proj/mylib') != generate_id('file:///c/proj/mylib')
    assert generate_id('file:///c/proj/mylib') == 'mylib@fsys.c.proj'


# -- the forge shape, and a digest for everything else ----------------------


def test_case_is_the_one_difference_an_id_cannot_keep():
    # Accepted, not covered. An id is a directory name, and NTFS and APFS are
    # case-insensitive, so folding is forced whatever this function does -- while
    # a host reached over ssh at a filesystem path is case-sensitive, and nothing
    # here detects one. The digest rescues every other difference; not this.
    #
    # Pinned so it stays a decision: several recipes (`microsoft/GSL`,
    # `SDL-mirror/SDL`) depend on the fold, so it cannot be lifted without
    # renaming them.
    assert (generate_id('ssh://git.company.com/org/Repo.git')
            == generate_id('ssh://git.company.com/org/repo.git'))


@pytest.mark.parametrize('url,expected', [
    ('https://github.com/nlohmann/json.git', 'json@com.github.nlohmann'),
    ('https://github.com/boostorg/boost.git', 'boost@com.github.boostorg'),
    # Capitals: a forge treats them as one owner, and several recipes rely on it.
    ('https://github.com/microsoft/GSL.git', 'gsl@com.github.microsoft'),
    ('https://github.com/SDL-mirror/SDL.git', 'sdl@com.github.sdl-mirror'),
    ('https://github.com/GolemCpp/recipes.git', 'recipes@com.github.golemcpp'),
    # Self-hosted on a three-label host is still the forge shape.
    ('https://git.company.com/org/repo.git', 'repo@com.company.git.org'),
])
def test_the_forge_shape_keeps_the_id_it_has_always_had(url, expected):
    # These are recipe directory names in the cookbook. They are a published
    # contract, so a digest must never appear on one.
    assert generate_id(url) == expected


def test_scp_style_is_not_a_spelling_of_an_ssh_url():
    # An scp path is relative to the login user's home where an `ssh://` path is
    # absolute, so these name three different repositories on one host. All three
    # used to be one id, and therefore one cache root holding one clone.
    ids = {generate_id(value) for value in (
        'git@host.xz:repo.git',
        'host.xz:repo.git',
        'ssh://host.xz/repo.git',
    )}

    assert len(ids) == 3


def test_writing_out_the_default_port_keeps_the_id():
    # The bare form already means this port, so spelling it must not cost the
    # readable id -- which is the recipe directory name, so losing it is a lookup
    # that misses rather than a cache root that duplicates.
    assert generate_id('https://github.com:443/nlohmann/json.git') == \
        'json@com.github.nlohmann'
    assert generate_id('ssh://git@github.com:22/nlohmann/json.git') == \
        'json@com.github.nlohmann'


def test_an_escape_is_decoded_before_it_is_read_as_a_name():
    # `as_uri` is what spells the `#` as `%23`, so leaving it encoded meant golem
    # read the digits of its own escape as part of the directory name.
    assert generate_id('file:///home/me/proj%23/weird%23name').startswith(
        'weird~name@fsys.home.me.proj~=')


def test_a_repository_name_may_hold_a_dot():
    # The name is the half before the `@`, which is in no safe set, so a dot in it
    # cannot blur any boundary. This retires the case the digest was added for.
    assert generate_id('file:///home/me/repo.bundle') == 'repo.bundle@fsys.home.me'
    assert generate_id('https://github.com/socketio/socket.io.git') == \
        'socket.io@com.github.socketio'
    assert generate_id('https://github.com/socketio/socketio.git') == \
        'socketio@com.github.socketio'


def test_only_the_repository_name_may_hold_a_dot():
    # The host half is dot-joined, so a dot inside one of its components makes the
    # boundary unrecoverable: both of these would otherwise be `repo@y.x.a.b`.
    assert generate_id('https://x.y/a.b/repo.git') != \
        generate_id('https://a.x.y/b/repo.git')
    assert generate_id('https://a.x.y/b/repo.git') == 'repo@y.x.a.b'


def test_an_id_does_not_depend_on_what_is_on_the_disk(monkeypatch):
    # `weird:name` is a directory here and git still reads it as ssh to host
    # `weird`. Answering from the disk contradicted git, and gave one string two
    # different identities depending on whether the directory happened to exist.
    #
    # The disk is made to claim the name rather than hold it: a colon cannot be in
    # a Windows filename, and what is under test is that nobody asks.
    absent = generate_id('weird:name')
    monkeypatch.setattr(os.path, 'isdir', lambda path: True)

    assert generate_id('weird:name') == absent
    assert absent.startswith('name@weird')


def test_a_host_reads_the_same_however_the_locator_spells_it():
    # An authority goes into the built URL unencoded, because a host is IDNA and
    # not percent-encoded. Encoded, it read back as its own escape: one host came
    # out `w~c3~a9ird` from the scp form and `w~ird` from the URL form.
    scp = generate_id('git@wéird:repo.git')
    url = generate_id('ssh://git@wéird/repo.git')

    assert scp.startswith('repo@w~ird')
    assert url.startswith('repo@w~ird')
    # Still two locators: an scp path is home-relative where an ssh:// one is not.
    assert scp != url


def test_a_bracket_cannot_break_the_locator_it_is_written_in():
    # The two characters that would make urlparse refuse the whole thing. Neither
    # can occur in a real hostname, so what they read as does not matter -- that
    # golem answers at all does.
    assert generate_id('git@a[b:repo.git').startswith('repo@')
    assert generate_id('git@a]b:repo.git').startswith('repo@')
    assert generate_id('git@a[b:repo.git') != generate_id('git@a]b:repo.git')


def test_a_path_separator_is_not_read_as_a_url_delimiter():
    # These build a URL out of a filesystem path, so what they insert has to be
    # encoded: unencoded, everything after the `#` fell off as a fragment.
    assert generate_id('git@host.xz:weird#name').startswith('weird~name@xz.host=')
    assert generate_id('C:/proj/weird#name').startswith('weird~name@fsys.c.proj=')


@pytest.mark.parametrize('value,expected', [
    # `_` and `-` are in the safe set, so a component leading with one is
    # untouched by the filter and has no lossiness for a digest to answer for.
    ('https://github.com/_owner/repo.git', 'repo@com.github._owner'),
    ('https://github.com/owner/-repo.git', '-repo@com.github.owner'),
    ('https://github.com/_o/-r.git', '-r@com.github._o'),
])
def test_a_component_may_lead_with_a_character_the_filter_keeps(value, expected):
    # The predicate used to require a leading alphanumeric -- RFC 1123's rule for
    # a hostname label, which a path segment has no reason to obey. It cost a
    # digest and prevented nothing: one is a suffix, so it cannot reach the first
    # character it was seemingly there to guard.
    assert generate_id(value) == expected


def test_a_dot_still_costs_a_digest_outside_the_repository_name():
    # The true negative the rule above must keep: the host half is dot-joined, so
    # a dot inside one of its components would blur the boundary.
    assert generate_id('file:///home/me/.config/repo').startswith(
        'repo@fsys.home.me.~config=')


@pytest.mark.parametrize('value', [
    # A single-label host spelled like the marker.
    'https://_no_host_/repo.git',
    # A locator naming no host at all.
    ':repo',
    # A helper address nothing can read a hierarchy out of.
    'ext::sh -c foo',
])
def test_the_no_host_marker_never_stands_without_a_digest(value):
    # Unlike `fsys`, the marker needs no reservation, because the forge shape
    # cannot reach it: a remote one needs two host labels or more, so its host
    # half is always dot-joined, and a `file://` one always heads with `fsys`.
    # Pinned as an invariant rather than left to that argument -- without a
    # digest, a host genuinely named `_no_host_` and a locator naming no host
    # would be one cache root.
    generated = generate_id(value)
    host_half = generated.partition('@')[2]

    assert host_half.split(DIGEST_SEPARATOR)[0] == NO_HOST
    assert DIGEST_SEPARATOR in generated


@pytest.mark.parametrize('one,other', [
    # The host/path boundary is not encoded, so a fixed segment count fixes it.
    ('https://a.b/c/repo.git', 'https://b/a/c/repo.git'),
    # A dot in a repository name is ordinary, and it used to be dropped.
    ('https://github.com/socketio/socket.io.git', 'https://github.com/socketio/socketio.git'),
    # The `fsys` marker is not reserved on a remote host.
    ('file:///tmp/mylib', 'https://fsys/tmp/mylib'),
    # Two ports on one host are two servers.
    ('ssh://host:2222/org/x.git', 'ssh://host:22/org/x.git'),
    # Non-ASCII is dropped, not substituted.
    ('https://héllo/x.git', 'https://hllo/x.git'),
])
def test_two_repositories_never_share_an_id(one, other):
    # Sharing one meant sharing a cache root: the second resolved onto the first
    # one's clone, and record_manifest relabelled the root rather than noticing.
    assert generate_id(one) != generate_id(other)


def test_every_spelling_of_one_repository_still_shares_its_id():
    ids = {generate_id(url) for url in (
        'https://github.com/nlohmann/json.git',
        'https://github.com/nlohmann/json',
        'git@github.com:nlohmann/json.git',
        'ssh://git@github.com/nlohmann/json.git',
        'https://github.com/NLohmann/JSON.git',
    )}

    assert ids == {'json@com.github.nlohmann'}


def test_a_local_directory_keeps_a_readable_id(tmp_path):
    # The common shape while developing against a checkout next door, so it is
    # worth its own clause rather than being digested with everything else.
    assert generate_id('file:///tmp/mylib') == 'mylib@fsys.tmp'
    assert generate_id('file:///tmp/my lib').startswith('my~lib@fsys.tmp=')
