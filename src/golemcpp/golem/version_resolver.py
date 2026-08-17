'''
Shared version resolution for cached resources.

A `RequestedSource` asks for a version (e.g. a semver  range, a branch, a tag,
a commit) and `VersionResolver` resolves it against the remote to make it a
`ResolvedVersion`, which is then used to make a `Source`.
'''

import os
import re

from golemcpp.golem import helpers
from golemcpp.golem import source
from golemcpp.golem.resolved_version import ResolvedVersion
from semver import max_satisfying


# Regex to identify a semver range (Node-like version)
# Note that this regex isn't verified as bulletproof. In the resolution
# algorithm, it is rather an optimistic way to attempt finding a verbatim
# reference if this reference doesn't look like a version range.
VERSION_RANGE = re.compile(r'[\^~<>=|*\s]|(?:^|\.)[xX](?:\.|$)')


class VersionResolver:
    @staticmethod
    def is_range(version) -> bool:
        '''
        Does the version name a semver range or is it a ref?
        '''
        return bool(VERSION_RANGE.search(version or ''))

    @staticmethod
    def revision_of(url, ref) -> str:
        '''
        What is the revision corresponding to the ref on the remote? if any.
        '''
        answer = helpers.read_git(['ls-remote', url, ref], cwd=os.getcwd())
        if not answer:
            return ''
        return answer.splitlines()[0].split('\t')[0]

    @staticmethod
    def published_tags(url, version_regex='') -> list:
        '''
        Every tag the remote publishes, but without whatever `version_regex`
        rejects.
        '''
        listing = helpers.read_git(['ls-remote', '--tags', url], cwd=os.getcwd())
        named = '\n'.join(
            line for line in listing.split('\n') if '^{}' not in line)
        tags = set(re.findall(r'refs/tags/(.*)', named))

        if version_regex:
            pattern = re.compile(version_regex)
            tags = {tag for tag in tags if pattern.match(tag)}

        return list(tags)

    @staticmethod
    def resolve_requested(requested, resolved,
                          require_revision=False) -> ResolvedVersion:
        '''
        Resolve the version of a `RequestedSource`, and hand back the resolution
        already in hand when there is one.

        What counts as already resolved depends on the caller. A kind keyed on
        the commit needs the revision, therefore it asks for `require_revision`
        and a resolution naming only a reference sends it to the remote.
        '''
        already = bool(resolved.revision) if require_revision else bool(resolved)
        if requested.type != source.SOURCE_TYPE_GIT or already:
            return resolved

        return VersionResolver.resolve(requested)

    @staticmethod
    def resolve(requested) -> ResolvedVersion:
        '''
        Resolve what a `RequestedSource` asks for, returning a `ResolvedVersion`.

        First, if the asked version doesn't look like a version range, try to find
        it verbatim on the remote.

        Second, we assume the asked version is a range. We gather the tags looking
        like semvers and normalize them to find if any matches. Multiples can match
        so only the last one is selected to follow what OpenSSL does.

        Third, if nothing matched keep the version as it stands, like a commit hash.
        '''
        url = str(requested.locator)
        version = requested.version

        if version and not VersionResolver.is_range(version):
            revision = VersionResolver.revision_of(url, version)
            if revision:
                return ResolvedVersion(reference=version, revision=revision)

        found_version = VersionResolver.find_version(
            VersionResolver.published_tags(url, requested.version_regex), version)
        if found_version:
            revision = VersionResolver.revision_of(
                url, 'refs/tags/' + found_version)
            if not revision:
                raise RuntimeError(
                    "Can't find any hash related to found tag {}".format(
                        found_version))
            return ResolvedVersion(reference=found_version, revision=revision)

        return ResolvedVersion(reference=version, revision=version)

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
