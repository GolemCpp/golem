'''
Why an identity comes out the way it does.

`no_module/test_composed_identities.py` is the index of cases, one corpus per
kind of identity. This keeps the arguments: which recipes depend on case
folding, why only the name may hold a dot, why an scp path is not an `ssh://`
one, and what each digest is taken over.
'''

import os

import pytest

from golemcpp.golem import safe_part
from golemcpp.golem.locator import generate_id
from golemcpp.golem.source_id import LOCAL_HOST, NO_HOST, SourceId


# -- the grammar ------------------------------------------------------------


def test_an_identity_leads_with_the_separator():
    # Load-bearing rather than decoration: a cookbook is a repository, so it
    # holds an AGENTS.md, a README and a .github/ beside its recipes. The `@` is
    # what a listing selects on to tell a recipe from the furniture.
    assert generate_id('https://github.com/nlohmann/json.git').startswith('@')


def test_the_fields_are_named_in_order_of_what_they_answer():
    identity = SourceId.from_locator('https://github.com/nlohmann/json.git')

    assert (identity.name, identity.owner, identity.host, identity.rooting) == (
        'json', 'nlohmann', 'github.com', '')
    assert str(identity) == '@json@nlohmann@github.com'


def test_the_host_is_read_in_natural_order():
    # Reversing existed to group a flat listing by host. With the name first
    # that is gone, and a reversed host reads as nothing anyone typed.
    assert SourceId.from_locator('https://github.com/o/r.git').host == 'github.com'


def test_an_empty_owner_is_spelled_rather_than_left_out():
    # The host has to stay in the field that answers "which host", so an owner
    # nobody named is written as the gap it is.
    assert generate_id('ftps://host.xz/repo.git') == '@repo@@host.xz'


def test_a_trailing_empty_field_is_not_spelled():
    # `@repo@@` and `@repo` would otherwise be two names for one identity, and
    # both would be directories a cookbook could hold.
    assert str(SourceId(name='repo')) == '@repo'
    assert str(SourceId.parse('@repo@@')) == '@repo'


@pytest.mark.parametrize('text', [
    '@json@nlohmann@github.com',
    '@repo@@host.xz@scp.alice',
    '@proj@group~subgroup=75085152@gitlab.com',
    '@ext@@_nohost_@=3c7d39aa',
])
def test_an_identity_reads_back_as_it_was_spelled(text):
    # A field can never hold a `@`, since it is outside every safe set, so
    # reading one back is a split rather than a parse.
    assert str(SourceId.parse(text)) == text


def test_an_identity_is_folded_on_the_way_in_as_well_as_on_the_way_out():
    # Composing one folds, so reading one has to: an identity is a directory
    # name, and `--recipe @JSON@Nlohmann@GitHub.com` has to find the recipe a
    # case-sensitive filesystem holds under the folded spelling.
    assert str(SourceId.parse('@JSON@Nlohmann@GitHub.com')) == \
        generate_id('https://github.com/nlohmann/json.git')


def test_something_that_is_not_an_identity_is_refused_by_name():
    with pytest.raises(ValueError) as error:
        SourceId.parse('json@com.github.nlohmann')

    assert "does not start with '@'" in str(error.value)


# -- the boundary the count used to buy ------------------------------------


def test_the_host_and_the_path_are_told_apart_by_the_separator():
    # These used to be one readable id, told apart only by a digest, because a
    # dot-joined head cannot say where the host ended. A fixed count of two path
    # segments bought the boundary back, and sent everything else into a digest.
    assert generate_id('https://a.b/c/repo.git') == '@repo@c@a.b'
    assert generate_id('https://b/a/c/repo.git') == '@repo@a.c@b'


@pytest.mark.parametrize('url,expected', [
    ('git://git.kernel.org/pub/scm/git/git.git', '@git@pub.scm.git@git.kernel.org'),
    ('https://gitlab.com/group/subgroup/proj.git', '@proj@group.subgroup@gitlab.com'),
    ('ftps://host.xz/repo.git', '@repo@@host.xz'),
])
def test_a_path_of_any_depth_stays_readable(url, expected):
    # The three shapes the reshape was for. Each cost a digest of the whole URL
    # under the count, which made a recipe unnameable for anything but a forge.
    assert generate_id(url) == expected
    assert safe_part.DIGEST_SEPARATOR not in expected


# -- what a digest is taken over -------------------------------------------


def test_only_the_field_that_lost_something_carries_a_digest():
    # The whole-URL digest is gone: it made every field unreadable to answer for
    # one of them.
    identity = SourceId.from_locator('https://gitlab.com/group.subgroup/proj.git')

    assert identity.name == 'proj'
    assert identity.host == 'gitlab.com'
    assert identity.owner.startswith('group~subgroup' + safe_part.DIGEST_SEPARATOR)


