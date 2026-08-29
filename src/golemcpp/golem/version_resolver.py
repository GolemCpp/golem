'''
Shared version resolution for cached resources.

A `RequestedSource` asks for a version (e.g. a semver  range, a branch, a tag,
a commit) and `VersionResolver` resolves it against the remote to make it a
`ResolvedVersion`, which is then used to make a `Source`.
'''

import os
import re

from golemcpp.golem import advertisement_store
from golemcpp.golem import helpers
from golemcpp.golem import source
from golemcpp.golem.resolved_version import ResolvedVersion
from golemcpp.golem.version import Version
from semver import max_satisfying

# `advertisement` is the local name every resolution works from, therefore these
# come in directly rather than through the module they would shadow.
from golemcpp.golem.advertisement import (
    ADVERTISED_PREFIXES,
    Advertisement,
    HEAD_VERSION,
    TAG_PREFIX,
)


class VersionResolver:
    @staticmethod
    def advertised(url) -> Advertisement:
        '''
        Ask the remote what it publishes. The one call a resolution makes, and
        none at all when a resolve already asked this remote.
        '''
        listing = advertisement_store.read(url)

        if not listing:
            listing = helpers.read_git(
                ['ls-remote', '--symref', url] + list(ADVERTISED_PREFIXES),
                cwd=os.getcwd(),
            )
            advertisement_store.write(url, listing)

        return Advertisement.parse(listing)

    @staticmethod
    def resolve_requested(
        requested, resolved, require_revision=False
    ) -> ResolvedVersion:
        '''
        Resolve the version of a `RequestedSource`, unless the resolution
        given already answers.

        With `require_revision`, a commit is mandatory: not finding one raises.

        A directory is returned as given: it names no remote to ask.
        '''
        already = bool(resolved.revision) if require_revision else bool(resolved)
        if requested.type != source.SOURCE_TYPE_GIT or already:
            return resolved

        resolved = VersionResolver.resolve(requested)
        if require_revision and not resolved.revision:
            raise RuntimeError(
                "no commit of '{}' answers version '{}'".format(
                    requested.locator, requested.version
                )
            )

        return resolved

    @staticmethod
    def resolve(requested) -> ResolvedVersion:
        '''
        Resolve what a `RequestedSource` asks for, returning a `ResolvedVersion`.

        The remote is asked once, then answers in five steps:

        1. No version, or `HEAD`: the default branch. Asking for nothing is
        asking for what a plain `git clone` gives.

        2. A ref by that name, looked up the way git looks a bare name up.

        3. Gather the tags looking like semvers and normalize them to find
        if any matches. Multiples can match so only the last one is selected to
        follow what OpenSSL does.

        4. Accept a commit as standing for itself. `ls-remote` matches ref
        names, therefore it can never have answered the second step with one.

        5. Nothing names it. Raise here, where the version asked for is
        still at hand, rather than hand git a value it cannot resolve either.
        '''
        url = str(requested.locator)
        version = requested.version
        advertisement = VersionResolver.advertised(url)

        if not version or version == HEAD_VERSION:
            revision = advertisement.revision_of(HEAD_VERSION)
            if not advertisement.head_reference or not revision:
                raise RuntimeError(
                    "nothing in '{}' answers version '{}'".format(url, version)
                )
            return ResolvedVersion(
                reference=advertisement.head_reference, revision=revision
            )

        revision = advertisement.revision_of(version)
        if revision:
            return ResolvedVersion(reference=version, revision=revision)

        found_version = VersionResolver.find_version(
            advertisement.tags(requested.version_regex), version
        )
        if found_version:
            return ResolvedVersion(
                reference=found_version,
                revision=advertisement.revision_of(TAG_PREFIX + found_version),
            )

        if Version.parse_git_hash(version):
            return ResolvedVersion(reference=version, revision=version)

        raise RuntimeError("nothing in '{}' answers version '{}'".format(url, version))

    @staticmethod
    def find_version(versions, ver):
        semver_regex = r'^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)(?:-(?P<prerelease>(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?(?:\+(?P<buildmetadata>[0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$'

        semver_regex_like = r'(?P<major>0|[1-9]\d*)[\._\-](?P<minor>0|[1-9]\d*)[\._\-](?P<patch>0|[1-9]\d*)(?:[-\._\-](?P<prerelease>(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:[\._\-](?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?(?:\+(?P<buildmetadata>[0-9a-zA-Z-]+(?:[\._\-][0-9a-zA-Z-]+)*))?'

        semver_short_regex_like = r'(?P<major>0|[1-9]\d*)(?:[\._\-](?P<minor>0|[1-9]\d*)(?:[\._\-](?P<patch>0|[1-9]\d*)(?:[-\._\-](?P<prerelease>(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:[\._\-](?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?(?:\+(?P<buildmetadata>[0-9a-zA-Z-]+(?:[\._\-][0-9a-zA-Z-]+)*))?)?)?'

        semver_list = []

        transformed_versions = dict()

        for v in versions:
            semver = re.search(semver_regex, v)
            if not semver:
                matches = re.search(semver_regex_like, v)
                if not matches:
                    matches = re.search(semver_short_regex_like, v)
                    if not matches:
                        continue
                new_version = matches.group('major')
                new_version += '.' + (matches.group('minor') or '0')
                new_version += '.' + (matches.group('patch') or '0')
                if matches.group('prerelease'):
                    new_version += '-' + matches.group('prerelease')
                if matches.group('buildmetadata'):
                    new_version += '+' + matches.group('buildmetadata')

                if new_version not in semver_list:
                    semver_list.append(new_version)
                if new_version not in transformed_versions:
                    transformed_versions[new_version] = []
                transformed_versions[new_version].append(v)
                continue
            if v not in semver_list:
                semver_list.append(v)
            if v not in transformed_versions:
                transformed_versions[v] = []
            transformed_versions[v].append(v)

        v = max_satisfying(semver_list, ver)

        if not v:
            return None

        if v in transformed_versions:

            # OpenSSL convention is OpenSSL_1_1_1j
            # The problem is the letter at the end
            # So ~1.1.1 matches multiple versions

            # Having no solution at the moment for this use case, matching
            # multiple versions is accepted and the list of versions is reverse
            # sorted...

            v_list = transformed_versions[v]
            if not v_list:
                return None
            v_list.sort(reverse=True)

            return v_list[0]


def report_resolution(name, version, resolved):
    '''Say what a version resolved to, under the name the resource goes by.'''
    # Asking for nothing is asking for HEAD, so say that rather than leave a gap
    # where the question goes.
    print(
        "{}: {} -> {} ({})".format(
            name, version or HEAD_VERSION, resolved.reference, resolved.revision
        )
    )
