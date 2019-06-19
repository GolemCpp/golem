import re
import os
import subprocess
import pickle
import helpers
import distutils
from distutils import dir_util
from cache import CacheConf
# from context import Context
from configuration import Configuration
from helpers import *


class Dependency:
    def __init__(self, name=None, targets=None, repository=None, version=None, link=None):
        self.name = '' if name is None else name
        self.targets = [] if targets is None else targets
        self.repository = '' if repository is None else repository
        self.version = '' if version is None else version
        self.resolved_version = ''
        self.type = 'library'
        self.link = link

    def __str__(self):
        return helpers.print_obj(self)

    def resolve(self):
        if self.resolved_version:
            return self.resolved_version

        dep_version = ''
        if str(self.version) == 'latest':
            tags = subprocess.check_output(
                ['git', 'ls-remote', '--tags', self.repository])
            tags = tags.split('\n')
            badtag = ['^{}']
            tmp = ''
            for line in tags:
                if '^{}' not in line:
                    tmp += line + '\n'
            tags = tmp
            versions_list = re.findall('refs\/tags\/v(\d*(?:\.\d*)*)', tags)
            versions_list = set(versions_list)
            versions_list = list(versions_list)
            versions_list.sort(key=lambda s: map(int, s.split('.')))
            last = versions_list[-1:]
            if not last:
                print("ERROR: no latest version")
                return
            last = 'v' + last[0]
            hash = subprocess.check_output(
                ['git', 'ls-remote', '--tags', self.repository, last])
            if not hash:
                print("ERROR: can't find " + last)
                return
            # dep_version = hash[:8]
            dep_version = last
        else:
            hash = subprocess.check_output(
                ['git', 'ls-remote', '--heads', self.repository, str(self.version)])
            if hash:
                dep_version = hash[:8]
            else:
                dep_version = str(self.version)

        self.resolved_version = dep_version
        return self.resolved_version

    def build(self, context, config):
        context.dep_command(
            config, self, context.make_cache_conf(), 'build', False)

    def configure(self, context, config):
        context.dep_command(
            config, self, context.make_cache_conf(), 'resolve', False)