def test_a_repository_name_may_hold_a_dot():
    # Nothing is joined onto the name, so a dot in it cannot blur a boundary.
    assert generate_id('https://github.com/socketio/socket.io.git') == \
        '@socket.io@socketio@github.com'
    assert generate_id('https://github.com/socketio/socketio.git') == \
        '@socketio@socketio@github.com'


def test_only_the_repository_name_may_hold_a_dot():
    # The owner is dot-joined, so a literal dot there spells what a path
    # separator spells and only the digest keeps the two apart.
    assert generate_id('https://x.y/a.b/repo.git') != generate_id('https://a.x.y/b/repo.git')
    assert generate_id('https://a.x.y/b/repo.git') == '@repo@b@a.x.y'


@pytest.mark.parametrize('value,expected', [
    # `_` and `-` are in the safe set, so a field leading with one is untouched
    # by the filter and has no lossiness for a digest to answer for.
    ('https://github.com/_owner/repo.git', '@repo@_owner@github.com'),
    ('https://github.com/owner/-repo.git', '@-repo@owner@github.com'),
])
def test_a_field_may_lead_with_a_character_the_filter_keeps(value, expected):
    assert generate_id(value) == expected


# -- the port ---------------------------------------------------------------


def test_writing_out_the_default_port_keeps_the_identity():
    # The bare form already means this port, so spelling it must not cost the
    # readable identity, which is the recipe directory name.
    assert generate_id('https://github.com:443/nlohmann/json.git') == \
        '@json@nlohmann@github.com'
    assert generate_id('ssh://git@github.com:22/nlohmann/json.git') == \
        '@json@nlohmann@github.com'


def test_a_port_digest_is_taken_over_the_host_and_the_port_and_nothing_else():
    # Digested over `parsed.netloc`, this swept up the userinfo -- which an
    # absolute URL discards -- and the case, which everything else folds. The
    # merges below then held on a default port and broke on any other.
    ids = {generate_id(url) for url in (
        'https://host.xz:8443/o/repo.git',
        'https://HOST.XZ:8443/o/repo.git',
        'https://host.xz:08443/o/repo.git',
        'https://alice@host.xz:8443/o/repo.git',
        'https://bob@host.xz:8443/o/repo.git',
    )}

    assert len(ids) == 1


def test_two_ports_on_one_host_are_two_servers():
    assert generate_id('ssh://host/o/x.git') != generate_id('ssh://host:2222/o/x.git')


def test_a_port_golem_cannot_read_is_carried_rather_than_dropped():
    # `parsed.port` raises here. Letting the port vanish merged this onto the
    # no-port spelling: two servers golem never looked at, one cache root.
    unreadable = generate_id('ssh://host.example.com:99999/org/repo.git')

    assert unreadable != generate_id('ssh://host.example.com/org/repo.git')
    assert unreadable.startswith('@repo@org@host.example.com=')


# -- where the path hangs from ----------------------------------------------


def test_scp_style_is_not_a_spelling_of_an_ssh_url():
    # An scp path is relative to the login user's home where an `ssh://` path is
    # absolute, so these name three different repositories on one host.
    assert generate_id('ssh://host.xz/repo.git') == '@repo@@host.xz'
    assert generate_id('host.xz:repo.git') == '@repo@@host.xz@scp'
    assert generate_id('git@host.xz:repo.git') == '@repo@@host.xz@scp.git'


def test_an_scp_user_is_part_of_the_root_rather_than_who_authenticates():
    assert generate_id('alice@host.xz:repo.git') != generate_id('bob@host.xz:repo.git')


def test_a_user_on_an_absolute_url_is_not_part_of_the_identity():
    # The path is absolute, so who authenticates does not change which
    # repository it names. They differed before only because the whole-URL
    # digest happened to sweep the userinfo up.
    assert (generate_id('ssh://alice@host.xz/repo.git')
            == generate_id('ssh://bob@host.xz/repo.git'))


def test_a_scheme_is_a_road_to_a_server_rather_than_a_different_one():
    ids = {generate_id(url) for url in (
        'https://github.com/nlohmann/json.git',
        'git://github.com/nlohmann/json.git',
        'https://github.com/nlohmann/json',
    )}

    assert ids == {'@json@nlohmann@github.com'}


def test_a_windows_drive_is_a_root_beside_the_others():
    # `C:/proj/mylib` and `/c/proj/mylib` are two directories on two roots.
    # Normalizing the drive to a bare `c` made them one readable name.
    assert generate_id('C:/proj/mylib') == '@mylib@proj@_local_@drive.c'
    assert generate_id('file:///c/proj/mylib') == '@mylib@c.proj@_local_'
    assert generate_id('C:/proj/mylib') == generate_id(r'C:\proj\mylib')
    assert generate_id('file:///C:/proj/mylib') == generate_id('C:/proj/mylib')


