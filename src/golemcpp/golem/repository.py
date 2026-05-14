import os
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse


@dataclass(frozen=True)
class Repository:
    url: str
    reference: str = 'main'

    @classmethod
    def from_url(cls, url, project_dir, reference='main'):
        return cls(url=cls.normalize_url(url=url, project_dir=project_dir),
                   reference=reference)

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
    def generate_recipe_id(url):
        is_filesystem = False
        is_http = False
        is_ssh = False

        if os.path.exists(url):
            url = 'file://' + url
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
    def make_repository_base(cls, repository, resolved_version):
        repo_id = cls.generate_recipe_id(repository)
        return repo_id + '+' + str(resolved_version)

    def get_local_path(self):
        return self.parse_local_directory_path(self.url)

    def get_non_git_directory_path(self):
        return self.parse_local_non_git_repository(self.url)

    def get_recipe_id(self):
        return self.generate_recipe_id(self.url)

    def get_cache_key(self):
        return self.make_repository_base(self.url, self.reference)
