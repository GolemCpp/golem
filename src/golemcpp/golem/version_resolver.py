'''
Shared version resolution for cached resources.

Given a remote `url` and a requested `version` (a semver spec, a branch, or an
exact ref), resolve it to a concrete `(resolved_version, resolved_hash)` pair by
querying the remote's git tags. Extracted from `Dependency.resolve` so every
resource kind (dependencies, tools, repositories) resolves versions identically.
'''

import os
import re

from golemcpp.golem import helpers
from semver import max_satisfying


class VersionResolver:
    @staticmethod
    def resolve(url, version, version_regex=''):
        '''
        Resolve `version` against `url`'s git tags, returning
        `(resolved_version, resolved_hash)`.

        Semantics (unchanged from the original Dependency.resolve):
        - The semver spec is matched against the remote tags (optionally
          pre-filtered by `version_regex`); on a match the tag and its sha are
          returned.
        - With no tag match, the value is treated as a branch head (`ls-remote
          --heads`); failing that, it is used literally as both version and hash.
        '''
        tags = helpers.read_git(
            ['ls-remote', '--tags', url], cwd=os.getcwd())
        tags = tags.split('\n')
        tmp = ''
        for line in tags:
            if '^{}' not in line:
                tmp += line + '\n'
        tags = tmp
        versions_list = re.findall(r'refs\/tags\/(.*)', tags)
        versions_list = list(set(versions_list))

        if version_regex:
            pattern = re.compile(version_regex)
            versions_list = [s for s in versions_list if pattern.match(s)]

        found_version = VersionResolver.find_version(versions_list, version)
        if found_version:
            hash = helpers.read_git(
                ['ls-remote', '--tags', url, 'refs/tags/' + found_version],
                cwd=os.getcwd())
            if not hash:
                raise RuntimeError(
                    "Can't find any hash related to found tag {}".format(
                        found_version))
            hash = hash.splitlines()[0]
            hash = hash.split('\t')[0]
            return found_version, hash

        resolved_version = version
        hash = helpers.read_git(
            ['ls-remote', '--heads', url, version], cwd=os.getcwd())
        if hash:
            hash = hash.splitlines()[0]
            hash = hash.split('\t')[0]
            resolved_hash = hash
        else:
            resolved_hash = version
        return resolved_version, resolved_hash

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
