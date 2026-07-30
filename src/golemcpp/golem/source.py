import os
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

from golemcpp.golem import helpers


# A cached resource is obtained from a Source. Today a Source is one of two kinds:
# a git repository (cloned) or a local directory (copied as-is).
SOURCE_TYPE_GIT = 'git'
SOURCE_TYPE_DIRECTORY = 'directory'


@dataclass(frozen=True)
class Source:
    # `location` is the URL (git) or the folder path (directory). `version` is the
    # requested git ref (only meaningful for a git source).
    location: str
    reference: str = 'main'
    type: str = SOURCE_TYPE_GIT

    @classmethod
    def for_repository(cls, location, reference='main'):
        return cls(location=location, reference=reference, type=SOURCE_TYPE_GIT)

    @classmethod
    def for_directory(cls, location):
        return cls(location=location, reference='', type=SOURCE_TYPE_DIRECTORY)

    @classmethod
    def detect(cls, locator, project_dir, reference='main'):
        '''
        Classify a bare locator string (used where a source is configured as a
        single value, e.g. recipes/overrides repositories) into a git repository
        or a local directory to copy.
        '''
        normalized = cls.normalize_url(url=locator, project_dir=project_dir)
        if cls.parse_local_non_git_repository(normalized) is not None:
            return cls.for_directory(normalized)
        return cls.for_repository(normalized, reference)

    # -- identity serialization (recorded in a resource manifest) ---------

    def to_dict(self) -> dict:
        return {
            'type': self.type,
            'location': self.location,
            'reference': self.reference,
        }

    @classmethod
    def from_dict(cls, source: dict) -> 'Source':
        return cls(
            location=helpers.first_non_empty_among_keys(source, 'location'),
            reference=helpers.first_non_empty_among_keys(source, 'reference'),
            type=helpers.first_non_empty_among_keys(source, 'type') or SOURCE_TYPE_GIT)

    @classmethod
    def from_manifest(cls, manifest) -> 'Source':
        return cls.from_dict((manifest.source or {}) if manifest else {})

    @property
    def label(self) -> str:
        '''Human label, e.g. "<location> <reference>"; empty when no location.'''
        if not self.location:
            return ''
        if self.reference:
            return '{} {}'.format(self.location, self.reference)
        return self.location

    @staticmethod
    def normalize_url(url, project_dir):
        if (url.startswith("http://") or url.startswith("https://")
                or url.startswith("ssh://") or url.startswith("file://")):
            return url
        path = os.path.join(project_dir, url)
        path = os.path.realpath(path)
        return Path(path).as_uri()

    @staticmethod
    def parse_local_directory_path(url):
        parsed = urlparse(url)

        if parsed.scheme != 'file':
            return None

        path = unquote(parsed.path)

        if sys.platform.startswith("win"):
            if path.startswith("/") and len(path) > 2 and path[2] == ":":
                path = path[1:]
            path = path.replace("/", "\\")

        return path

    @staticmethod
    def is_git_repository(path):
        git_index = os.path.join(path, '.git', 'HEAD')
        return os.path.exists(git_index)

    @classmethod
    def parse_local_non_git_repository(cls, url):
        path = cls.parse_local_directory_path(url)
        if path is None:
            return None

        if not os.path.isdir(path):
            return None

        if cls.is_git_repository(path=path):
            return None

        return path

    @staticmethod
    def generate_id(url):
        is_filesystem = False
        is_http = False
        is_ssh = False

        if os.path.exists(url):
            url = Path(url).resolve().as_uri()
        if url.startswith('file:///'):
            url = url.replace('file:///', 'file://')

        if url.startswith('file://'):
            is_filesystem = True
        elif url.startswith('http://') or url.startswith('https://'):
            is_http = True
        elif url.startswith('ssh://'):
            is_ssh = True
        else:
            is_ssh = True

        parsed = urlparse(url)
        if is_filesystem:
            host = ['fsys'] + parsed.hostname.split('.')
        else:
            host = parsed.hostname.split('.')
            host.reverse()
        path = list(filter(None, parsed.path.split('/')))

        if len(path) > 0 and path[-1].endswith('.git'):
            path[-1] = path[-1][:-4]

        path = list(filter(None, path))

        identifier = host + path
        for index, item in enumerate(identifier):
            identifier[index] = ''.join(
                filter(
                    lambda x: x in
                    "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ-_",
                    item)).lower()

        name = identifier[-1]
        host = identifier[:-1]

        host = '.'.join(host)

        if not host:
            host = '_no_host_'

        repo_id = name + '@' + host

        return ''.join(repo_id)

    @classmethod
    def make_repository_base(cls, location, reference):
        repo_id = cls.generate_id(location)
        return repo_id + '+' + str(reference)

    def get_local_path(self):
        return self.parse_local_directory_path(self.location)

    def get_id(self):
        return self.generate_id(self.location)

    def get_cache_key(self):
        return self.make_repository_base(self.location, self.reference)
