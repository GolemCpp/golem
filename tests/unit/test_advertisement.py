from golemcpp.golem import advertisement
from golemcpp.golem.advertisement import Advertisement

MAIN = 'ref: refs/heads/main\tHEAD\nabc123\tHEAD\nabc123\trefs/heads/main\n'

ANNOTATED = MAIN + '0bjec7ff\trefs/tags/v2.0.0\n' + 'c0mm17ff\trefs/tags/v2.0.0^{}\n'


def test_the_default_branch_is_read_off_the_symref_line():
    assert Advertisement.parse(MAIN).head_reference == 'main'


def test_a_remote_advertising_nothing_reads_empty():
    # What an empty repository answers.
    assert Advertisement.parse('') == Advertisement()


def test_a_line_naming_no_ref_is_left_out():
    assert Advertisement.parse(MAIN + 'warning: something\n').refs == {
        'HEAD': 'abc123',
        'refs/heads/main': 'abc123',
    }


# -- looking a version up ---------------------------------------------------


def test_each_step_of_the_lookup_order_answers():
    # The order `gitrevisions` gives, minus the remote-tracking steps a remote
    # advertises nothing for.
    parsed = Advertisement.parse(MAIN + 'cafebabe\trefs/tags/v1.2.0\n')

    assert parsed.revision_of('HEAD') == 'abc123'
    assert parsed.revision_of('refs/tags/v1.2.0') == 'cafebabe'
    assert parsed.revision_of('tags/v1.2.0') == 'cafebabe'
    assert parsed.revision_of('heads/main') == 'abc123'
    assert parsed.revision_of('v1.2.0') == 'cafebabe'
    assert parsed.revision_of('main') == 'abc123'


def test_an_ambiguous_name_answers_the_tag_the_way_git_does():
    # `git rev-parse v1.2.0` answers the tag, warning that the name is ambiguous:
    # `gitrevisions` looks in refs/tags/ before refs/heads/.
    parsed = Advertisement.parse(
        MAIN + 'b2a4c400\trefs/heads/v1.2.0\n' + 'ta61e5000\trefs/tags/v1.2.0\n'
    )

    assert parsed.revision_of('v1.2.0') == 'ta61e5000'


def test_a_suffix_of_a_ref_name_does_not_match_it():
    # git matches whole path components, so `1.2.0` names nothing when the tag
    # is `v1.2.0`.
    parsed = Advertisement.parse(MAIN + 'cafebabe\trefs/tags/v1.2.0\n')

    assert parsed.revision_of('1.2.0') == ''
    assert parsed.revision_of('v1.2.0') == 'cafebabe'


def test_a_name_nothing_advertises_answers_empty():
    assert Advertisement.parse(MAIN).revision_of('v9.9.9') == ''


# -- annotated tags ---------------------------------------------------------


def test_an_annotated_tag_holds_the_commit_a_checkout_lands_on():
    # Not the tag object: `git checkout v2.0.0` leaves HEAD at the commit.
    assert Advertisement.parse(ANNOTATED).revision_of('v2.0.0') == 'c0mm17ff'


def test_a_peeled_entry_is_never_a_ref_of_its_own():
    # `v2.0.0^{}` is a spelling of one tag, not a second tag, so it may reach
    # neither a resolved reference nor the list a range is matched against.
    parsed = Advertisement.parse(ANNOTATED)

    assert parsed.tags() == ['v2.0.0']
    assert advertisement.PEELED_SUFFIX not in str(parsed.refs)


# -- the tags a range is matched against ------------------------------------


def test_tags_leaves_out_what_is_not_one():
    assert Advertisement.parse(MAIN + 'cafebabe\trefs/tags/v1.2.0\n').tags() == [
        'v1.2.0'
    ]


def test_tags_keeps_only_what_a_regex_accepts():
    parsed = Advertisement.parse(
        MAIN + 'cafebabe\trefs/tags/v1.2.0\n' + 'deadbeef\trefs/tags/nightly-1.2.0\n'
    )

    assert parsed.tags(version_regex=r'^v') == ['v1.2.0']