def test_a_helper_address_golem_cannot_read_names_no_hierarchy():
    # `sh -c foo` is a command and `lp:project` is a bzr alias. Read as
    # locations they became a path under the current directory and a host named
    # `lp` -- a hierarchy invented out of a string that has none. The rooting
    # field's bare digest is where that goes.
    assert generate_id('ext::sh -c foo').startswith('@ext@@' + NO_HOST + '@=')
    assert generate_id('bzr::lp:project').startswith('@bzr@@' + NO_HOST + '@=')
    assert generate_id('ext::sh -c foo') != generate_id('ext::sh -c bar')

    # The exception, and the documented common case.
    assert generate_id('hg::https://host.xz/repo') == '@repo@@host.xz'


# -- the `.git` rule --------------------------------------------------------


def test_a_git_suffix_is_a_server_convention_a_filesystem_does_not_share():
    # A server serves `/o/repo` and `/o/repo.git` as one store. A filesystem has
    # two directory entries, and golem may not merge two paths that both exist.
    assert generate_id('https://github.com/o/repo.git') == \
        generate_id('https://github.com/o/repo')
    assert generate_id('file:///a/b/c.git') != generate_id('file:///a/b/c')
    assert generate_id('file:///a/b/c.git') == '@c.git@a.b@_local_'


def test_a_whole_git_segment_is_the_repository_above_it():
    # A fact about git rather than a convention: `git clone <path>/.git` works.
    assert generate_id('file:///a/b/c/.git') == generate_id('file:///a/b/c')
    assert generate_id('https://github.com/org/.git') == \
        generate_id('https://github.com/org')


def test_only_one_suffix_comes_off_and_case_is_no_defence():
    assert generate_id('https://github.com/o/repo.git.git') == '@repo.git@o@github.com'
    assert generate_id('https://github.com/o/x.GIT') == generate_id('https://github.com/o/x.git')


# -- the sentinels ----------------------------------------------------------


def test_a_local_locator_says_so_in_the_host_field():
    # The path used to stand in for a host behind a marker, which put the whole
    # path into the field answering "which host".
    assert SourceId.from_locator('file:///tmp/mylib').host == LOCAL_HOST
    assert generate_id('file:///tmp/mylib') == '@mylib@tmp@_local_'


@pytest.mark.parametrize('sentinel,url', [
    (LOCAL_HOST, 'https://_local_/repo.git'),
    (NO_HOST, 'https://_nohost_/repo.git'),
])
def test_a_host_really_spelled_like_a_sentinel_says_it_is_not_one(sentinel, url):
    # A construction rather than a reserved-name list: the real host always
    # carries a digest and the sentinel never does, so they cannot be equal.
    # Only an exact single-label host can collide, since natural order leaves
    # `_local_.example.com` spelling itself.
    identity = SourceId.from_locator(url)

    assert identity.host.startswith(sentinel + safe_part.DIGEST_SEPARATOR)
    assert identity.host != sentinel


def test_a_sentinel_is_bare_and_a_subdomain_of_one_is_untouched():
    assert SourceId.from_locator('https://_local_.example.com/o/r.git').host == \
        '_local_.example.com'
    assert SourceId.from_locator('ext::sh -c foo').host == NO_HOST


# -- case, which an identity cannot keep ------------------------------------


def test_case_is_the_one_difference_an_identity_cannot_keep():
    # Accepted, not covered. An identity is a directory name, and NTFS and APFS
    # are case-insensitive, so folding is forced whatever this function does.
    #
    # Pinned so it stays a decision: several recipes depend on the fold, so it
    # cannot be lifted without renaming them.
    assert (generate_id('ssh://git.company.com/org/Repo.git')
            == generate_id('ssh://git.company.com/org/repo.git'))


@pytest.mark.parametrize('url,expected', [
    ('https://github.com/microsoft/GSL.git', '@gsl@microsoft@github.com'),
    ('https://github.com/SDL-mirror/SDL.git', '@sdl@sdl-mirror@github.com'),
    ('https://github.com/nlohmann/json.git', '@json@nlohmann@github.com'),
    ('https://github.com/GolemCpp/recipes.git', '@recipes@golemcpp@github.com'),
])
def test_the_recipes_that_depend_on_the_fold_keep_their_directory_name(url, expected):
    # These are recipe directory names in the cookbook, and a published
    # contract, so a digest must never appear on one.
    assert generate_id(url) == expected
    assert safe_part.DIGEST_SEPARATOR not in expected


