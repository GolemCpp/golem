import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

from golemcpp.golem import helpers


# A cached resource is obtained from a Source. Today a Source is one of two kinds:
# a git repository (cloned) or a local directory (copied as-is).
SOURCE_TYPE_GIT = 'git'
SOURCE_TYPE_DIRECTORY = 'directory'

# A configured location may spell its kind: `<kind>+<locator>`.
SOURCE_KIND_SEPARATOR = '+'

# A leading bare word followed by the separator claims a kind. Kept narrow so a
# real locator never matches: a URL has `:` after its scheme, a path has none.
KIND_CLAIM = re.compile(r'^([a-z][a-z0-9]*)\{}'.format(SOURCE_KIND_SEPARATOR))


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
    def parse(cls, location, project_dir):
        '''
        The Source a configured location denotes: `<kind>+<locator>`, or a bare
        locator whose kind detect() works out.
        '''
        kind, locator = split_kind(location)
        normalized = cls.normalize_url(url=locator, project_dir=project_dir)
        return SOURCE_KINDS[kind or cls.detect(normalized)](normalized)

    @classmethod
    def detect(cls, location):
        '''
        The kind of a location that does not spell one: a local directory that is
        not a git checkout is copied, anything else is cloned.
        '''
        path = cls.parse_local_directory_path(location)
        if path is None or not os.path.isdir(path):
            return SOURCE_TYPE_GIT
        if helpers.is_git_repository(path=path):
            return SOURCE_TYPE_GIT
        return SOURCE_TYPE_DIRECTORY

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


# Every kind a location may claim, and how to build it. A new kind (an archive,
# an SVN checkout) is one entry here plus its branch in Context.clone_repository.
SOURCE_KINDS = {
    SOURCE_TYPE_GIT: Source.for_repository,
    SOURCE_TYPE_DIRECTORY: Source.for_directory,
}


def split_kind(location):
    '''
    The kind a location claims and the locator left once it is removed, the kind
    being None when nothing is claimed. A claim naming a kind we do not know is
    a typo worth reporting: read as a locator it would fail much later, inside
    git, against a path the user never wrote.
    '''
    match = KIND_CLAIM.match(location)
    if not match:
        return None, location

    kind = match.group(1)
    if kind not in SOURCE_KINDS:
        raise ValueError("unknown source kind '{}': expected {}".format(
            kind, ', '.join(name + SOURCE_KIND_SEPARATOR for name in SOURCE_KINDS)))

    return kind, location[match.end():]


def parse_location(value, context):
    '''A location setting into the Source it denotes.'''
    return Source.parse(value, project_dir=context.project_dir)


def format_location(source, context):
    '''
    The way a Source is spelled back into a setting, the reverse of
    parse_location. Always explicit: what is written is never re-detected.
    '''
    return '{}{}{}'.format(source.type, SOURCE_KIND_SEPARATOR, source.location)
