import sys
import re
import subprocess


class Version:
    def __init__(self, working_dir=None, build_number=None):
        if not working_dir:
            self.gitlong = 'v0.0.0'
            self.gitshort = 'v0.0.0'
            self.githash = ''
            self.gitmessage = ''
            self.gitbranch = ''
            self.build_number = build_number
            self.update_semver()
            return

        self.gitlong = Version.retrieve_gitlong(working_dir=working_dir,
                                                default='v0.0.0')
        self.gitshort = Version.retrieve_gitshort(working_dir=working_dir,
                                                  default='v0.0.0')
        self.githash = Version.retrieve_githash(working_dir=working_dir)
        self.gitmessage = Version.retrieve_gitmessage(working_dir=working_dir,
                                                      commit_hash=self.githash)
        self.gitbranch = Version.retrieve_gitbranch(working_dir=working_dir,
                                                    default='')
        self.build_number = build_number
        self.update_semver()

    def force_version(self, version):
        self.gitlong = version
        self.gitshort = version
        self.update_semver()

    def update_semver(self):
        git_hash = Version.parse_git_hash(self.gitlong)

        if git_hash:
            self.gitshort = git_hash[0]
            self.gitlong = git_hash[1]

            self.gitlong_semver = '0.0.0'
            self.semver = '0.0.0'
        else:
            self.gitlong_semver = self.gitlong
            self.semver = self.gitshort

        if self.gitlong_semver[0] == 'v':
            self.gitlong_semver = self.gitlong_semver[1:]

        if self.semver[0] == 'v':
            self.semver = self.semver[1:]

        pair = Version.parse_semver(self.semver)

        if not pair:
            self.semver = '0.0.0'
            version, matches = Version.parse_semver(self.semver)
        else:
            version = pair[0]
            matches = pair[1]

        self.semver = version

        self.major = int(matches.group('major'))
        self.minor = int(matches.group('minor'))
        self.patch = int(matches.group('patch'))
        self.prerelease = matches.group('prerelease') if matches.group(
            'prerelease') else ''
        self.buildmetadata = matches.group('buildmetadata') if matches.group(
            'buildmetadata') else ''
        self.semver_short = str(self.major) + '.' + str(
            self.minor) + '.' + str(self.patch)

        if not self.buildmetadata and self.build_number:
            self.buildmetadata = str(self.build_number)

        self.semver = Version.make_semver(major=self.major,
                                          minor=self.minor,
                                          patch=self.patch,
                                          prerelease=self.prerelease,
                                          buildmetadata=self.buildmetadata)

    def to_semver_string(self):
        return Version.make_semver(major=self.major,
                                   minor=self.minor,
                                   patch=self.patch,
                                   prerelease=self.prerelease,
                                   buildmetadata=self.buildmetadata)

    @staticmethod
    def make_semver(major, minor, patch, prerelease, buildmetadata):
        if major is None:
            major = 0
        if minor is None:
            minor = 0
        if patch is None:
            patch = 0
        new_version = str(major)
        new_version += '.' + str(minor)
        new_version += '.' + str(patch)
        if prerelease:
            new_version += '-' + prerelease
        if buildmetadata:
            new_version += '+' + buildmetadata
        return new_version

    @staticmethod
    def parse_git_hash(version):
        hash_regex = r'^[0-9a-fA-F]{7,40}$'
        if re.fullmatch(hash_regex, version):
            return version[:7], version
        return None

    @staticmethod
    def parse_semver(version):
        semver_regex = r'^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)(?:-(?P<prerelease>(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?(?:\+(?P<buildmetadata>[0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$'
        matches = re.search(semver_regex, version)
        if matches:
            return (version, matches)

        # Allow alternative separators,
        # but force having Major, Minor and Patch defined
        semver_regex_like = r'(?P<major>0|[1-9]\d*)[\._](?P<minor>0|[1-9]\d*)[\._](?P<patch>0|[1-9]\d*)(?:[-\._](?P<prerelease>(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:[\._](?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?(?:\+(?P<buildmetadata>[0-9a-zA-Z-]+(?:[\._][0-9a-zA-Z-]+)*))?'
        matches = re.search(semver_regex_like, version)
        if matches:
            new_version = Version.make_semver(
                major=matches.group('major'),
                minor=matches.group('minor'),
                patch=matches.group('patch'),
                prerelease=matches.group('prerelease'),
                buildmetadata=matches.group('buildmetadata'))
            return (new_version, matches)

        # Allow alternative separators
        semver_regex_like = r'(?P<major>0|[1-9]\d*)(?:[\._](?P<minor>0|[1-9]\d*))?(?:[\._](?P<patch>0|[1-9]\d*))?(?:[-\._](?P<prerelease>(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:[\._](?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?(?:\+(?P<buildmetadata>[0-9a-zA-Z-]+(?:[\._][0-9a-zA-Z-]+)*))?'
        matches = re.search(semver_regex_like, version)
        if matches:
            new_version = Version.make_semver(
                major=matches.group('major'),
                minor=matches.group('minor'),
                patch=matches.group('patch'),
                prerelease=matches.group('prerelease'),
                buildmetadata=matches.group('buildmetadata'))
            return (new_version, matches)

        return None

    @staticmethod
    def retrieve_gitlong(working_dir, default=None):

        version_string = None

        try:
            version_string = subprocess.check_output(
                ['git', 'describe', '--long', '--tags', '--dirty=-d'],
                cwd=working_dir,
                stderr=subprocess.DEVNULL).decode(sys.stdout.encoding)
            version_string = version_string.splitlines()[0]
        except:
            version_string = default

        return version_string

    @staticmethod
    def retrieve_gitshort(working_dir, default=None):

        version_string = None

        try:
            version_string = subprocess.check_output(
                ['git', 'describe', '--abbrev=0', '--tags'],
                cwd=working_dir,
                stderr=subprocess.DEVNULL).decode(sys.stdout.encoding)
            version_string = version_string.splitlines()[0]
        except:
            version_string = default

        return version_string

    @staticmethod
    def retrieve_githash(working_dir):
        version_string = None

        try:
            version_string = subprocess.check_output(
                ['git', 'rev-parse', 'HEAD'],
                cwd=working_dir,
                stderr=subprocess.DEVNULL).decode(sys.stdout.encoding)
            version_string = version_string.splitlines()[0]
        except:
            version_string = ''

        return version_string

    @staticmethod
    def retrieve_gitmessage(working_dir, commit_hash):

        message = None

        if not commit_hash:
            return ''

        try:
            message = subprocess.check_output(
                ['git', 'log', '--format=%B', '-n', '1', commit_hash],
                cwd=working_dir,
                stderr=subprocess.DEVNULL).decode(sys.stdout.encoding)
            message = message.strip()
        except:
            message = ''

        return message

    @staticmethod
    def retrieve_gitbranch(working_dir, default=None):

        branch = None

        try:
            branch = subprocess.check_output(
                ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
                cwd=working_dir,
                stderr=subprocess.DEVNULL).decode(sys.stdout.encoding)
            branch = branch.strip()
        except:
            branch = default

        return branch