# -- reading the locator rather than the disk -------------------------------


def test_an_identity_does_not_depend_on_what_is_on_the_disk(monkeypatch):
    # `weird:name` is a directory here and git still reads it as ssh to host
    # `weird`. Answering from the disk contradicted git, and gave one string two
    # identities depending on whether the directory happened to exist.
    absent = generate_id('weird:name')
    monkeypatch.setattr(os.path, 'isdir', lambda path: True)

    assert generate_id('weird:name') == absent
    assert absent == '@name@@weird@scp'


def test_a_relative_path_is_absolute_by_the_time_it_is_an_identity(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    assert generate_id('mylib') == generate_id(str(tmp_path / 'mylib'))
    assert generate_id('mylib') == generate_id('./mylib')
    assert SourceId.from_locator('mylib').host == LOCAL_HOST


def test_an_escape_is_decoded_before_it_is_read_as_a_name():
    # `as_uri` is what spells the `#` as `%23`, so leaving it encoded meant
    # golem read the digits of its own escape as part of the directory name.
    assert SourceId.from_locator('file:///home/me/weird%23name').name.startswith(
        'weird~name' + safe_part.DIGEST_SEPARATOR)


def test_a_path_separator_is_not_read_as_a_url_delimiter():
    # These build a URL out of a filesystem path, so what they insert has to be
    # encoded: unencoded, everything after the `#` fell off as a fragment.
    assert SourceId.from_locator('git@host.xz:weird#name').name.startswith('weird~name' + safe_part.DIGEST_SEPARATOR)
    assert SourceId.from_locator('C:/proj/weird#name').name.startswith('weird~name' + safe_part.DIGEST_SEPARATOR)


def test_a_host_reads_the_same_however_the_locator_spells_it():
    # An authority goes into the built URL unencoded, because a host is IDNA and
    # not percent-encoded. Encoded, it read back as its own escape: one host came
    # out `w~c3~a9ird` from the scp form and `w~ird` from the URL form.
    scp = SourceId.from_locator('git@wéird:repo.git')
    url = SourceId.from_locator('ssh://git@wéird/repo.git')

    assert scp.host == url.host
    # Still two locators: an scp path is home-relative where an ssh:// one is not.
    assert str(scp) != str(url)


def test_a_bracket_cannot_break_the_locator_it_is_written_in():
    # The two characters that would make urlparse refuse the whole thing.
    assert generate_id('git@a[b:repo.git') != generate_id('git@a]b:repo.git')
    assert generate_id('git@a[b:repo.git').startswith('@repo@@a~')


# -- what is refused --------------------------------------------------------


@pytest.mark.parametrize('value', ['https://host.xz', 'git://host.xz/', 'ssh://'])
def test_a_locator_naming_no_path_is_refused(value):
    # `https://host.xz` used to read the TLD as the host and the domain as the
    # repository, naming something nobody asked for. There is no segment to be
    # a name, so it is refused where it was written.
    with pytest.raises(ValueError) as error:
        generate_id(value)

    assert 'names no repository' in str(error.value)


def test_an_empty_locator_composes_an_empty_identity():
    assert generate_id('') == ''
    assert not SourceId.from_locator('')


# -- the ladder and the merge, which Stage B reads --------------------------


def test_the_rungs_drop_one_field_at_a_time_most_specific_first():
    # An ssh clone composes the scp rung; a recipe named at the plain one has to
    # answer it, which is what probing upward is for.
    identity = SourceId.from_locator('git@github.com:nlohmann/json.git')

    assert [str(rung) for rung in identity.rungs()] == [
        '@json@nlohmann@github.com@scp.git',
        '@json@nlohmann@github.com',
        '@json@nlohmann',
        '@json',
    ]


def test_a_rung_a_trailing_empty_field_would_spell_twice_is_named_once():
    # Dropping the host from `@repo@@host.xz` lands on `@repo`, since an empty
    # owner is not spelled once nothing follows it.
    assert [str(rung) for rung in SourceId.parse('@repo@@host.xz').rungs()] == [
        '@repo@@host.xz', '@repo']


def test_a_merge_fills_what_was_left_out_and_keeps_what_was_stated():
    recipe = SourceId.parse('@boost@boostorg@github.com')

    assert str(SourceId.parse('@boost').filled_from(recipe)) == \
        '@boost@boostorg@github.com'
    assert str(SourceId.parse('@boost@@gitlab.com').filled_from(recipe)) == \
        '@boost@boostorg@gitlab.com'
    assert str(SourceId.parse('@boost@somefork@github.com').filled_from(recipe)) == \
        '@boost@somefork@github.com'
