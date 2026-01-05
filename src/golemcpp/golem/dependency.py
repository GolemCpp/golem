import re
import os
import subprocess
import pickle
from golemcpp.golem import helpers
from golemcpp.golem.cache import CacheConf
from golemcpp.golem.configuration import Configuration
from golemcpp.golem.condition_expression import ConditionExpression
from golemcpp.golem.helpers import *
from semver import max_satisfying
from collections import OrderedDict


class Dependency(Configuration):
    def __init__(self,
                 name=None,
                 targets=None,
                 repository=None,
                 version=None,
                 version_regex=None,
                 variant=None,
                 link=None,
                 runtime=None,
                 shallow=False):
        super(Dependency, self).__init__(targets=targets,
                                         type='library',
                                         variant=variant,
                                         link=link,
                                         runtime=runtime)
        self.name = '' if name is None else name
        self.repository = '' if repository is None else repository
        self.version = '' if version is None else version
        self.version_regex = '' if version_regex is None else version_regex
        self.resolved_version = ''
        self.resolved_hash = ''
        self.shallow = shallow
        self.cache_dir = None
        self.dynamically_added = False

    def __str__(self):
        return helpers.print_obj(self)

    def update_cache_dir(self, context):
        self.cache_dir = context.find_dep_cache_dir(
            dep=self, cache_conf=context.cache_conf)

    def resolve(self):

        if self.resolved_hash:
            return self.resolved_hash

        tags = subprocess.check_output(
            ['git', 'ls-remote', '--tags',
             self.repository]).decode(sys.stdout.encoding)
        tags = tags.split('\n')
        tmp = ''
        for line in tags:
            if '^{}' not in line:
                tmp += line + '\n'
        tags = tmp
        versions_list = re.findall(r'refs\/tags\/(.*)', tags)
        versions_list = set(versions_list)
        versions_list = list(versions_list)

        if self.version_regex:
            p = re.compile(self.version_regex)
            versions_list = [s for s in versions_list if p.match(s)]

        found_version = Dependency.find_version(versions_list, self.version)
        if found_version:
            hash = subprocess.check_output([
                'git', 'ls-remote', '--tags', self.repository,
                'refs/tags/' + found_version
            ]).decode(sys.stdout.encoding)
            if not hash:
                raise RuntimeError(
                    "Can't find any hash related to found tag {}".format(
                        found_version))
            hash = hash.splitlines()[0]
            hash = hash.split('\t')[0]
            self.resolved_hash = hash
            self.resolved_version = found_version
        else:
            self.resolved_version = self.version
            hash = subprocess.check_output(
                ['git', 'ls-remote', '--heads', self.repository,
                 self.version]).decode(sys.stdout.encoding)
            if hash:
                hash = hash.splitlines()[0]
                hash = hash.split('\t')[0]
                self.resolved_hash = hash
            else:
                self.resolved_hash = self.version

        if not self.resolved_hash:
            raise RuntimeError(
                "Bad version {} can't find any hash related".format(
                    self.version))

        print("{}: {} -> {} ({})".format(self.name, self.version,
                                         self.resolved_version,
                                         self.resolved_hash))
        return self.resolved_hash

    def build(self, context, config):
        context.dep_command(config, self, 'build', False)

    def configure(self, context, config):
        context.dep_command(config, self, 'resolve', False)

    @staticmethod
    def serialized_members():
        return [
            'name', 'repository', 'version', 'version_regex',
            'resolved_version', 'resolved_hash', 'shallow'
        ]

    @staticmethod
    def serialize_to_json(o, avoid_lists=False):
        json_obj = Configuration.serialize_to_json(o, avoid_lists=avoid_lists)

        for key in o.__dict__:
            if key in Dependency.serialized_members():
                if o.__dict__[key]:
                    json_obj[key] = o.__dict__[key]

        return json_obj

    def read_json(self, o):
        Configuration.read_json(self, o)

        for key, value in o.items():
            if key in Dependency.serialized_members():
                self.__dict__[key] = value

    @staticmethod
    def unserialize_from_json(o):
        dependency = Dependency()
        dependency.read_json(o)
        return dependency

    @staticmethod
    def save_cache(dependencies):
        cache = []

        for dependency in dependencies:
            json = Dependency.serialize_to_json(dependency, avoid_lists=True)
            cache.append(json)

        return cache

    @staticmethod
    def load_cache(cache):
        dependencies = []

        for item in cache:
            dependency = Dependency.unserialize_from_json(item)
            dependencies.append(dependency)

        return dependencies

    @staticmethod
    def find_version(versions, ver):
        semver_regex = r'^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)(?:-(?P<prerelease>(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?(?:\+(?P<buildmetadata>[0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$'

        semver_regex_like = r'(?P<major>0|[1-9]\d*)[\._\-](?P<minor>0|[1-9]\d*)[\._\-](?P<patch>0|[1-9]\d*)(?:[-\._\-](?P<prerelease>(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:[\._\-](?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?(?:\+(?P<buildmetadata>[0-9a-zA-Z-]+(?:[\._\-][0-9a-zA-Z-]+)*))?'

        semver_list = []

        transformed_versions = dict()

        for v in versions:
            semver = re.search(semver_regex, v)
            if not semver:
                matches = re.search(semver_regex_like, v)
                if not matches:
                    continue
                new_version = matches.group('major')
                if matches.group('minor'):
                    new_version += '.' + matches.group('minor')
                    if matches.group('patch'):
                        new_version += '.' + matches.group('patch')
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

            #if len(v_list) > 1:
            #    raise RuntimeError(
            #        "Found more than one matching version: {} -> {}".format(
            #            ver, v_list))

            return v_list[0]