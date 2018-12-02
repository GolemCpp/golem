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
    def __init__(self, name=None, repository=None, version=None):
        self.name = '' if name is None else name
        self.repository = '' if repository is None else repository
        self.version = '' if version is None else version
        self.resolved_version = ''

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
            #dep_version = hash[:8]
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

    def get_target_filename(self, context):
        return [self.name + context.variant_suffix() + '.dll', self.name + context.variant_suffix() + '.lib', self.name + context.variant_suffix() + '.exe'] if context.is_windows() else ['lib' + self.name + context.variant_suffix() + '.so', self.name + context.variant_suffix()]

    def build(self, context):

        cache_conf = context.find_cache_conf()
        if not cache_conf:
            cache_conf = CacheConf()
            cache_conf.location = context.make_cache_dir()

        cache_location = cache_conf.location
        cache_repo = cache_conf.remote

        if not os.path.exists(cache_location):
            os.makedirs(cache_location)

        dep_version = self.resolve()
        dep_version_branch = dep_version
        if self.version != 'latest' and dep_version != self.version:
            dep_version_branch = self.version

        dep_path_base = make_dep_base(self)
        dep_path = os.path.join(cache_location, dep_path_base)

        dep_path_include = os.path.join(dep_path, 'include')
        dep_path_build = os.path.join(dep_path, context.build_path())

        # if os.path.exists(dep_path):
        #	removeTree(self, dep_path)
        # os.makedirs(dep_path)
        if not os.path.exists(dep_path):
            os.makedirs(dep_path)

        should_copy = False
        beacon_build_done = os.path.join(
            context.make_out_path(), self.name + '.pkl')

        if not os.path.exists(beacon_build_done):
            should_copy = True

            dep_path_build_target = os.path.join(
                dep_path_build, self.name + '.pkl')
            if not os.path.exists(dep_path_build_target):
                print "INFO: can't find the dependency " + self.name
                print "Search in the cache repository..."

                should_build = True
                # search the corresponding branch in the cache repo (with the right version)
                if cache_repo:
                    ret = subprocess.call(
                        ['git', 'ls-remote', '--heads', '--exit-code', cache_repo, dep_path_build])
                    if not ret:
                        should_build = False

                if should_build:
                    print "Nothing in cache, have to build..."

                    # building
                    build_dir = os.path.join(dep_path, 'repository')
                    if os.path.exists(build_dir):
                        # removeTree(self, build_dir)
                        ret = subprocess.call(
                            ['git', 'reset', '--hard'], cwd=build_dir)
                        ret = subprocess.call(
                            ['git', 'clean', '-fxd'], cwd=build_dir)
                        ret = 0
                    else:
                        os.makedirs(build_dir)
                        # removed ['--depth', '1'] because of git describe --tags
                        ret = subprocess.call(['git', 'clone', '--recursive', '--branch',
                                               dep_version_branch, '--', self.repository, '.'], cwd=build_dir)
                    if ret:
                        raise RuntimeError(
                            "ERROR: cloning " + self.repository + ' ' + dep_version_branch)

                    if context.is_windows():
                        ret = subprocess.check_output(['golem', '--targets=' + self.name, '--runtime=' + context.context.options.runtime, '--link=' + context.context.options.link, '--arch=' +
                                                       context.context.options.arch, '--variant=' + context.context.options.variant, '--export=' + dep_path, '--cache-dir=' + context.make_cache_dir(), '--static-cache-dir=' + context.make_static_cache_dir(), '--dir=' + dep_path_build + '-build'], cwd=build_dir, shell=True)
                    else:
                        ret = subprocess.check_output(['golem', '--targets=' + self.name, '--runtime=' + context.context.options.runtime, '--link=' + context.context.options.link,
                                                       '--arch=' + context.context.options.arch, '--variant=' + context.context.options.variant, '--export=' + dep_path, '--cache-dir=' + context.make_cache_dir(), '--static-cache-dir=' + context.make_static_cache_dir(), '--dir=' + dep_path_build + '-build'], cwd=build_dir)
                    print ret

        filepkl = open(os.path.join(dep_path_build, self.name + '.pkl'), 'rb')
        dep_export_ctx = pickle.load(filepkl)
        depdeps = None
        if isinstance(dep_export_ctx, Configuration):
            depconfig = dep_export_ctx
        else:
            depdeps = dep_export_ctx[0]
            depconfig = dep_export_ctx[1]
        filepkl.close()
        depconfig.includes = []

        if depdeps is not None:
            context.project.deps = dict((obj.name, obj) for obj in (
                context.project.deps + depdeps)).values()

        if should_copy:
            distutils.dir_util.copy_tree(
                dep_path_build, context.make_out_path())

    def configure(self, context, config):

        cache_conf = context.find_cache_conf()
        if not cache_conf:
            cache_conf = CacheConf()
            cache_conf.location = context.make_cache_dir()

        cache_location = cache_conf.location
        cache_repo = cache_conf.remote

        if not os.path.exists(cache_location):
            os.makedirs(cache_location)

        dep_version = self.resolve()
        dep_version_branch = dep_version
        if self.version != 'latest' and dep_version != self.version:
            dep_version_branch = self.version

        dep_path_base = make_dep_base(self)
        dep_path = os.path.join(cache_location, dep_path_base)

        dep_path_include = os.path.join(dep_path, 'include')
        dep_path_build = os.path.join(dep_path, context.build_path())

        # if os.path.exists(dep_path):
        #	removeTree(self, dep_path)
        # os.makedirs(dep_path)
        if not os.path.exists(dep_path):
            os.makedirs(dep_path)

        should_copy = False
        beacon_build_done = os.path.join(
            context.make_out_path(), self.name + '.pkl')

        if not os.path.exists(beacon_build_done):
            should_copy = True

            if not os.path.exists(dep_path_build):
                print "INFO: can't find the dependency " + self.name
                print "Search in the cache repository..."

                should_build = True
                # search the corresponding branch in the cache repo (with the right version)
                if cache_repo:
                    ret = subprocess.call(
                        ['git', 'ls-remote', '--heads', '--exit-code', cache_repo, dep_path_build])
                    if not ret:
                        should_build = False

                if should_build:
                    print "Nothing in cache, have to build..."

                    # building
                    build_dir = os.path.join(dep_path, 'repository')
                    if os.path.exists(build_dir):
                        removeTree(self, build_dir)
                    os.makedirs(build_dir)

                    # removed ['--depth', '1'] because of git describe --tags
                    ret = subprocess.call(['git', 'clone', '--recursive', '--branch',
                                           dep_version_branch, '--', self.repository, '.'], cwd=build_dir)
                    if ret:
                        print "ERROR: cloning " + self.repository + ' ' + dep_version_branch
                        return

                    if context.is_windows():
                        ret = subprocess.check_output(['golem', 'resolve', '--targets=' + self.name, '--runtime=' + context.context.options.runtime, '--link=' + context.context.options.link, '--arch=' +
                                                       context.context.options.arch, '--variant=' + context.context.options.variant, '--export=' + dep_path, '--cache-dir=' + context.make_cache_dir(), '--static-cache-dir=' + context.make_static_cache_dir(), '--dir=' + dep_path_build + '-build'], cwd=build_dir, shell=True)
                    else:
                        ret = subprocess.check_output(['golem', 'resolve', '--targets=' + self.name, '--runtime=' + context.context.options.runtime, '--link=' + context.context.options.link,
                                                       '--arch=' + context.context.options.arch, '--variant=' + context.context.options.variant, '--export=' + dep_path, '--cache-dir=' + context.make_cache_dir(), '--static-cache-dir=' + context.make_static_cache_dir(), '--dir=' + dep_path_build + '-build'], cwd=build_dir)
                    print ret

        filepkl = open(os.path.join(dep_path_build, self.name + '.pkl'), 'rb')
        dep_export_ctx = pickle.load(filepkl)
        depdeps = None
        if isinstance(dep_export_ctx, Configuration):
            depconfig = dep_export_ctx
        else:
            depdeps = dep_export_ctx[0]
            depconfig = dep_export_ctx[1]
        filepkl.close()
        depconfig.includes = []

        config_target = config.target
        config.merge(context.context, [depconfig])
        config.target = config_target

        config.use.append(self.name)
        if depdeps is not None:
            context.project.deps = dict((obj.name, obj) for obj in (
                context.project.deps + depdeps)).values()

        if should_copy:
            distutils.dir_util.copy_tree(
                dep_path_build, context.make_out_path())
