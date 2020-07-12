import sys
import re
import subprocess


class Version:
    def __init__(self, working_dir):
        self.gitlong = Version.retrieve_gitlong(working_dir=working_dir,
                                                default='v0.0.0')
        self.gitshort = Version.retrieve_gitshort(working_dir=working_dir,
                                                  default='v0.0.0')
        self.githash = Version.retrieve_githash(working_dir=working_dir)
        self.gitmessage = Version.retrieve_gitmessage(working_dir=working_dir,
                                                      commit_hash=self.githash)
        self.update_semver()

    def update_semver(self):
        self.gitlong_semver = self.gitlong

        if self.gitlong_semver[0] == 'v':
            self.gitlong_semver = self.gitlong_semver[1:]

        self.semver = self.gitshort

        if self.semver[0] == 'v':
            self.semver = self.semver[1:]

        regex = r'^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)(?:-(?P<prerelease>(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?(?:\+(?P<buildmetadata>[0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$'
        matches = re.search(regex, self.semver)

        self.major = int(matches.group('major'))
        self.minor = int(matches.group('minor'))
        self.patch = int(matches.group('patch'))
        self.prerelease = matches.group('prerelease')
        self.buildmetadata = matches.group('buildmetadata')

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
