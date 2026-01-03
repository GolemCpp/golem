import os
import io
import re
import sys
import hashlib
import glob
import json
import fnmatch
import shutil
import platform
import subprocess
import configparser
import stat
import string
from datetime import datetime
from copy import deepcopy
from golemcpp.golem.module import Module
from golemcpp.golem.cache import CacheConf, CacheDir
from golemcpp.golem.configuration import Configuration
from golemcpp.golem import cache
from golemcpp.golem import helpers
from golemcpp.golem.project import Project
from golemcpp.golem.build_target import BuildTarget
from golemcpp.golem.dependency import Dependency
from golemcpp.golem.template import Template
import copy
from golemcpp.golem.target import TargetConfigurationFile
from golemcpp.golem.version import Version
from functools import partial
from pathlib import Path
from waflib import Logs, Task
from collections import OrderedDict
from golemcpp.golem.target import Target
from golemcpp.golem.artifact import Artifact
from golemcpp.golem.package_msi import package_msi
from golemcpp.golem.package_dmg import package_dmg


class Context:
    def __init__(self, context):
        self.context = context
        self.project = None

        self.load_project()

        self.resolved_dependencies_path = None
        self.compiler_commands = []
        self.deps_to_resolve = []

        self.version = Version(working_dir=self.get_project_dir(),
                               build_number=self.get_build_number())

        self.deps_resolve = False
        self.deps_build = False
        self.built_tasks = []
        self.build_on = False

        self.resolved_master_dependencies = ''

        self.cache_conf = None
        self.repository = None

        self.context_tasks = []

    def get_build_number(self, default=None):
        if not self.project or not self.project.enable_build_number:
            if default is not None:
                return default
            return None
        build_number_key = 'BUILD_NUMBER'
        if build_number_key in os.environ:
            return int(os.environ[build_number_key])
        return 0

    def load_project(self, directory=None):
        if directory is None:
            directory = self.get_project_dir()

        def get_project_file_path(filname):
            return os.path.join(directory, filname)

        self.project_path = get_project_file_path("golem.json")
        if os.path.exists(self.project_path):
            json_object = None
            with io.open(self.project_path, 'r') as file:
                json_object = json.load(file)
            self.project = Project.unserialize_from_json(json_object)
            self.module = None

        if self.project is not None:
            return

        self.project_path = get_project_file_path("golemfile.py")
        if not os.path.exists(self.project_path):
            self.project_path = get_project_file_path("golem.py")
        if not os.path.exists(self.project_path):
            self.project_path = get_project_file_path("project.glm")
        if os.path.exists(self.project_path):
            self.module = Module(directory)
            self.project = self.module.project()

    def get_dependencies_json_path(self):

        deps_cache_file_json = self.make_project_path('dependencies.json')

        if self.context.options.resolved_dependencies_directory:
            deps_cache_file_json = os.path.join(
                self.context.options.resolved_dependencies_directory,
                'dependencies.json')

        return deps_cache_file_json

    @staticmethod
    def make_dependency_unique_identifier(dependency):
        return '{}_{}_{}_{}_{}'.format(dependency.repository,
                                       dependency.resolved_hash,
                                       dependency.link, dependency.runtime,
                                       dependency.runtime)

    def load_resolved_dependencies(self):
        master_dependencies = self.load_master_dependencies_configuration()
        if master_dependencies:
            for dependency in self.project.deps:
                for master_dependency in master_dependencies:
                    if dependency.repository == master_dependency.repository:
                        if master_dependency.version:
                            dependency.version = master_dependency.version
                        if master_dependency.resolved_version:
                            dependency.resolved_version = master_dependency.resolved_version
                        if master_dependency.resolved_hash:
                            dependency.resolved_hash = master_dependency.resolved_hash
                        if master_dependency.shallow:
                            dependency.shallow = master_dependency.shallow
                        if master_dependency.link:
                            dependency.link = master_dependency.link
                        if master_dependency.variant:
                            dependency.variant = master_dependency.variant
                        if master_dependency.runtime:
                            dependency.runtime = master_dependency.runtime
                        break

        if self.resolved_dependencies_path is not None:
            return

        deps_cache_file_json = self.get_dependencies_json_path()

        if os.path.exists(deps_cache_file_json):
            print('Found ' + str(deps_cache_file_json))
            self.load_dependencies_json(deps_cache_file_json)
            self.resolved_dependencies_path = deps_cache_file_json
        else:
            print("No dependencies cache found")

    def load_dependencies_json_cache(self):
        deps_cache_file_json = self.get_dependencies_json_path()
        if not os.path.exists(deps_cache_file_json):
            return None
        cache = None
        with open(deps_cache_file_json, 'r') as fp:
            cache = json.load(fp)
        cached_dependencies = Dependency.load_cache(cache=cache)
        return cached_dependencies

    def load_cached_dependencies_to_keep(self):
        if not self.get_only_update_dependencies_regex():
            return []

        cached_dependencies = self.load_dependencies_json_cache()

        if not cached_dependencies:
            return []

        pattern = re.compile(self.get_only_update_dependencies_regex())

        dependencies_to_keep = []
        for dependency in cached_dependencies:
            if not pattern.match(dependency.repository):
                dependencies_to_keep.append(dependency)

        return dependencies_to_keep

    def resolve_dependencies(self):
        deps_cache_file_json = self.make_project_path('dependencies.json')
        global_dependencies_configuration = self.get_global_dependencies_configuration_file(
        )

        deps_cache_file_json_build = None
        if self.context.options.resolved_dependencies_directory:
            deps_cache_file_json_build = os.path.join(
                self.context.options.resolved_dependencies_directory,
                'dependencies.json')

        cached_dependencies_to_keep = self.load_cached_dependencies_to_keep()

        if not self.context.options.keep_resolved_dependencies:
            if os.path.exists(deps_cache_file_json):
                print("Cleaning up " + str(deps_cache_file_json))
                os.remove(deps_cache_file_json)

            if deps_cache_file_json_build is not None and os.path.exists(
                    deps_cache_file_json_build):
                print("Cleaning up " + str(deps_cache_file_json_build))
                os.remove(deps_cache_file_json_build)

            if os.path.exists(
                    global_dependencies_configuration
            ) and not self.context.options.global_dependencies_configuration:
                print(
                    "Cleaning up {}".format(global_dependencies_configuration))
                os.remove(global_dependencies_configuration)

        self.resolved_dependencies_path = None

        self.load_resolved_dependencies()

        if self.resolved_dependencies_path is None:
            save_path = deps_cache_file_json
            if self.context.options.resolved_dependencies_directory:
                helpers.make_directory(
                    self.context.options.resolved_dependencies_directory)
                save_path = os.path.join(
                    self.context.options.resolved_dependencies_directory,
                    'dependencies.json')

            Logs.info("Resolving versions of required dependencies")
            self.project.resolve(
                global_config_file=global_dependencies_configuration,
                dependencies_to_keep=cached_dependencies_to_keep)

            Logs.info("Saving dependencies in cache " + str(save_path))
            self.save_dependencies_json(save_path)

            self.resolved_dependencies_path = save_path

    def get_global_dependencies_configuration_file(self):
        global_dependencies_configuration = self.make_build_path(
            'all_dependencies.json')
        if self.context.options.global_dependencies_configuration:
            global_dependencies_configuration = self.context.options.global_dependencies_configuration
        return global_dependencies_configuration

    def load_dependencies_json(self, path):
        cache = None
        with open(path, 'r') as fp:
            cache = json.load(fp)
        self.project.deps_load_json(cache)

    def save_dependencies_json(self, path):
        cache = self.project.deps_resolve_json()
        with open(path, 'w') as fp:
            json.dump(cache, fp, indent=4)

    def get_project_dir(self):
        return self.context.options.dir

    def get_golemcpp_dir(self):
        return Path(os.path.abspath(os.path.dirname(os.path.realpath(__file__)))).parent

    def get_golemcpp_data_dir(self):
        return os.path.join(self.get_golemcpp_dir(), 'data')

    def make_cache_dirs(self):
        cache_dir_list = []

        cache_dir = self.make_writable_cache_dir()
        if cache_dir:
            cache_dir_list.append(CacheDir(cache_dir, False))

        defined_cached_directories = self.make_define_cache_directories_list()
        cache_dir_list += defined_cached_directories

        static_cache_dir = self.make_static_cache_dir()
        if static_cache_dir:
            cache_dir_list.append(CacheDir(static_cache_dir, True))

        return cache_dir_list

    def make_writable_cache_dir(self):
        cache_dir = self.make_local_path_absolute(
            path=self.context.options.cache_dir)
        if cache_dir:
            return cache_dir

        cache_dir = cache.default_cached_dir().location

        return cache_dir

    def get_static_cache_dir_option(self):
        static_cache_dir = self.context.options.static_cache_dir
        if not static_cache_dir and 'GOLEM_STATIC_CACHE_DIRECTORY' in os.environ and os.environ[
                'GOLEM_STATIC_CACHE_DIRECTORY']:
            static_cache_dir = os.environ['GOLEM_STATIC_CACHE_DIRECTORY']
        return static_cache_dir

    def get_master_dependencies_configuration(self):
        master_dependencies_configuration = self.context.options.master_dependencies_configuration
        if not master_dependencies_configuration and self.project.master_dependencies_configuration:
            master_dependencies_configuration = self.project.master_dependencies_configuration
        if not master_dependencies_configuration and 'GOLEM_MASTER_DEPENDENCIES_CONFIGURATION' in os.environ and os.environ[
                'GOLEM_MASTER_DEPENDENCIES_CONFIGURATION']:
            master_dependencies_configuration = os.environ[
                'GOLEM_MASTER_DEPENDENCIES_CONFIGURATION']
        return master_dependencies_configuration

    def make_master_dependencies_configuration(self):
        return self.make_local_path_absolute(
            path=self.get_master_dependencies_configuration())

    def get_master_dependencies_repository(self):
        master_dependencies_repository = self.project.master_dependencies_repository
        if not self.project.master_dependencies_repository and 'GOLEM_MASTER_DEPENDENCIES_REPOSITORY' in os.environ and os.environ[
                'GOLEM_MASTER_DEPENDENCIES_REPOSITORY']:
            master_dependencies_repository = os.environ[
                'GOLEM_MASTER_DEPENDENCIES_REPOSITORY']
        return master_dependencies_repository

    def load_master_dependencies_configuration(self):

        if not self.resolved_master_dependencies:
            master_dependencies_configuration = self.make_master_dependencies_configuration(
            )
            master_dependencies_repository = self.get_master_dependencies_repository(
            )
            if not master_dependencies_configuration and master_dependencies_repository:
                repo_path = self.clone_master_dependencies_repository(
                    master_dependencies_repository)
                master_dependencies_json = os.path.join(
                    repo_path, 'master_dependencies.json')
                if os.path.exists(master_dependencies_json):
                    master_dependencies_configuration = master_dependencies_json

            if master_dependencies_configuration:
                self.resolved_master_dependencies = master_dependencies_configuration

        if not self.resolved_master_dependencies or not os.path.exists(
                self.resolved_master_dependencies):
            return None

        if not os.path.exists(self.resolved_master_dependencies):
            raise RuntimeError(
                "Can't find master dependencies configuration: {}".format(
                    self.resolved_master_dependencies))

        cache = None
        with open(self.resolved_master_dependencies, 'r') as fp:
            cache = json.load(fp)

        master_dependencies = []
        for entry in cache:
            cached_dependency = Dependency.unserialize_from_json(entry)
            master_dependencies.append(cached_dependency)

        return master_dependencies

    def get_static_cache_dependencies_regex(self):
        static_cache_dependencies_regex = self.context.options.static_cache_dependencies_regex
        if not static_cache_dependencies_regex and 'GOLEM_STATIC_CACHE_DEPENDENCIES_REGEX' in os.environ and os.environ[
                'GOLEM_STATIC_CACHE_DEPENDENCIES_REGEX']:
            static_cache_dependencies_regex = os.environ[
                'GOLEM_STATIC_CACHE_DEPENDENCIES_REGEX']
        return static_cache_dependencies_regex

    def get_only_update_dependencies_regex(self):
        return self.context.options.only_update_dependencies_regex

    def parse_cache_directories_string(self, string):

        dirs = []
        cache_directories_pairs = string.split('|')
        for cache_string in cache_directories_pairs:
            cache_definition = cache_string.split('=')
            if len(cache_definition) != 2:
                raise RuntimeError(
                    "Bad cache definition: {}".format(cache_string))

            cache_path = cache_definition[0]
            cache_regex = cache_definition[1]

            _ = re.compile(cache_regex)

            cache_path = self.make_local_path_absolute(path=cache_path)

            cache = CacheDir(location=cache_path,
                             is_static=False,
                             regex=cache_regex)
            dirs.append(cache)

        return dirs

    def get_define_cache_directories_string(self):
        cache_directories_string = self.context.options.define_cache_directories
        if not cache_directories_string and 'GOLEM_DEFINE_CACHE_DIRECTORIES' in os.environ and os.environ[
                'GOLEM_DEFINE_CACHE_DIRECTORIES']:
            cache_directories_string = os.environ[
                'GOLEM_DEFINE_CACHE_DIRECTORIES']
        return cache_directories_string

    def make_define_cache_directories_list(self):
        cache_directories_string = self.get_define_cache_directories_string()
        if not cache_directories_string:
            return []

        return self.parse_cache_directories_string(
            string=cache_directories_string)

    def get_define_cache_directories(self):
        cache_directories_string = self.get_define_cache_directories_string()

        if not cache_directories_string:
            return ''

        dirs = self.parse_cache_directories_string(
            string=cache_directories_string)

        new_string = []
        for cache_dir in dirs:
            string = '{}={}'.format(cache_dir.location,
                                    cache_dir.regex if cache_dir.regex else '')
            new_string.append(string)

        cache_directories_string = '|'.join(new_string)

        return cache_directories_string

    def get_options_static_cache_dir(self):
        return self.make_local_path_absolute(
            path=self.context.options.static_cache_dir)

    def get_options_master_dependencies_configuration(self):
        return self.make_local_path_absolute(
            path=self.context.options.master_dependencies_configuration)

    def make_static_cache_dir(self):
        return self.make_local_path_absolute(
            path=self.get_static_cache_dir_option())

    def make_local_path_absolute(self, path):
        abolute_path = path
        if not abolute_path:
            return ''
        if not os.path.isabs(abolute_path):
            abolute_path = os.path.join(self.get_project_dir(), abolute_path)
        return abolute_path

    def make_project_path(self, path):
        return os.path.join(self.get_project_dir(), str(Path(path)))

    @staticmethod
    def hash_identifier(flags):
        return hashlib.md5(''.join(flags)).hexdigest()[:8]

    def make_base_path(self, path, prefix_path = ''):
        base_path = self.context.root
        if len(prefix_path) == 0:
            if os.path.isabs(path):
                base_path = self.context.root
            else:
                base_path = self.context.srcnode
        else:
            if os.path.isabs(prefix_path):
                base_path = self.context.root.find_dir(prefix_path)
            else:
                base_path = self.context.srcnode.find_dir(prefix_path) 
        return base_path

    def list_include(self, includes, prefix_path = ''):
        file_nodes = []
        for x in includes:
            base_path = self.make_base_path(x, prefix_path)
            file_node = base_path.find_dir(str(x))
            file_nodes.append(file_node)
        return file_nodes

    def list_files(self, prefix_path, source, extentions):
        result = []
        for x in source:
            if isinstance(x, tuple):
                base_path = self.make_base_path('', prefix_path)
                args = { }
                if len(x) > 0:
                    args['incl'] = x[0]
                if len(x) > 1:
                    args['excl'] = x[1]
                if len(x) > 2:
                    args['dir'] = x[2]
                if len(x) > 3:
                    args['src'] = x[3]
                if len(x) > 4:
                    args['maxdepth'] = x[4]
                if len(x) > 5:
                    args['ignorecase'] = x[5]
                if len(x) > 6:
                    args['generator'] = x[6]
                if len(x) > 7:
                    args['remove'] = x[7]
                if len(x) > 8:
                    args['quiet'] = x[8]
                result += base_path.ant_glob(**args)
            elif isinstance(x, dict):
                base_path = self.make_base_path('', prefix_path)
                result += base_path.ant_glob(**x)
            else:
                base_path = self.make_base_path(x, prefix_path)
                x_path = base_path.find_node(str(x))
                if os.path.isfile(str(x_path)):
                    result += [x_path]
                elif os.path.isdir(str(x_path)):
                    file_nodes = []
                    for extention in extentions:
                        file_nodes += x_path.ant_glob('**/*.' + extention)
                    result += file_nodes
                else:
                    result += x_path.ant_glob(str(x))

        return result

    def list_source(self, source):
        return self.list_files(self.get_project_dir(), source, ['cpp', 'c', 'cxx', 'cc'] +
                               (['mm'] if self.is_darwin() else []))

    def list_moc(self, source):
        return self.list_files(self.get_project_dir(), source, ['hpp', 'h', 'hxx', 'hh'])

    def list_qt_qrc(self, source):
        return self.list_files(self.get_project_dir(), source, ['qrc'])

    def list_qt_ui(self, source):
        return self.list_files(self.get_project_dir(), source, ['ui'])

    def list_template(self, source):
        return self.list_files(self.get_project_dir(), source, ['template'])

    @staticmethod
    def get_parent_directories(files):
        directories = [str(Path(str(file)).parent.absolute()) for file in files]
        return helpers.filter_unique(directories)
    
    @staticmethod
    def link_static():
        return 'static'

    @staticmethod
    def link_shared():
        return 'shared'

    def link(self, dep=None):
        return self.context.options.link if dep is None or not dep.link else dep.link[
            0]

    def distribution(self):
        if self.is_linux():
            if (hasattr(platform, 'linux_distribution')):
                return platform.linux_distribution()[0].lower()
            elif (hasattr(platform, 'freedesktop_os_release')):
                return platform.freedesktop_os_release()['ID'].lower()
            else:
                raise RuntimeError("Not implemented yet")
        return None

    def release(self):
        if self.is_linux():
            if (hasattr(platform, 'linux_distribution')):
                import lsb_release
                return lsb_release.get_distro_information()['CODENAME'].lower()
            elif (hasattr(platform, 'freedesktop_os_release')):
                return platform.freedesktop_os_release()['VERSION_ID'].lower()
            else:
                raise RuntimeError("Not implemented yet")
        return None

    def link_min(self, dep=None):
        return self.link(dep)[:2]

    def is_static(self):
        return self.context.options.link == self.link_static()

    def is_shared(self):
        return self.context.options.link == self.link_shared()

    def runtime(self, dep=None):
        return self.context.options.runtime if dep is None or not dep.runtime else dep.runtime[
            0]

    def is_runtime_static(self):
        return self.runtime() == self.link_static()

    def is_runtime_shared(self):
        return self.runtime() == self.link_shared()

    def runtime_min(self, dep=None):
        return self.runtime(dep)[:2]

    def arch(self):
        return self.context.options.arch

    def arch_min(self):
        return self.arch()

    @staticmethod
    def variant_debug():
        return 'debug'

    @staticmethod
    def variant_release():
        return 'release'

    def variant(self):
        return self.context.options.variant

    def variant_suffix(self):
        variant = ''
        if self.context.options.variant == self.variant_debug():
            variant = '-' + self.variant_debug()
        return variant

    def artifact_suffix_mode(self, config, is_shared):
        is_library = not config.type or config.type_unique == 'library'

        if is_library:
            if config.link:
                if config.link_unique == 'shared':
                    is_shared = True
                elif config.link_unique == 'static':
                    is_shared = False

            if is_shared:
                if self.is_windows():
                    return ['.dll', '.lib']
                elif self.is_darwin():
                    return ['.dylib']
                else:
                    return ['.so']
            else:
                if self.is_windows():
                    return ['.lib']
                else:
                    return ['.a']
        elif config.type_unique == 'program':
            if self.is_windows():
                return ['.exe']
            else:
                return ['']
        elif config.type_unique == 'objects':
            return ['.o']
        else:
            return []

    def artifact_suffix(self, config):
        is_shared = self.is_shared(
        ) if not config.link else config.link_unique == 'shared'
        return self.artifact_suffix_mode(config, is_shared)

    def is_config_shared(self, config):
        return self.is_shared(
        ) if not config.link else config.link_unique == 'shared'

    def artifact_prefix(self, config):
        is_program = config.type_unique == 'program'
        return '' if (self.is_windows() or is_program) else 'lib'

    def dev_artifact_suffix(self, is_shared=None):
        if is_shared is None:
            is_shared = self.is_shared()

        if is_shared:
            if self.is_windows():
                return '.lib'
            elif self.is_darwin():
                return '.dylib'
            else:
                return '.so'
        else:
            if self.is_windows():
                return '.lib'
            else:
                return '.a'

    def artifact_suffix_dev(self, target):
        is_shared = self.is_shared(
        ) if not target.link else target.link_unique == 'shared'
        return self.dev_artifact_suffix(is_shared)

    def is_debug(self):
        return self.context.options.variant == self.variant_debug()

    def is_release(self):
        return self.context.options.variant == self.variant_release()

    def variant_min(self, dep=None):
        if dep and dep.variant:
            v = dep.variant[0].lower()
            if v in ['release', 'debug']:
                return v[:1]
            else:
                return v
        return self.context.options.variant[:1]

    @staticmethod
    def os_windows():
        return 'windows'

    @staticmethod
    def os_linux():
        return 'linux'

    @staticmethod
    def os_osx():
        return 'osx'

    @staticmethod
    def os_android():
        return 'android'

    @staticmethod
    def is_windows():
        return sys.platform.startswith('win32')

    @staticmethod
    def is_linux():
        return sys.platform.startswith('linux')

    @staticmethod
    def is_flatpak():
        return Context.is_linux() and hasattr(platform, 'freedesktop_os_release') and (shutil.which('flatpak-spawn') is not None)

    @staticmethod
    def is_darwin():
        return sys.platform.startswith('darwin')

    def is_android(self):
        return self.has_android_ndk_path()

    def osname(self):
        osname = ''
        if self.is_android():
            osname = Context.os_android()
        elif Context.is_windows():
            osname = Context.os_windows()
        elif Context.is_linux():
            osname = Context.os_linux()
        elif Context.is_darwin():
            osname = Context.os_osx()
        return osname

    def osname_min(self):
        return self.osname()[:3]

    def compiler(self):
        return self.context.env.CXX_NAME + '-' + '.'.join(
            self.context.env.CC_VERSION)

    def compiler_name(self):
        return self.context.env.CXX_NAME

    def compiler_version(self):
        return '.'.join(self.context.env.CC_VERSION)

    def compiler_min(self):
        return self.context.env.CXX_NAME[:1] + ''.join(
            self.context.env.CC_VERSION)
    
    def is_msvc_like(self):
        return self.compiler_name() == 'msvc' or self.compiler_name() == 'clang-cl'

    @staticmethod
    def machine():
        if os.name == 'nt' and sys.version_info[:2] < (2, 7):
            return os.environ.get("PROCESSOR_ARCHITEW6432",
                                  os.environ.get('PROCESSOR_ARCHITECTURE', ''))
        else:
            return platform.machine()

    @staticmethod
    def osarch_parser(arch):
        machine2bits = {
            'amd64': 'x64',
            'x86_64': 'x64',
            'x64': 'x64',
            'x86_amd64': 'x64',
            'i386': 'x86',
            'i686': 'x86',
            'x86': 'x86',
            'amd64_x86': 'x86'
        }
        return machine2bits.get(arch.lower(), None)

    @staticmethod
    def osarch():
        return Context.osarch_parser(Context.machine())

    def get_arch(self):
        return Context.osarch_parser(self.context.options.arch)

    def is_x86(self):
        return self.get_arch() == 'x86'

    def is_x64(self):
        return self.get_arch() == 'x64'

    def get_arch_for_linux(self, arch=None):
        machine2bits = {'x64': 'amd64', 'x86': 'i386'}
        return machine2bits.get(
            self.get_arch() if arch is None else arch.lower(), None)

    def get_build_runtime(self):
        if self.context.env.MSVC_VERSION:
            return 'msvc'
        elif self.is_darwin():
            if self.context.env.MACOSX_DEPLOYMENT_TARGET:
                return 'macosx'
            elif self.context.env.IPHONEOS_DEPLOYMENT_TARGET:
                return 'iphoneos'
            else:
                return 'macosx'
        elif self.is_android():
            return 'android'
        else:
            return str(platform.libc_ver()[0])

    def get_build_runtime_version(self):
        if self.context.env.MSVC_VERSION:
            return str(self.context.env.MSVC_VERSION)
        elif self.is_darwin():
            if self.context.env.MACOSX_DEPLOYMENT_TARGET:
                return str(self.context.env.MACOSX_DEPLOYMENT_TARGET)
            elif self.context.env.IPHONEOS_DEPLOYMENT_TARGET:
                return str(self.context.env.IPHONEOS_DEPLOYMENT_TARGET)
            else:
                return str(platform.mac_ver()[0])
        elif self.is_android():
            # minSdkVersion (__ANDROID_API__)
            raise RuntimeError("Not implemented yet")
        else:
            return str(platform.libc_ver()[1])

    def get_build_runtime_version_semver(self):
        version = self.get_build_runtime_version()
        return Version.parse_semver(version)[0]

    @staticmethod
    def options(context):
        context.load('compiler_c compiler_cxx qt5')
        context.add_option("--dir",
                           action="store",
                           default='.',
                           help="Project location")
        context.add_option("--variant",
                           action="store",
                           default='debug',
                           help="Variant (debug, release)")
        context.add_option("--runtime",
                           action="store",
                           default='shared',
                           help="Runtime Linking")
        context.add_option("--link",
                           action="store",
                           default='shared',
                           help="Library Linking")
        context.add_option("--arch",
                           action="store",
                           default=Context.osarch(),
                           help="Target Architecture")

        context.add_option("--major",
                           action="store_true",
                           default=False,
                           help="Release major version")
        context.add_option("--minor",
                           action="store_true",
                           default=False,
                           help="Release minor version")
        context.add_option("--patch",
                           action="store_true",
                           default=False,
                           help="Release patch version")

        context.add_option("--export",
                           action="store",
                           default='',
                           help="Export folder")
        context.add_option("--packages",
                           action="store",
                           default='',
                           help="Packages to process")

        context.add_option("--vscode",
                           action="store_true",
                           default=False,
                           help="VSCode CppTools Properties")

        context.add_option("--clangd",
                           action="store_true",
                           default=False,
                           help="clangd configuration file")

        context.add_option("--compile-commands",
                           action="store_true",
                           default=False,
                           help="Generate the compile_commands.json files")

        context.add_option("--cache-dir",
                           action="store",
                           default='',
                           help="Cache directory location")
        context.add_option("--static-cache-dir",
                           action="store",
                           default='',
                           help="Read-only cache directory location")

        if Context.is_windows():
            context.add_option("--nounicode",
                               action="store_true",
                               default=False,
                               help="Unicode Support")
        else:
            context.add_option("--nounicode",
                               action="store_true",
                               default=True,
                               help="Unicode Support")

        context.add_option("--android-ndk",
                           action="store",
                           default='',
                           help="Android NDK path")
        context.add_option("--android-sdk",
                           action="store",
                           default='',
                           help="Android SDK path")
        context.add_option("--android-ndk-platform",
                           action="store",
                           default='',
                           help="Android NDK platform version")
        context.add_option("--android-sdk-platform",
                           action="store",
                           default='',
                           help="Android SDK platform version")
        context.add_option("--android-jdk",
                           action="store",
                           default='',
                           help="JDK path to use when packaging Android app")
        context.add_option("--android-arch",
                           action="store",
                           default='',
                           help="Android target architecture")

        context.add_option("--keep-resolved-dependencies",
                           action="store_true",
                           default=False,
                           help="Keep resolved dependencies when set")

        context.add_option("--resolved-dependencies-directory",
                           action="store",
                           default='',
                           help="Resolved dependencies directory path")

        context.add_option(
            "--global-dependencies-configuration",
            action="store",
            default='',
            help="Configuration file of all required dependencies for the build"
        )

        context.add_option(
            "--master-dependencies-configuration",
            action="store",
            default='',
            help=
            "Master configuration file to resolve dependencies for the build")

        context.add_option("--recipe",
                           action="store",
                           default='',
                           help="Identifier to lookup a recide")

        context.add_option("--no-recipes-repositories-fetch",
                           action="store_true",
                           default=False,
                           help="Disable recipes repositories git clone/fetch")

        context.add_option("--force-version",
                           action="store",
                           default='',
                           help="Force version")

        context.add_option(
            "--no-copy-artifacts",
            action="store_true",
            default=False,
            help="Disable copy of dependencies' artifacts into binary folder")

        context.add_option(
            "--no-copy-licenses",
            action="store_true",
            default=False,
            help="Disable copy of dependencies' licenses into licenses folder")

        context.add_option(
            "--static-cache-dependencies-regex",
            action="store",
            default='',
            help=
            "Store all dependencies with an URL matching the regex in the static cache (if defined)"
        )

        context.add_option(
            "--only-update-dependencies-regex",
            action="store",
            default='',
            help=
            "Select only dependencies with an URL matching the regex to resolve new versions"
        )

        context.add_option(
            "--define-cache-directories",
            action="store",
            default='',
            help=
            "Define cache directories by specifying a string such as <path>=<regex>|<path>=(...) where regex is selecting dependencies with a matching repository URL"
        )

        context.add_option(
            "--output-file",
            action="store",
            default='',
            help="Output file for static analysis results (e.g. cppcheck)")

    def configure_init(self):
        if not self.context.env.DEFINES:
            self.context.env.DEFINES = []
        if not self.context.env.CXXFLAGS:
            self.context.env.CXXFLAGS = []
        if not self.context.env.CFLAGS:
            self.context.env.CFLAGS = []
        if not self.context.env.LINKFLAGS:
            self.context.env.LINKFLAGS = []
        if not self.context.env.ARFLAGS:
            self.context.env.ARFLAGS = []

    def find_cache_conf(self):
        settings_path = self.make_project_path('settings.glm')
        if not os.path.exists(settings_path):
            return None
        raise Exception("Not implemented")

        config = configparser.RawConfigParser()
        config.read(settings_path)

        if not config.has_section('GOLEM'):
            return None

        cacheconf = CacheConf()
        cacheconf.locations = self.make_cache_dirs()

        # cache remote
        if not config.has_option('GOLEM', 'cache.remote'):
            return None

        remote = config.get('GOLEM', 'cache.remote')

        if not remote:
            return None

        cacheconf.remote = remote.strip('\'"')

        # cache location
        # if config.has_option('GOLEM', 'cache.location'):
        #	location = config.get('GOLEM', 'cache.location')

        #if cacheconf.location:
        #    cacheconf.locations = [CacheDir(cacheconf.location.strip('\'"'))]

        # return cache configuration
        return cacheconf

    def configure_default(self):
        if not self.context.options.nounicode:
            self.context.env.DEFINES.append('UNICODE')

        if self.is_msvc_like():
            if self.is_x86():
                self.context.env.LINKFLAGS.append('/MACHINE:X86')
                self.context.env.ARFLAGS.append('/MACHINE:X86')
            elif self.is_x64():
                self.context.env.LINKFLAGS.append('/MACHINE:X64')
                self.context.env.ARFLAGS.append('/MACHINE:X64')

            if self.is_x86():
                self.context.env.MSVC_TARGETS = ['x86']
            elif self.is_x64():
                self.context.env.MSVC_TARGETS = ['amd64']

            self.context.env.MSVC_MANIFEST = False  # disable waf manifest behavior

            default_flags = ['/DWIN32', '/D_WINDOWS', '/GR', '/EHsc']
            
            self.context.env.CFLAGS += default_flags
            self.context.env.CXXFLAGS += default_flags

            # Set /external ON
            # TODO: Need to find a way to discover if the compiler supports /external to use /I if it can't

            default_flags = ['/experimental:external', '/external:W0']
            
            self.context.env.CFLAGS += default_flags
            self.context.env.CXXFLAGS += default_flags

            # Serialized writes to the program database (PDB) to avoid fatal error C1041

            default_flags = ['/FS']
            
            self.context.env.CFLAGS += default_flags
            self.context.env.CXXFLAGS += default_flags

            # Compiler Options https://msdn.microsoft.com/en-us/library/fwkeyyhe.aspx
            # Linker Options https://msdn.microsoft.com/en-us/library/y0zzbyt4.aspx

            # MSVC_VERSIONS = ['msvc 14.0']

            # Some compilation flags (self.context.env.CXXFLAGS)

            # '/MP'             # compiles multiple source files by using multiple processes
            # '/Gm-'            # disable minimal rebuild
            # '/Zc:inline'      # compiler does not emit symbol information for unreferenced COMDAT functions or data
            # '/Zc:forScope'    # implement standard C++ behavior for for loops
            # '/Zc:wchar_t'     # wchar_t as a built-in type
            # '/fp:precise'     # improves the consistency of floating-point tests for equality and inequality
            # '/W4'             # warning level 4
            # '/sdl'            # enables a superset of the baseline security checks provided by /GS
            # '/GS'             # detects some buffer overruns that overwrite things
            # '/EHsc'           # enable exception
            # '/nologo'         # suppress startup banner
            # '/Gd'             # specifies default calling convention
            # '/analyze-'       # disable code analysis
            # '/WX-'            # warnings are not treated as errors
            # '/FS'             # serialized writes to the program database (PDB)
            # '/Fd:testing.pdb' # file name for the program database (PDB) defaults to VCx0.pdb
            # '/std:c++latest'  # enable all features as they become available, including feature removals
            # '/bigobj'
            # '/experimental:external'  # enable use of /external:I
            # '/utf-8'                  # enable {source/executable/validate}-charset to utf-8

            # Some link flags (self.context.env.LINKFLAGS)

            # '/errorReport:none'   # do not send CL crash reports
            # '/NXCOMPAT'           # tested to be compatible with the Windows Data Execution Prevention feature
            # '/DYNAMICBASE'        # generate an executable image that can be randomly rebased at load time

            # '/OUT:"D:.dll"'   # specifies the output file name
            # '/PDB:"D:.pdb"'   # creates a program database (PDB) file
            # '/IMPLIB:"D:.lib"'
            # '/PGD:"D:.pgd"'   # specifies a .pgd file for profile-guided optimizations

            # '/MANIFEST'   # creates a side-by-side manifest file and optionally embeds it in the binary
            # '/MANIFESTUAC:"level=\'asInvoker\' uiAccess=\'false\'"'
            # '/ManifestFile:".dll.intermediate.manifest"'
            # '/SUBSYSTEM'  # how to run the .exe file
            # '/DLL'        # builds a DLL
            # '/TLBID:1'    # resource ID of the linker-generated type library
        else:
            if not self.is_android():
                if self.is_x86():
                    self.context.env.CXXFLAGS.append('-m32')
                    self.context.env.CFLAGS.append('-m32')
                elif self.is_x64():
                    self.context.env.CXXFLAGS.append('-m64')
                    self.context.env.CFLAGS.append('-m64')

        if self.is_darwin():
            self.context.env.CXX = ['clang++']

    def configure_debug(self):

        if self.is_msvc_like():
            if self.is_runtime_static():
                self.context.env.CXXFLAGS.append('/MTd')
                self.context.env.CFLAGS.append('/MTd')
            elif self.is_runtime_shared():
                self.context.env.CXXFLAGS.append('/MDd')
                self.context.env.CFLAGS.append('/MDd')

            default_flags = ['/Zi', '/Ob0', '/Od', '/RTC1']
            
            self.context.env.CFLAGS += default_flags
            self.context.env.CXXFLAGS += default_flags

            default_flags = ['/debug', '/INCREMENTAL']

            self.context.env.LINKFLAGS += default_flags
            self.context.env.ARFLAGS += default_flags

            # Some compilation flags (self.context.env.CXXFLAGS)

            # '/RTC1'   # run-time error checks (stack frame & uninitialized used variables)
            # '/ZI'     # produces a program database in a format that supports the Edit and Continue feature.
            # '/Z7'     # embeds the program database
            # '/Od'     # disable optimizations
            # '/Oy-'    # speeds function calls (should be specified after others /O args)

            # Some link flags (self.context.env.LINKFLAGS)

            # '/MAP'                # creates a mapfile
            # '/MAPINFO:EXPORTS'    # includes exports information in the mapfile
            # '/DEBUG'              # creates debugging information
            # '/INCREMENTAL'        # incremental linking
        else:
            default_flags = ['-O0', '-g']

            self.context.env.LINKFLAGS += default_flags
            self.context.env.ARFLAGS += default_flags


    def configure_release(self):

        self.context.env.DEFINES.append('NDEBUG')

        if self.is_msvc_like():
            if self.is_runtime_static():
                self.context.env.CXXFLAGS.append('/MT')
                self.context.env.CFLAGS.append('/MT')
            elif self.is_runtime_shared():
                self.context.env.CXXFLAGS.append('/MD')
                self.context.env.CFLAGS.append('/MD')

            default_flags = ['/O2', '/Ob2']
            
            self.context.env.CFLAGS += default_flags
            self.context.env.CXXFLAGS += default_flags

            default_flags =['/INCREMENTAL:NO']

            self.context.env.LINKFLAGS += default_flags
            self.context.env.ARFLAGS += default_flags

            # TODO: Add --runtime-variant so that on Windows,
            # we can choose independantly the variant of the runtime
            # from the variant of the project and its dependencies

            # Some compilation flags (self.context.env.CXXFLAGS)

            # About COMDATs, linker requires that functions be packaged separately as COMDATs to EXCLUTE or ORDER individual functions in a DLL or .exe file.

            # '/Zi'     # produces a program database (PDB) does not affect optimizations
            # '/Gy'     # allows the compiler to package individual functions in the form of packaged functions (COMDATs)
            # '/GL'     # enables whole program optimization
            # '/O2'     # generate fast code
            # '/Oi'     # request to the compiler to replace some function calls with intrinsics
            # '/Oy-'    # speeds function calls (should be specified after others /O args)

            # Some link flags (self.context.env.LINKFLAGS)

            # '/DEF:"D:.def"'
            # '/LTCG'               # perform whole-program optimization
            # '/LTCG:incremental'   # perform incremental whole-program optimization
            # '/OPT:REF'            # eliminates functions and data that are never referenced
            # '/OPT:ICF'            # to perform identical COMDAT folding
            # '/SAFESEH'            # image will contain a table of safe exception handlers
        else:
            default_flags = ['-O2']

            self.context.env.LINKFLAGS += default_flags
            self.context.env.ARFLAGS += default_flags

    def environment(self, resolve_dependencies=False):

        # load all environment variables
        self.context.load_envs()

        _ = self.restore_options_env(self.context.all_envs['main'])
        self.context.env = self.context.all_envs['main'].derive()

        # Restore options
        self.restore_options()

        # init default environment variables
        self.configure_init()
        self.configure_default()

        # set environment variables according variant
        if self.is_debug():
            self.configure_debug()
        else:
            self.configure_release()

        # android specific flags
        self.append_android_cxxflags()
        self.append_android_linkflags()
        self.append_android_ldflags()

        self.cache_conf = self.make_cache_conf()
        self.load_recipe()

        if resolve_dependencies:
            self.resolve_dependencies()
        else:
            self.load_resolved_dependencies()

        if self.context.options.force_version:
            self.version.force_version(self.context.options.force_version)

        for dependency in self.project.deps:
            dependency.update_cache_dir(context=self)

    def dep_system(self, context, libs):
        context.env['LIB'] += libs

    def dep_static_release(self, name, fullname, lib):

        self.context.env['INCLUDES_' + name] = self.list_include(['includes'])
        self.context.env['STLIBPATH_' + name] = self.list_include(['libpath'])
        self.context.env['STLIB_' + name] = lib

    def dep_static(self, name, fullname, lib, libdebug):

        self.context.env['INCLUDES_' + name] = self.list_include(['includes'])
        self.context.env['STLIBPATH_' + name] = self.list_include(['libpath'])

        if self.is_debug():
            self.context.env['STLIB_' + name] = libdebug
        else:
            self.context.env['STLIB_' + name] = lib

    def dep_shared_release(self, name, fullname, lib):

        self.context.env['INCLUDES_' + name] = self.list_include(['includes'])
        self.context.env['LIBPATH_' + name] = self.list_include(['libpath'])
        self.context.env['LIB_' + name] = lib

    def dep_shared(self, name, fullname, lib, libdebug):

        self.context.env['INCLUDES_' + name] = self.list_include(['includes'])
        self.context.env['LIBPATH_' + name] = self.list_include(['libpath'])

        if self.is_debug():
            self.context.env['LIB_' + name] = libdebug
        else:
            self.context.env['LIB_' + name] = lib

    def make_cache_conf(self):
        cache_conf = self.find_cache_conf()
        if not cache_conf:
            cache_conf = CacheConf()
            cache_conf.locations = self.make_cache_dirs()

        if len(cache_conf.locations) == 0:
            cache_conf.locations.append(cache.default_cached_dir())

        return cache_conf

    def get_local_dep_pkl(self, dep):
        return os.path.join(self.make_out_path(), dep.name + '.pkl')

    def get_dependency_location(self, dependency):
        path = helpers.make_dep_base(dep=dependency)
        return os.path.join(dependency.cache_dir.location, path)

    def get_dep_location(self, dep, cache_dir):
        path = helpers.make_dep_base(dep)
        return os.path.join(cache_dir.location, path)

    def get_dep_repo_location(self, dep, cache_dir, base=None):
        path = self.get_dep_location(dep, cache_dir) if base is None else base
        return os.path.join(path, 'repository')

    def get_dep_include_location(self, dep, cache_dir, base=None):
        path = self.get_dep_location(dep, cache_dir) if base is None else base
        return os.path.join(path, 'include')

    def make_dependency_path(self, dependency, path):
        return os.path.join(
            self.get_dependency_location(dependency=dependency), path)

    def make_dependency_build_path(self, dependency, path):
        return self.make_dependency_path(dependency=dependency,
                                         path=os.path.join(
                                             self.build_path(dep=dependency),
                                             path))

    def get_dependency_dependencies_json_path(self, dependency):
        return self.make_dependency_build_path(dependency=dependency,
                                               path='dependencies.json')

    def load_dependency_dependencies_json(self, dependency):
        path = self.get_dependency_dependencies_json_path(
            dependency=dependency)
        cache = None
        with open(path, 'r') as fp:
            cache = json.load(fp)
        return Dependency.load_cache(cache)

    def save_dep_dependencies_json(self, dependency):
        path = self.get_dependency_dependencies_json_path(
            dependency=dependency)
        cache = self.project.deps_resolve_json()
        with open(path, 'w') as fp:
            json.dump(cache, fp, indent=4)

    def get_dep_artifact_location(self, dependency, cache_dir, base=None):
        cached_dependencies = self.load_dependency_dependencies_json(
            dependency=dependency)
        path = self.get_dep_location(
            dep=dependency, cache_dir=cache_dir) if base is None else base
        return os.path.join(
            path, self.build_path(dep=dependency),
            self.make_binary_foldername(dependencies=cached_dependencies))

    def get_dep_build_location(self, dep, cache_dir, base=None):
        path = self.get_dep_location(dep, cache_dir) if base is None else base
        return os.path.join(path, self.build_path(dep))

    def make_dep_artifact_filename(self,
                                   dep,
                                   target_name=None,
                                   repository=None):

        name = []

        if target_name:
            name.append(target_name)

        name.append(dep.name)

        if repository is None:
            repository = self.load_git_remote_origin_url()

        config_filename = "{}@{}.json".format(
            '@'.join(name), helpers.generate_recipe_id(repository))

        return config_filename

    def get_dep_artifact_json(self, dep, cache_dir, target_name=None):
        path = os.path.join(self.get_dep_build_location(dep, cache_dir),
                            'conf')
        return os.path.join(
            path,
            self.make_dep_artifact_filename(dep=dep,
                                            target_name=target_name,
                                            repository=dep.repository))

    def get_dep_artifact_json_list(self, dep, cache_dir):
        if dep.targets:
            return [
                self.get_dep_artifact_json(dep=dep,
                                           cache_dir=cache_dir,
                                           target_name=target_name)
                for target_name in dep.targets
            ]
        return [
            self.get_dep_artifact_json(dep=dep,
                                       cache_dir=cache_dir,
                                       target_name=None)
        ]

    def use_dep(self, config, dep, cache_dir):
        dep_configs = self.read_dep_config_file_list(dep=dep,
                                                     cache_dir=cache_dir)

        for dep_config in dep_configs:
            dependency_dependencies = dep_config.dependencies
            dependency_configuration = dep_config.configuration

            if config is not None:
                dependency_configuration.type = []
                dependency_configuration.isystem += dependency_configuration.includes
                dependency_configuration.includes = []
                dependency_configuration.licenses = []
                dependency_configuration.artifacts_dev = []
                dependency_configuration.artifacts_run = []

                config_targets = copy.deepcopy(config.targets)
                config.merge(self, [dependency_configuration])
                config.targets = config_targets

                target_name = dependency_configuration.targets[0]

                if target_name and target_name not in dependency_configuration.targets:
                    raise RuntimeError("Cannot find target: " + target_name)
                for target in dep.targets:
                    if not target in dependency_configuration.targets and not target_name:
                        raise RuntimeError("Cannot find target: " + target)

                if dependency_dependencies is not None:
                    for dependency in dependency_dependencies:
                        dependency.dynamically_added = True
                    dependency_dict = dict()
                    for dependency in (self.project.deps +
                                       dependency_dependencies):
                        dependency_id = Context.make_dependency_unique_identifier(
                            dependency)
                        if dependency_id not in dependency_dict:
                            dependency_dict[dependency_id] = dependency
                        else:
                            if not dependency.targets:
                                dependency_dict[dependency_id].targets = []
                            elif dependency_dict[dependency_id].targets:
                                dependency_dict[
                                    dependency_id].targets = helpers.filter_unique(
                                        dependency_dict[dependency_id].targets
                                        + dependency.targets)
                            if not dependency.shallow:
                                dependency_dict[dependency_id].shallow = False

                    self.project.deps = list(dependency_dict.values())

            if not self.context.options.no_copy_artifacts and self.deps_build:
                for artifact_binary in dependency_configuration.artifacts:
                    if not os.path.exists(artifact_binary.absolute_path):
                        continue
                    if artifact_binary.type not in ['library', 'program']:
                        continue
                    artifact_path_dir = os.path.dirname(artifact_binary.path)
                    dest_dir = os.path.join(self.make_out_path(),
                                            artifact_path_dir)
                    helpers.copy_file_if_recent(
                        source_path=artifact_binary.absolute_path,
                        destination_directory=dest_dir,
                        callback=lambda filename: print("Copy binary {}".
                                                        format(filename)))

            if not self.context.options.no_copy_licenses and self.deps_build:
                for artifact_license in dependency_configuration.artifacts:
                    if artifact_license.type != 'license':
                        continue
                    dep_id = self.find_dependency_id(artifact_license.location)
                    helpers.copy_file_if_recent(
                        source_path=artifact_license.absolute_path,
                        destination_directory=self.make_output_path(
                            os.path.join('licenses', dep_id)),
                        callback=lambda filename: print(
                            "Copy license {}".format(
                                os.path.join(dep_id, filename))))

    def find_dependency_id(self, path):
        common_path = None

        for cache_dir in self.cache_conf.locations:
            common_path = os.path.commonpath([path, cache_dir.location])
            if common_path != cache_dir.location:
                common_path = None
            else:
                break

        if not common_path:
            raise RuntimeError(
                "Can't find path in any cache directories {}".format(path))

        new_path = Path(os.path.relpath(path=path, start=common_path))
        return new_path.parts[0]

    def list_dep_binary_artifacts(self, config, dep, cache_dir):
        artifacts_list = []
        dep_path_build = self.get_dep_artifact_location(dep, cache_dir)
        expected_files = self.get_expected_files(config,
                                                 dep,
                                                 cache_dir,
                                                 True,
                                                 only_binaries=True,
                                                 allow_executable=True,
                                                 only_dlls=True)
        for file in expected_files:
            dep_path_build = os.path.abspath(dep_path_build)
            src_file_path = os.path.join(dep_path_build, file)
            artifacts_list.append(
                Artifact(os.path.abspath(src_file_path), file, dep_path_build))
            if self.is_linux() and file.endswith('.so'):
                src_file_path_glob = glob.glob(src_file_path + '.*')
                for other_file_path in src_file_path_glob:
                    abspath = os.path.abspath(other_file_path)
                    relpath = os.path.relpath(other_file_path, dep_path_build)
                    artifacts_list.append(
                        Artifact(abspath, relpath, dep_path_build))
        return artifacts_list

    def list_target_binary_artifacts(self, config, target):
        artifacts_list = []
        path_build = helpers.make_directory(self.make_out_path())
        expected_files = self.make_artifacts_from_context(
            config, target, allow_executable=True, only_dlls=True)
        for file in expected_files:
            path_build = os.path.abspath(path_build)
            src_file_path = os.path.join(path_build, file)
            artifacts_list.append(
                Artifact(os.path.abspath(src_file_path), file, path_build))
            if self.is_linux() and file.endswith('.so'):
                src_file_path_glob = glob.glob(src_file_path + '.*')
                for other_file_path in src_file_path_glob:
                    abspath = os.path.abspath(other_file_path)
                    relpath = os.path.relpath(other_file_path, path_build)
                    artifacts_list.append(
                        Artifact(abspath, relpath, path_build))
        return artifacts_list

    def clean_repo(self, repo_path):
        helpers.run_task(['git', 'clean', '-ffxd'],
                         cwd=repo_path,
                         stdout=subprocess.DEVNULL)
        helpers.run_task([
            'git', 'submodule', 'foreach', '--recursive', 'git', 'clean',
            '-ffxd'
        ],
                         cwd=repo_path,
                         stdout=subprocess.DEVNULL)
        helpers.run_task(['git', 'reset', '--hard'],
                         cwd=repo_path,
                         stdout=subprocess.DEVNULL)
        helpers.run_task([
            'git', 'submodule', 'foreach', '--recursive', 'git', 'reset',
            '--hard'
        ],
                         cwd=repo_path,
                         stdout=subprocess.DEVNULL)
        helpers.run_task(
            ['git', 'submodule', 'update', '--init', '--recursive'],
            cwd=repo_path,
            stdout=subprocess.DEVNULL)

    def clone_repo(self, dep, repo_path):
        dep.resolve()
        # NOTE: Can't use ['--depth', '1'] by default because of git describe --tags required for golem repos

        os.makedirs(repo_path)
        print("Cloning repository {} into {}".format(dep.repository,
                                                     repo_path))

        if dep.shallow:
            helpers.run_task(['git', 'init'], cwd=repo_path)
            helpers.run_task(
                ['git', 'remote', 'add', 'origin', dep.repository],
                cwd=repo_path)
            helpers.run_task(
                ['git', 'fetch', '--depth=1', 'origin', dep.resolved_hash],
                cwd=repo_path)
            helpers.run_task(['git', 'reset', '--hard', 'FETCH_HEAD'],
                             cwd=repo_path)
        else:
            helpers.run_task(['git', 'clone', '--', dep.repository, '.'],
                             cwd=repo_path)
            helpers.run_task(['git', 'checkout', dep.resolved_version],
                             cwd=repo_path)
            helpers.run_task(['git', 'reset', '--hard', dep.resolved_hash],
                             cwd=repo_path)

        helpers.run_task([
            'git', 'submodule', 'update', '--init', '--recursive', '--depth=1'
        ],
                         cwd=repo_path)

    def make_repo_ready(self, dep, cache_dir, should_clean=False):
        repo_path = self.get_dep_repo_location(dep, cache_dir)

        if os.path.exists(repo_path):
            if should_clean:
                self.clean_repo(repo_path)
        else:
            self.clone_repo(dep, repo_path)

        return repo_path

    def run_dep_command(self, dep, cache_dir, command):

        should_clean_repo = False
        if command == 'resolve':
            Logs.info("Resolving {} ({})...".format(dep.name, dep.version))
        elif command == 'build':
            Logs.info("Building {} ({})...".format(dep.name, dep.version))
            should_clean_repo = True
        else:
            Logs.info("Running {} on {} ({})...".format(
                command, dep.name, dep.version))

        dep_path = self.get_dep_location(dep, cache_dir)
        repo_path = self.make_repo_ready(dep,
                                         cache_dir,
                                         should_clean=should_clean_repo)
        build_path = self.get_dep_build_location(dep, cache_dir)

        global_dependencies_configuration = self.get_global_dependencies_configuration_file(
        )

        helpers.run_task([
            'golem', 'configure', '--targets=' + dep.name, '--runtime=' +
            (self.context.options.runtime
             if not dep.runtime else dep.runtime[0]), '--link=' +
            (self.context.options.link if not dep.link else dep.link[0]),
            '--arch=' + self.context.options.arch, '--variant=' +
            (self.context.options.variant
             if not dep.variant else dep.variant[0]), '--export=' + dep_path,
            '--no-copy-artifacts', '--no-copy-licenses',
            '--cache-dir=' + self.make_writable_cache_dir(),
            '--static-cache-dir=' + self.make_static_cache_dir(),
            '--static-cache-dependencies-regex=' +
            self.get_static_cache_dependencies_regex(), '--dir=' + build_path,
            '--resolved-dependencies-directory=' + build_path,
            '--no-recipes-repositories-fetch',
            '--only-update-dependencies-regex=' +
            self.get_only_update_dependencies_regex(),
            '--master-dependencies-configuration=' +
            self.resolved_master_dependencies,
            '--global-dependencies-configuration=' +
            global_dependencies_configuration, "--define-cache-directories=" +
            self.get_define_cache_directories()
        ] + (['--force-version=' +
              dep.resolved_version] if dep.shallow else []),
                         cwd=repo_path)

        if command == 'build':
            helpers.run_task(['golem', 'dependencies', '--dir=' + build_path],
                             cwd=repo_path)

        helpers.run_task(['golem', command, '--dir=' + build_path],
                         cwd=repo_path)

        if command == 'build':
            helpers.run_task(['golem', 'export', '--dir=' + build_path],
                             cwd=repo_path,
                             stdout=subprocess.DEVNULL)

    def can_open_json(self, dep, cache_dir, target_name=None):
        json_path = self.get_dep_artifact_json(dep=dep,
                                               cache_dir=cache_dir,
                                               target_name=target_name)
        return os.path.exists(json_path)

    def open_json(self, dep, cache_dir, target_name=None):
        json_path = self.get_dep_artifact_json(dep=dep,
                                               cache_dir=cache_dir,
                                               target_name=target_name)
        return open(json_path, 'r')

    def read_json(self, dep, cache_dir, target_name=None):
        json_path = self.get_dep_artifact_json(dep=dep,
                                               cache_dir=cache_dir,
                                               target_name=target_name)
        if not self.can_open_json(
                dep=dep, cache_dir=cache_dir, target_name=target_name):
            raise RuntimeError("Can't read file {}".format(json_path))
        with self.open_json(dep=dep,
                            cache_dir=cache_dir,
                            target_name=target_name) as file_json:
            return json.load(file_json)
        return None

    def read_dep_config_file(self, dep, cache_dir, target_name=None):
        json_path = self.get_dep_artifact_json(dep=dep,
                                               cache_dir=cache_dir,
                                               target_name=target_name)
        if not self.can_open_json(
                dep=dep, cache_dir=cache_dir, target_name=target_name):
            raise RuntimeError("Can't read file {}".format(json_path))

        return TargetConfigurationFile.load_file(path=json_path, context=self)

    def read_dep_configs(self, dep, cache_dir, target_name=None):
        config_file = self.read_dep_config_file(dep=dep,
                                                cache_dir=cache_dir,
                                                target_name=target_name)
        if config_file is None:
            return None
        return config_file.configuration

    def read_dep_config_file_list(self, dep, cache_dir):
        dep_configs = []
        if not dep.targets:
            config = self.read_dep_config_file(dep=dep,
                                               cache_dir=cache_dir,
                                               target_name=None)
            dep_configs.append(config)
        else:
            for target_name in dep.targets:
                config = self.read_dep_config_file(dep=dep,
                                                   cache_dir=cache_dir,
                                                   target_name=target_name)
                dep_configs.append(config)
        return dep_configs

    def read_dep_configs_list(self, dep, cache_dir):
        dep_configs = []
        if not dep.targets:
            config = self.read_dep_configs(dep=dep,
                                           cache_dir=cache_dir,
                                           target_name=None)
            dep_configs.append(config)
        else:
            for target_name in dep.targets:
                config = self.read_dep_configs(dep=dep,
                                               cache_dir=cache_dir,
                                               target_name=target_name)
                dep_configs.append(config)
        return dep_configs

    def make_target_name_from_context(self, config, target):

        if config.targets:
            return config.targets
        else:
            target_name = target.name + self.variant_suffix()

            if target.type_unique == 'library':
                if self.is_windows():
                    target_name = Context.make_windows_target_name(target_name)

            return [target_name]

    @staticmethod
    def make_windows_target_name(target_name):
        return os.path.join(os.path.dirname(target_name),
                            os.path.basename(target_name))

    def make_target_from_context(self,
                                 config,
                                 target,
                                 allow_executable=False,
                                 only_dlls=False):
        target_name = self.make_target_name_from_context(config, target)
        is_program = config.type_unique == 'program'
        if not self.is_windows() and not is_program:
            target_name = [
                Context.make_windows_target_name(t) for t in target_name
            ]

        result = list()
        for filename in target_name:
            for suffix in self.artifact_suffix(config):
                if (suffix != '.dll' or not config.dlls) and not is_program:
                    result.append(filename + suffix)
        if '.dll' in self.artifact_suffix(config) and config.dlls:
            result += [dll + '.dll' for dll in config.dlls]

        for filename in config.static_targets:
            for suffix in self.artifact_suffix_mode(config=config,
                                                    is_shared=False):
                if not self.is_windows() and not is_program:
                    filename = Context.make_windows_target_name(filename)
                result.append(filename + suffix)
        for filename in config.shared_targets:
            for suffix in self.artifact_suffix_mode(config=config,
                                                    is_shared=True):
                if not self.is_windows() and not is_program:
                    filename = Context.make_windows_target_name(filename)
                if suffix != '.dll' or not config.dlls:
                    result.append(filename + suffix)

        if allow_executable and is_program:
            for filename in target_name:
                for suffix in self.artifact_suffix(config):
                    result.append(filename + suffix)

        if only_dlls:
            result = [r for r in result if os.path.splitext(r)[1] != 'lib']
        return result

    @staticmethod
    def default_target_decorator(target_name, config, context):
        target_name = target_name + context.variant_suffix()

        if config.type_unique == 'library' and context.is_windows():
            target_name = Context.make_windows_target_name(target_name)

        return target_name

    def make_decorated_target_from_context(self, config, target_name):

        decorated_target_path = os.path.dirname(target_name)
        decorated_target_base = os.path.basename(target_name)

        target_decorators = config.target_decorators if config.target_decorators else [
            Context.default_target_decorator
        ]
        for target_decorator in target_decorators:
            decorated_target_base = target_decorator(decorated_target_base,
                                                     config, self)

        return os.path.join(decorated_target_path, decorated_target_base)

    def make_decorated_target_list_from_context(self, config, target_names):

        return [
            self.make_decorated_target_from_context(config=config,
                                                    target_name=target_name)
            for target_name in target_names
        ]

    def list_target_names_from_context(self, config, target):
        return config.targets if config.targets else [target.name]

    def get_target_names_from_context(self, config, target):
        if config.header_only:
            return []
        return self.list_target_names_from_context(config, target)

    def make_decorated_targets_from_context(self, config, target):

        targets = self.get_target_names_from_context(config, target)

        decorated_targets = []

        for target_name in targets:
            decorated_targets.append(
                self.make_decorated_target_from_context(config, target_name))

        return decorated_targets

    @staticmethod
    def default_artifacts_generator(decorated_target, config, context):
        artifacts = []
        for suffix in context.artifact_suffix(config):
            artifact = context.artifact_prefix(
                config) + decorated_target + suffix
            artifacts.append(artifact)
        return artifacts

    @staticmethod
    def internal_artifacts_generator(decorated_target, config, context):
        artifacts = []
        for suffix in context.artifact_suffix(config):
            artifact = context.artifact_prefix(
                config) + decorated_target + suffix
            artifacts.append(artifact)
            if suffix == '.so':
                artifacts.append(artifact + '.' + str(context.version.major))
                artifacts.append(artifact + '.' + context.version.semver_short)
        return artifacts

    def make_binary_artifact_from_context(self,
                                          config,
                                          decorated_target,
                                          enable_dev_libs=True,
                                          enable_run_libs=True,
                                          enable_exes=True):

        decorated_target_path = os.path.dirname(decorated_target)
        decorated_target_base = os.path.basename(decorated_target)

        if not enable_exes and config.type_unique == 'program':
            return []

        if config.type_unique == 'library' and config.header_only:
            return []

        if not enable_run_libs and not enable_dev_libs:
            return []

        artifacts = []
        artifacts_generators = []

        if config.artifacts_generators:
            artifacts_generators = config.artifacts_generators
        elif config.scripts:
            artifacts_generators = [Context.default_artifacts_generator]
        else:
            artifacts_generators = [Context.internal_artifacts_generator]

        for artifact_generator in artifacts_generators:
            artifacts += [
                os.path.join(decorated_target_path,
                             result) for result in artifact_generator(
                                 decorated_target_base, config, self)
            ]

        if not enable_dev_libs:
            filtered_artifacts = []
            for artifact in artifacts:
                extension = os.path.splitext(artifact)[1]
                if not extension or extension not in ['.a', '.lib', '.pdb']:
                    filtered_artifacts.append(artifact)
            artifacts = filtered_artifacts.copy()
        if not enable_run_libs:
            filtered_artifacts = []
            for artifact in artifacts:
                extension = os.path.splitext(artifact)[1]
                if not extension or extension not in ['.dll']:
                    filtered_artifacts.append(artifact)
            artifacts = filtered_artifacts.copy()

        return artifacts

    def make_binary_artifacts_from_context(self,
                                           config,
                                           target,
                                           enable_dev_libs=True,
                                           enable_run_libs=True,
                                           enable_exes=True):

        decorated_targets = self.make_decorated_targets_from_context(
            config, target)

        artifacts = []

        for decorated_target in decorated_targets:
            artifacts += self.make_binary_artifact_from_context(
                config=config,
                decorated_target=decorated_target,
                enable_dev_libs=enable_dev_libs,
                enable_run_libs=enable_run_libs,
                enable_exes=enable_exes)

        return artifacts

    def make_artifacts_from_context(self,
                                    config,
                                    target,
                                    allow_executable=False,
                                    only_dlls=False):
        return self.make_binary_artifacts_from_context(
            config=config,
            target=target,
            enable_dev_libs=not only_dlls,
            enable_run_libs=True,
            enable_exes=allow_executable)

    def get_expected_artifacts(self, dep, cache_dir):

        dep_configs = self.read_dep_configs_list(dep=dep, cache_dir=cache_dir)
        artifacts = []
        for config in dep_configs:
            if not config:
                return None
            for artifact in config.artifacts:
                if artifact.absolute_path not in artifacts:
                    artifacts.append(artifact.absolute_path)
        return artifacts

    def get_expected_files(self,
                           config,
                           dep,
                           cache_dir,
                           has_artifacts,
                           only_binaries=False,
                           allow_executable=False,
                           only_dlls=False):

        expected_files = []

        for target in dep.targets:
            if not only_binaries:
                json_file_path = self.get_dep_artifact_json(
                    dep=dep, cache_dir=cache_dir, target_name=target)
                expected_files.append(json_file_path)

            if not has_artifacts:
                return expected_files

            dep_configs = self.read_dep_configs(dep,
                                                cache_dir,
                                                target_name=target)
            if dep_configs is None or dep_configs.header_only:
                return expected_files

            if not target in dep_configs.targets:
                raise RuntimeError("Cannot find target: " + target)
            dep_configs.targets = [target]

            config = dep.merge_copy(self, [dep_configs])

            artifacts = dep_configs.artifacts_run
            for a in artifacts:
                if a not in expected_files:
                    expected_files.append(a)

            artifacts = dep_configs.artifacts_dev
            for a in artifacts:
                if a not in expected_files:
                    expected_files.append(a)

            continue

        if not dep.targets:

            if not only_binaries:
                json_file_path = self.get_dep_artifact_json(
                    dep=dep, cache_dir=cache_dir)
                expected_files.append(json_file_path)

            if not has_artifacts:
                return expected_files

            dep_configs = self.read_dep_configs(dep, cache_dir)
            if dep_configs is None or dep_configs.header_only:
                return expected_files

            config = dep.merge_copy(self, [dep_configs])

            artifacts = dep_configs.artifacts_run
            for a in artifacts:
                if a not in expected_files:
                    expected_files.append(a)

            artifacts = dep_configs.artifacts_dev
            for a in artifacts:
                if a not in expected_files:
                    expected_files.append(a)

        return expected_files

    def is_header_only(self, dep, cache_dir):

        dep_configs = self.read_dep_configs(dep, cache_dir)
        if dep_configs is None:
            return False

        return dep_configs.header_only

    def has_artifacts(self, command):
        return command in ['build', 'export']

    def dep_command(self, config, dep, command, enable_env):
        dep.resolve()

        cache_dir = dep.cache_dir

        json_paths = self.get_dep_artifact_json_list(dep, cache_dir)

        all_json_paths_exists = True
        for json_path in json_paths:
            if not os.path.exists(json_path):
                all_json_paths_exists = False

        if not all_json_paths_exists and not self.deps_resolve:
            raise RuntimeError(
                "Error: run golem resolve first! Can't find {}".format(
                    json_path))

        are_headers_available = os.path.exists(
            self.get_dep_include_location(dep, cache_dir))

        missing_artifacts = []
        are_artifacts_availables = True

        if all_json_paths_exists:
            expected_files = self.get_expected_artifacts(dep=dep,
                                                         cache_dir=cache_dir)
            for path in expected_files:
                if not os.path.exists(path):
                    are_artifacts_availables = False
                    missing_artifacts.append(path)
        else:
            are_artifacts_availables = False

        is_resolving = (command == 'resolve'
                        and dep.name not in self.deps_to_resolve
                        and self.deps_resolve)
        is_building = (command == 'build'
                       and (not are_headers_available
                            or not are_artifacts_availables))

        should_run_command = is_resolving or is_building

        if should_run_command:
            if missing_artifacts:
                Logs.warn("Missing artifacts: {} requires {}".format(
                    dep.name, missing_artifacts))
            if cache_dir.is_static:
                raise RuntimeError(
                    "Cannot find artifacts {} for {} from the static cache location {}"
                    .format(missing_artifacts, dep.name, cache_dir.location))
            self.run_dep_command(dep, cache_dir, command)
            self.deps_to_resolve.append(dep.name)

        self.use_dep(config, dep, cache_dir)

    def find_dep_cache_dir(self, dep, cache_conf):
        static_cache_dir = self.make_static_cache_dir()
        if self.get_static_cache_dependencies_regex() and static_cache_dir:
            pattern = re.compile(self.get_static_cache_dependencies_regex())
            if pattern.match(dep.repository):
                return CacheDir(location=static_cache_dir, is_static=True)

        cache_dir = self.find_existing_dep_cache_dir(dep, cache_conf)

        if cache_dir is None:
            cache_dir = self.find_writable_cache_dir(dep, cache_conf)

        return cache_dir

    def is_dep_in_cache_dir(self, dep, cache_dir):
        path = self.get_dep_location(dep, cache_dir)
        return os.path.exists(path)

    def find_existing_dep_cache_dir(self, dep, cache_conf):
        for cache_dir in cache_conf.locations:
            if self.is_dep_in_cache_dir(dep, cache_dir):
                return cache_dir
        return None

    def find_writable_cache_dir(self, dep, cache_conf):

        for cache_dir in cache_conf.locations:
            if not cache_dir.regex or cache_dir.is_static:
                continue

            pattern = re.compile(cache_dir.regex)
            if pattern.match(dep.repository):
                return cache_dir

        for cache_dir in cache_conf.locations:
            if not cache_dir.is_static:
                return cache_dir

        raise RuntimeError("Can't find any writable cache location")

    def export_dependency(self, config, dep):
        self.dep_command(config, dep, 'export', True)

    def link_dependency(self, config, dep):
        self.dep_command(config, dep, 'build', True)

    def get_build_path(self):
        # return self.context.out_dir if (hasattr(self.context, 'out_dir') and self.context.out_dir) else self.context.options.out if (hasattr(self.context.options, 'out') and self.context.options.out) else ''
        return self.make_golem_path('obj')

    def make_golem_path(self, path):
        return os.path.join(os.getcwd(), path)

    def make_build_path(self, path):
        return os.path.realpath(os.path.join(self.get_build_path(), path))

    def make_dependencies_slug(self, dependencies):
        string = ''
        for dependency in dependencies:
            string += json.dumps(Dependency.serialize_to_json(dependency),
                                 sort_keys=True)
        return hashlib.sha1(string.encode('utf-8')).hexdigest()[:8]

    def make_binary_foldername(self, dependencies=None):
        foldername = 'bin'

        if dependencies is not None:
            return foldername + '-' + self.make_dependencies_slug(
                dependencies=dependencies)

        if self.context.options.export:
            return foldername + '-' + self.make_dependencies_slug(
                dependencies=self.project.deps)

        # NOTE: 'conf' and 'bin-HASH' can conflict with use of master
        # dependencies configurations which bypass "default" dependencies
        # resolution process using versions declared in project file
        # TODO: Find a solution to tamper the conflict of master dependencies
        # configuration with "default" caching process of dependencies

        return foldername

    def make_target_out(self):
        return os.path.join('..', '..', self.make_binary_foldername())

    def make_out_path(self):
        return self.make_build_path(self.make_target_out())

    def make_output_path(self, path):
        return self.make_build_path(os.path.join('..', '..', path))

    def get_output_path(self):
        return self.make_output_path(".")

    def recursively_link_dependencies(self, config):
        self.recursively_apply_to_deps(config, self.link_dependency)

    def recursively_apply_to_deps(self, config, callback):
        deps_linked = []
        deps_count = 0
        while len(self.project.deps) != deps_count:
            deps_count = len(self.project.deps)
            for dep_name in config.deps:
                if dep_name in deps_linked:
                    continue
                for dep in self.project.deps:
                    if dep.dynamically_added == True:
                        continue
                    if dep_name == dep.name:
                        callback(config, dep)
                        deps_linked.append(dep.name)

    def build_target_gather_config(self, task, targets, config):

        config = config.copy()

        decorated_targets = self.make_decorated_target_list_from_context(
            config=config, target_names=targets)

        project_qt = False
        if any([feature.startswith("QT5") for feature in config.features]):
            project_qt = True

        if any([feature.startswith("QT6") for feature in config.features]):
            project_qt = True

        context_tasks_added = False

        wfeatures = []

        if project_qt and 'qt5' not in config.wfeatures:
            wfeatures.append('qt5')

        if self.is_debug() and self.is_windows():
            for i, feature in enumerate(config.features):
                if feature.startswith("QT5"):
                    config.features[i] += "D"
            for i, feature in enumerate(config.features):
                pass
                # NOTE: This may not be required anymore
                # INSTALL_QT6CORED can't be find, even in debug variant
                #if feature.startswith("QT6"):
                #    config.features[i] += "D"

        listinclude = self.list_include(config.includes, self.get_project_dir())
        qrc_sources = self.list_qt_qrc(config.source)

        listsource = []
        if project_qt:
            listsource += self.list_source(config.source) + qrc_sources + self.list_qt_ui(config.source)
        else:
            listsource += self.list_source(config.source)

        moc_candidates = []
        if project_qt:
            moc_candidates += self.list_moc(config.moc)

        qmldir_template_files = self.list_template(config.source)
        for path in qmldir_template_files:
            if os.path.basename(path.abspath()) == "qmldir.template":
                qmldir_template_path = path
                qmldir_path = self.context.root.find_or_declare(
                    os.path.join(os.path.dirname(path.abspath()), 'qmldir'))

                if str(qmldir_template_path) in self.context_tasks:
                    continue

                Logs.debug("Generating {} from {}".format(
                    qmldir_path, qmldir_template_path))

                self.context(name=qmldir_path,
                             features='subst',
                             source=qmldir_template_path,
                             target=qmldir_path,
                             PLUGIN_NAME=str(decorated_targets[0]))

                self.context_tasks.append(str(qmldir_template_path))
                context_tasks_added = True

        listmoc = []
        for moc_candidate in moc_candidates:
            with open(str(moc_candidate), 'r') as file:
                for line in file:
                    if re.search("Q_OBJECT", line):
                        listmoc.append(moc_candidate)

        version_short = None
        version_source = []
        version = Version(working_dir=self.get_project_dir(),
                          build_number=self.get_build_number())
        version_short = version.semver_short
        templates_to_process = []
        if task.version_template is not None:
            templates_to_process += task.version_template
        if task.templates is not None:
            templates_to_process += task.templates
        for template_to_process in templates_to_process:
            if isinstance(template_to_process, str):
                template_to_process = Template(source=template_to_process)
            version_template_src = self.context.root.find_node(
                self.make_project_path(template_to_process.source))

            if template_to_process.target is not None:
                filename = template_to_process.target
                version_template_dst = self.context.root.find_or_declare(
                    os.path.join(self.make_out_path(),
                                 template_to_process.target))
            else:
                filename, filename_ext = os.path.splitext(
                    os.path.basename(template_to_process.source))
                if filename_ext not in ['.template']:
                    filename = os.path.basename(
                        template_to_process.source) + '.cpp'
                version_template_dst = self.context.root.find_or_declare(
                    self.make_build_path(filename))

            if str(version_template_src) in self.context_tasks:
                continue

            Logs.debug("Generating {} from {}".format(
                str(version_template_dst), str(version_template_src)))

            def escape_string_for_macro_names(value):
                return re.sub('[^0-9a-zA-Z]+', '_', value)

            _, _, target_artifact_basename = self.make_target_artifact(
                config=config, decorated_target=decorated_targets[0])

            self.context(
                name=version_template_dst,
                features='subst',
                source=version_template_src,
                target=version_template_dst,
                VERSION_SEMVER=str(version.semver),
                VERSION_SEMVER_LONG=str(version.semver),
                VERSION_SEMVER_SHORT=str(version.semver_short),
                VERSION_SEMVER_MAJOR=str(version.major),
                VERSION_MAJOR=str(version.major),
                VERSION_SEMVER_MINOR=str(version.minor),
                VERSION_MINOR=str(version.minor),
                VERSION_SEMVER_PATCH=str(version.patch),
                VERSION_PATCH=str(version.patch),
                VERSION_SEMVER_PRERELEASE=str(version.prerelease),
                VERSION_PRERELEASE=str(version.prerelease),
                VERSION_SEMVER_BUILDMETADATA=str(version.buildmetadata),
                VERSION_BUILDMETADATA=str(version.buildmetadata),
                VERSION_BUILD_NUMBER=str(self.get_build_number(default=0)),
                VERSION=str(version.gitlong_semver),
                VERSION_GIT_DESCRIBE_LONG=str(version.gitlong),
                VERSION_LONG=str(version.gitlong),
                VERSION_GIT_DESCRIBE_SHORT=str(version.gitshort),
                VERSION_GIT_TAG=str(version.gitshort),
                VERSION_SHORT=str(version.gitshort),
                VERSION_GIT_REVISION=str(version.githash),
                VERSION_REVISION=str(version.githash),
                VERSION_HASH=str(version.githash),
                VERSION_GIT_MESSAGE=str(version.gitmessage),
                VERSION_MESSAGE=str(version.gitmessage),
                VERSION_GIT_BRANCH=str(version.gitbranch),
                VERSION_GIT_BRANCH_MACRO=escape_string_for_macro_names(
                    str(version.gitbranch)),
                VERSION_BRANCH=str(version.gitbranch),
                VERSION_BRANCH_MACRO=escape_string_for_macro_names(
                    str(version.gitbranch)),
                GOLEM_TMPL_VERSION_HASH=str(version.githash),
                GOLEM_TMPL_VERSION_REVISION=str(version.githash),
                GOLEM_TMPL_VERSION_MESSAGE=str(version.gitmessage),
                GOLEM_TMPL_VERSION_BUILD_NUMBER=str(
                    self.get_build_number(default=0)),
                GOLEM_TMPL_VERSION_SEMVER=str(version.semver),
                GOLEM_TMPL_VERSION_SEMVER_LONG=str(version.semver),
                GOLEM_TMPL_VERSION_SEMVER_SHORT=str(version.semver_short),
                GOLEM_TMPL_VERSION_SEMVER_MAJOR=str(version.major),
                GOLEM_TMPL_VERSION_SEMVER_MINOR=str(version.minor),
                GOLEM_TMPL_VERSION_SEMVER_PATCH=str(version.patch),
                GOLEM_TMPL_VERSION_SEMVER_PRERELEASE=str(version.prerelease),
                GOLEM_TMPL_VERSION_SEMVER_BUILDMETADATA=str(
                    version.buildmetadata),
                GOLEM_TMPL_VERSION=str(version.gitlong_semver),
                GOLEM_TMPL_VERSION_SHORT=str(version.gitshort),
                GOLEM_TMPL_VERSION_LONG=str(version.gitlong),
                GOLEM_TMPL_VERSION_MAJOR=str(version.major),
                GOLEM_TMPL_VERSION_MINOR=str(version.minor),
                GOLEM_TMPL_VERSION_PATCH=str(version.patch),
                GOLEM_TMPL_VERSION_PRERELEASE=str(version.prerelease),
                GOLEM_TMPL_VERSION_BUILDMETADATA=str(version.buildmetadata),
                GOLEM_TMPL_VERSION_GIT_DESCRIBE_SHORT=str(version.gitshort),
                GOLEM_TMPL_VERSION_GIT_DESCRIBE_LONG=str(version.gitlong),
                GOLEM_TMPL_VERSION_GIT_TAG=str(version.gitshort),
                GOLEM_TMPL_VERSION_GIT_REVISION=str(version.githash),
                GOLEM_TMPL_VERSION_GIT_MESSAGE=str(version.gitmessage),
                GOLEM_TMPL_VERSION_GIT_BRANCH=str(version.gitbranch),
                GOLEM_TMPL_VERSION_GIT_BRANCH_MACRO=
                escape_string_for_macro_names(str(version.gitbranch)),
                GOLEM_TMPL_VERSION_BRANCH=str(version.gitbranch),
                GOLEM_TMPL_VERSION_BRANCH_MACRO=escape_string_for_macro_names(
                    str(version.gitbranch)),
                GOLEM_TMPL_DATE_UTC_ISO8601=datetime.now().replace(
                    microsecond=0).isoformat() + 'Z',
                GOLEM_TMPL_PLATFORM=self.osname(),
                GOLEM_TMPL_RUNTIME=self.get_build_runtime(),
                GOLEM_TMPL_RUNTIME_VERSION=self.get_build_runtime_version(),
                GOLEM_TMPL_RUNTIME_VERSION_SEMVER=self.
                get_build_runtime_version_semver(),
                GOLEM_TMPL_ARCHITECTURE=self.get_arch(),
                GOLEM_TMPL_TARGET_ARTIFACT_BASENAME=target_artifact_basename)
            filename, filename_ext = os.path.splitext(filename)
            if filename_ext in ['.cpp', '.cxx', '.c', '.cc'
                                ] or template_to_process.build == True:
                version_source.append(version_template_dst)
            elif filename_ext in ['.hpp', '.hxx', '.h', '.hh'
                                  ] or template_to_process.build == True:
                include_path = self.make_build_path('.')
                if include_path not in listinclude:
                    listinclude.append(include_path)

            self.context_tasks.append(str(version_template_src))
            context_tasks_added = True

        if context_tasks_added:
            self.context.add_group()

        env_isystem = []
        for key in list(self.context.env.keys()):
            if key.startswith("ISYSTEM_"):
                for path in self.context.env[key]:
                    env_isystem.append(str(path))

        isystem_argument = '-isystem'
        if self.is_windows():
            isystem_argument = '/external:I'

        isystemflags = []
        for include in config.isystem:
            isystemflags.append('{}{}'.format(isystem_argument, include))
            env_isystem.append(include)

        for key in list(self.context.env.keys()):
            if key.startswith(
                    "INCLUDES_") and not key.startswith("INCLUDES_QT5") and not key.startswith("INCLUDES_QT6"):
                for path in self.context.env[key]:
                    if path.startswith('/usr'):
                        isystemflags.append('-isystem' + str(Path(str(path))))
                        env_isystem.append(str(Path(str(path))))

        config_all_use = helpers.filter_unique(config.use + config.features)
        for config_use in config_all_use:
            if config_use.startswith('QT5') or config_use.startswith('QT6'):
                for key in list(self.context.env.keys()):
                    if (key.startswith("INCLUDES_QT5") or key.startswith("INCLUDES_QT6")) and config_use in key:
                        for path in self.context.env[key]:
                            isystemflags.append('{}{}'.format(
                                isystem_argument, str(Path(str(path)))))
                            env_isystem.append(str(Path(str(path))))

        if self.is_windows():
            version_short = None

        target_type = None
        if config.type_unique == 'program' and self.is_android():
            target_type = 'library'
        else:
            target_type = config.type

        target_cxxflags = config.program_cxxflags if target_type == 'program' else config.library_cxxflags
        target_linkflags = config.program_linkflags if target_type == 'program' else config.library_linkflags

        env_cxxflags = self.context.env.CXXFLAGS.copy()
        env_defines = self.context.env.DEFINES.copy()
        for config_use in config_all_use:
            if config_use.startswith('QT5') or config_use.startswith('QT6'):
                for key in list(self.context.env.keys()):
                    if (key.startswith("DEFINES_QT5") or key.startswith("DEFINES_QT6")) and config_use in key:
                        env_defines += self.context.env[key].copy()
        env_includes = []

        rpath_link = []
        if not self.is_windows() and not self.is_darwin():
            rpath_links = config.rpath_link.copy()
            if 'QTLIBS' in self.context.env:
                rpath_links.append(self.context.env.QTLIBS)
            if rpath_links:
                rpath_link += [
                    '-Wl,-rpath-link,{}'.format(':'.join(rpath_links))
                ]

        if self.is_darwin() and 'QTLIBS' in self.context.env:
            if self.context.env.QTLIBS:
                rpath_link += ['-Wl,-rpath,{}'.format(self.context.env.QTLIBS)]

        # TODO: Should link static library with absolute path on macOS
        #if self.is_darwin():
        #    stlib_filename = os.path.join(path, self.artifact_prefix(
        #        config
        #    ) + decorated_target + self.artifact_suffix_dev(
        #        config))
        #    if stlib_filename not in config.ldflags:
        #        config.ldflags.append(stlib_filename)
        
        filtered_wfeatures = helpers.filter_unique(config.wfeatures +
                                                   wfeatures)
        
        qt_cxxflags = []
        if 'qt5' in filtered_wfeatures and self.is_msvc_like():
            qt_cxxflags += ['/Zc:__cplusplus', '/permissive-']

        final_cxxflags = helpers.filter_unique(config.cxxflags +
                                               target_cxxflags + isystemflags + qt_cxxflags)

        for flag in final_cxxflags:
            if flag.startswith('-std=c++') or flag.startswith('/std:c++'):
                if 'CXXFLAGS_qt5' in self.context.env:
                    copy_flags = self.context.env.CXXFLAGS_qt5.copy()
                    copy_flags = [
                        f for f in copy_flags
                        if (not f.startswith('-std=c++')
                            and not f.startswith('/std:c++'))
                    ]
                    self.context.env.CXXFLAGS_qt5 = copy_flags
                if 'CXXFLAGS_qt6' in self.context.env:
                    copy_flags = self.context.env.CXXFLAGS_qt6.copy()
                    copy_flags = [
                        f for f in copy_flags
                        if (not f.startswith('-std=c++')
                            and not f.startswith('/std:c++'))
                    ]
                    self.context.env.CXXFLAGS_qt6 = copy_flags
                break

        if 'qt5' in filtered_wfeatures and self.is_darwin():
            env_cxxflags += ['-iframework{}'.format(self.context.env.QTLIBS)]

        rpath_option = config.rpath
        linkflags_option = helpers.filter_unique(config.linkflags +
                                                 target_linkflags + rpath_link)

        config_lib = []
        absolute_path_lib = []
        for lib in config.lib:
            if os.path.isabs(lib):
                absolute_path_lib.append(lib)
            else:
                config_lib.append(lib)

        config_stlib = []
        absolute_path_stlib = []
        for lib in config.stlib:
            if os.path.isabs(lib):
                absolute_path_stlib.append(lib)
            else:
                config_stlib.append(lib)

        ldflags_option = helpers.filter_unique(absolute_path_lib +
                                               absolute_path_stlib +
                                               config.ldflags)
        if self.is_linux():
            if not config.rpath:
                lib_paths = list()
                lib_paths.append('$ORIGIN')
                if 'qt5' in filtered_wfeatures:
                    lib_paths.append(self.context.env.QTLIBS)

                lib_artifacts = list()
                for target_name in targets:
                    decorated_target = self.make_decorated_target_from_context(
                        config=config, target_name=target_name)
                    artifacts = self.make_artifacts_list(
                        config=config, decorated_target=decorated_target)
                    for artifact in artifacts:
                        lib_artifacts.append(
                            self.create_artifact(
                                path=artifact,
                                location=self.make_out_path(),
                                type='library',
                                scope=None,
                                target=target_name,
                                decorated_target=decorated_target))

                libraries_list = [
                    os.path.basename(artifact.path)
                    for artifact in config.artifacts
                    if artifact.type in ['library']
                    and not artifact.path.endswith('.a')
                ]
                local_artifacts = config.artifacts.copy()
                for local_artifact in local_artifacts:
                    local_artifact.location = self.make_out_path()
                lib_paths += self.patch_linux_binary_artifacts(
                    binary_artifacts=lib_artifacts,
                    prefix_path='$ORIGIN',
                    source_artifacts=local_artifacts,
                    libraries=libraries_list,
                    simulate=True,
                    relative_path=True)
                lib_paths = helpers.filter_unique(lib_paths)
                rpath_option = lib_paths

        return BuildTarget(
            config=config,
            defines=config.defines,
            includes=listinclude,
            source=helpers.filter_unique(listsource + version_source),
            target=[
                os.path.join(self.make_target_out(), decorated_target)
                for decorated_target in decorated_targets
            ],
            name=task.name,
            cxxflags=final_cxxflags,
            cflags=helpers.filter_unique(config.cflags + target_cxxflags +
                                         isystemflags + qt_cxxflags),
            linkflags=linkflags_option,
            ldflags=ldflags_option,
            use=config_all_use,
            uselib=config.uselib,
            moc=listmoc,
            features=filtered_wfeatures,
            install_path=None,
            vnum=version_short,
            depends_on=version_source,
            lib=helpers.filter_unique(
                config_lib + (config.system if self.is_shared() else [])),
            stlib=helpers.filter_unique(
                config_stlib + (config.system if self.is_static() else [])),
            libpath=config.libpath,
            stlibpath=config.stlibpath,
            cppflags=config.cppflags,
            framework=config.framework,
            frameworkpath=config.frameworkpath,
            rpath=rpath_option,
            cxxdeps=config.cxxdeps,
            ccdeps=config.ccdeps,
            linkdeps=config.linkdeps,
            env_defines=env_defines,
            env_cxxflags=env_cxxflags,
            env_includes=env_includes,
            env_isystem=env_isystem)

    def initialize_compiler_commands(self):
        self.compiler_commands = []

    def initialize_vscode_configs(self):
        self.vscode_configs = []

    def initialize_clangd_configs(self):
        self.clangd_configs = []

    def initialize_compile_commands_configs(self):
        self.compile_commands_configs = []

    def append_compiler_commands(self, build_target):
        self.compiler_commands += self.make_compiler_commands(build_target)

    def make_compiler_commands(self, build_target):
        compiler_commands = []

        # TODO: There are duplicates between build_target.cxxflags and 
        # build_target.env_isystem. But we can't just remove any duplicates
        # since sometimes duplicates may be used to override a behavior if 
        # they are placed in last position. Therefore, we need to find a 
        # different approach.

        windows_isystem = '/external:I'

        for source in build_target.source:
            file = {
                "directory": self.get_build_path(),
                "arguments": [
                    self.context.env.get_flat('CXX')
                ] + build_target.env_cxxflags + build_target.cxxflags +
                [(windows_isystem
                  if self.is_msvc_like() else '-isystem') + str(d)
                 for d in build_target.env_isystem] +
                ['-I' + str(d) for d in build_target.env_includes] +
                ['-I' + str(d) for d in build_target.includes] +
                ['-D' + d for d in build_target.env_defines] +
                ['-D' + d for d in build_target.defines] +
                [str(source), '-c'] + build_target.cppflags,
                "file": str(source)
            }
            compiler_commands.append(file)

        return compiler_commands

    def save_compiler_commands_list(self, path, compiler_commands):
        with open(path, 'w') as fp:
            json.dump(compiler_commands, fp, indent=4)

    def save_compiler_commands(self, path):
        self.save_compiler_commands_list(path, self.compiler_commands)

    def append_vscode_config_target(self, compiler_commands_path, task,
                                    targets, config):
        if not self.context.options.vscode:
            return

        targets_includes = []

        build_target = self.build_target_gather_config(task=task,
                                                       targets=targets,
                                                       config=config)

        targets_includes += [str(item) for item in self.list_include(build_target.config.includes, self.get_project_dir())]
        targets_includes += [str(item) for item in Context.get_parent_directories(self.list_source(build_target.config.source))]
        targets_includes += [str(item) for item in build_target.env_isystem]
        targets_includes += [str(item) for item in build_target.env_includes]
        targets_includes += [str(item) for item in build_target.includes]

        targets_includes = helpers.filter_unique(targets_includes)

        vscode_config = OrderedDict({
            "name": task.name,
            "intelliSenseMode": "msvc-x64" if Context.is_windows() else
            "gcc-x64" if Context.is_linux() else "clang-x64",
            "includePath": targets_includes,
            "defines": [],
            "compileCommands": compiler_commands_path,
            "browse": {
                "path": targets_includes,
                "limitSymbolsToIncludedHeaders": True,
                "databaseFilename": "${workspaceRoot}/.vscode/cache/.browse.VC.db"
            }
        })

        if self.is_darwin():
            vscode_config.update({
                'macFrameworkPath': [
                    "/System/Library/Frameworks", "/Library/Frameworks"
                ] + ([] if not 'qt5' in config.wfeatures else
                     [self.context.env.QTLIBS])
            })

        cxx_standard = ''
        for cxxflag in config.cxxflags:
            if cxxflag.startswith('-std=') or (cxxflag.startswith('/std:') and
                                               cxxflag != '/std:c++latest'):
                cxx_standard = cxxflag[5:]
                break

        if cxx_standard:
            vscode_config.update({"cppStandard": cxx_standard})

        if Context.is_linux():
            vscode_config.update(
                {"compilerPath": "/usr/bin/" + self.context.env.CXX_NAME})

        self.vscode_configs.append(vscode_config)

    def generate_vscode_config(self, compiler_commands_path):
        if not self.context.options.vscode:
            return

        targets_cxxflags = []
        targets_includes = []
        targets_wfeatures = []

        def list_all_targets_includes(task, targets, config, targets_includes,
                                      targets_cxxflags, targets_wfeatures):
            build_target = self.build_target_gather_config(task=task,
                                                           targets=targets,
                                                           config=config)

            targets_includes += [str(item) for item in self.list_include(build_target.config.includes, self.get_project_dir())]
            targets_includes += [str(item) for item in Context.get_parent_directories(self.list_source(build_target.config.source))]
            targets_includes += [str(item) for item in build_target.env_isystem]
            targets_includes += [str(item) for item in build_target.env_includes]
            targets_includes += [str(item) for item in build_target.includes]
            targets_cxxflags += config.cxxflags
            targets_wfeatures += config.wfeatures

        self.call_build_target(
            lambda task, targets, config: list_all_targets_includes(
                task=task,
                targets=targets,
                config=config,
                targets_includes=targets_includes,
                targets_cxxflags=targets_cxxflags,
                targets_wfeatures=targets_wfeatures))

        targets_includes = helpers.filter_unique(targets_includes)

        vscode_config = OrderedDict({
            "name": "Default",
            "intelliSenseMode": "msvc-x64" if Context.is_windows() else
            "gcc-x64" if Context.is_linux() else "clang-x64",
            "includePath": targets_includes,
            "defines": [],
            "compileCommands": compiler_commands_path,
            "browse": {
                "path": targets_includes,
                "limitSymbolsToIncludedHeaders": True,
                "databaseFilename": "${workspaceRoot}/.vscode/cache/.browse.VC.db"
            }
        })

        if self.is_darwin():
            vscode_config.update({
                'macFrameworkPath': [
                    "/System/Library/Frameworks", "/Library/Frameworks"
                ] + ([] if not 'qt5' in targets_wfeatures else
                     [self.context.env.QTLIBS])
            })

        cxx_standard = ''
        for cxxflag in targets_cxxflags:
            if cxxflag.startswith('-std=') or (cxxflag.startswith('/std:') and
                                               cxxflag != '/std:c++latest'):
                cxx_standard = cxxflag[5:]
                break

        if cxx_standard:
            vscode_config.update({"cppStandard": cxx_standard})

        if Context.is_linux():
            vscode_config.update(
                {"compilerPath": "/usr/bin/" + self.context.env.CXX_NAME})

        data = OrderedDict(
            {"configurations": [vscode_config] + self.vscode_configs})
        properties_path = os.path.join(self.get_project_dir(), '.vscode',
                                       'c_cpp_properties.json')
        with open(properties_path, 'w') as outfile:
            json.dump(data, outfile, indent=4, sort_keys=True)

    def get_vscode_path(self):
        return self.make_golem_path('vscode')

    def make_vscode_path(self, path):
        return os.path.join(self.get_vscode_path(), path)

    def append_clangd_config_target(self, compiler_commands_path, task,
                                    targets, config):
        if not self.context.options.clangd:
            return

        targets_includes = []

        build_target = self.build_target_gather_config(task=task,
                                                       targets=targets,
                                                       config=config)

        targets_includes += [str(item) for item in self.list_include(build_target.config.includes, self.get_project_dir())]
        targets_includes += [str(item) for item in Context.get_parent_directories(self.list_source(build_target.config.source))]
        targets_includes += [str(item) for item in build_target.env_isystem]
        targets_includes += [str(item) for item in build_target.env_includes]
        targets_includes += [str(item) for item in build_target.includes]

        targets_includes = helpers.filter_unique(targets_includes)

    def generate_clangd_config(self, compiler_commands_path):
        if not self.context.options.clangd:
            return

        targets_cxxflags = []
        targets_includes = []
        targets_wfeatures = []

        def list_all_targets_includes(task, targets, config, targets_includes,
                                      targets_cxxflags, targets_wfeatures):
            build_target = self.build_target_gather_config(task=task,
                                                           targets=targets,
                                                           config=config)

            targets_includes += [str(item) for item in self.list_include(build_target.config.includes, self.get_project_dir())]
            targets_includes += [str(item) for item in Context.get_parent_directories(self.list_source(build_target.config.source))]
            targets_includes += [str(item) for item in build_target.env_isystem]
            targets_includes += [str(item) for item in build_target.env_includes]
            targets_includes += [str(item) for item in build_target.includes]
            targets_cxxflags += config.cxxflags
            targets_wfeatures += config.wfeatures

        self.call_build_target(
            lambda task, targets, config: list_all_targets_includes(
                task=task,
                targets=targets,
                config=config,
                targets_includes=targets_includes,
                targets_cxxflags=targets_cxxflags,
                targets_wfeatures=targets_wfeatures))

        targets_includes = helpers.filter_unique(targets_includes)

        data = {
            'compilation_database_path': os.path.abspath(os.path.dirname(compiler_commands_path))
        }
        
        config_file_template_path = os.path.join(self.get_golemcpp_data_dir(), 'clangd.template')
        with open(config_file_template_path, 'r') as config_file_template:
            config_file_template_src = string.Template(config_file_template.read())
            config_file_src = config_file_template_src.safe_substitute(data)

            config_file_path = os.path.join(self.get_project_dir(), '.clangd')
            with open(config_file_path, 'w') as outfile:
                outfile.write(config_file_src)

    def get_clangd_path(self):
        return self.make_golem_path('clangd')

    def make_clangd_path(self, path):
        return os.path.join(self.get_clangd_path(), path)

    def append_compile_commands_config_target(self, compiler_commands_path, task,
                                    targets, config):
        if not self.context.options.compile_commands:
            return

        targets_includes = []

        build_target = self.build_target_gather_config(task=task,
                                                       targets=targets,
                                                       config=config)

        targets_includes += [str(item) for item in self.list_include(build_target.config.includes, self.get_project_dir())]
        targets_includes += [str(item) for item in Context.get_parent_directories(self.list_source(build_target.config.source))]
        targets_includes += [str(item) for item in build_target.env_isystem]
        targets_includes += [str(item) for item in build_target.env_includes]
        targets_includes += [str(item) for item in build_target.includes]

        targets_includes = helpers.filter_unique(targets_includes)

    def generate_compile_commands_config(self, compiler_commands_path):
        if not self.context.options.compile_commands:
            return

        targets_cxxflags = []
        targets_includes = []
        targets_wfeatures = []

        def list_all_targets_includes(task, targets, config, targets_includes,
                                      targets_cxxflags, targets_wfeatures):
            build_target = self.build_target_gather_config(task=task,
                                                           targets=targets,
                                                           config=config)
            
            targets_includes += [str(item) for item in self.list_include(build_target.config.includes, self.get_project_dir())]
            targets_includes += [str(item) for item in Context.get_parent_directories(self.list_source(build_target.config.source))]
            targets_includes += [str(item) for item in build_target.env_isystem]
            targets_includes += [str(item) for item in build_target.env_includes]
            targets_includes += [str(item) for item in build_target.includes]
            targets_cxxflags += config.cxxflags
            targets_wfeatures += config.wfeatures

        self.call_build_target(
            lambda task, targets, config: list_all_targets_includes(
                task=task,
                targets=targets,
                config=config,
                targets_includes=targets_includes,
                targets_cxxflags=targets_cxxflags,
                targets_wfeatures=targets_wfeatures))

    def get_compile_commands_path(self):
        return self.make_golem_path('compile_commands')

    def make_compile_commands_path(self, path):
        return os.path.join(self.get_compile_commands_path(), path)

    def build_target(self, task, targets, config):
        build_target = self.build_target_gather_config(task=task,
                                                       targets=targets,
                                                       config=config)

        self.append_compiler_commands(build_target)

        if self.context.options.vscode:
            compiler_commands_list = self.make_compiler_commands(build_target)

            vscode_dir = self.get_vscode_path()
            compiler_commands_path = self.make_vscode_path(
                task.name + '_compile_commands.json')

            if not os.path.exists(vscode_dir):
                helpers.make_directory(vscode_dir)
            if os.path.exists(compiler_commands_path):
                os.remove(compiler_commands_path)
            self.save_compiler_commands_list(compiler_commands_path,
                                             compiler_commands_list)
            self.append_vscode_config_target(
                compiler_commands_path=compiler_commands_path,
                task=task,
                targets=targets,
                config=config)

        if self.context.options.clangd:
            compiler_commands_list = self.make_compiler_commands(build_target)

            clangd_dir = self.make_clangd_path(task.name)
            compiler_commands_path = os.path.join(clangd_dir, 'compile_commands.json')

            if not os.path.exists(clangd_dir):
                helpers.make_directory(clangd_dir)
            if os.path.exists(compiler_commands_path):
                os.remove(compiler_commands_path)
            self.save_compiler_commands_list(compiler_commands_path,
                                             compiler_commands_list)
            self.append_clangd_config_target(
                compiler_commands_path=compiler_commands_path,
                task=task,
                targets=targets,
                config=config)

        if self.context.options.compile_commands:
            compiler_commands_list = self.make_compiler_commands(build_target)

            compile_commands_dir = self.make_compile_commands_path(task.name)
            compiler_commands_path = os.path.join(compile_commands_dir, 'compile_commands.json')

            if not os.path.exists(compile_commands_dir):
                helpers.make_directory(compile_commands_dir)
            if os.path.exists(compiler_commands_path):
                os.remove(compiler_commands_path)
            self.save_compiler_commands_list(compiler_commands_path,
                                             compiler_commands_list)
            self.append_compile_commands_config_target(
                compiler_commands_path=compiler_commands_path,
                task=task,
                targets=targets,
                config=config)

        build_fun = None

        if task.type_unique == 'program' and self.is_android():
            build_fun = self.context.shlib
        elif task.type_unique == 'library':
            if task.link:
                if task.link_unique == 'shared':
                    build_fun = self.context.shlib
                elif task.link_unique == 'static':
                    build_fun = self.context.stlib
                else:
                    raise Exception("ERROR: Bad link option {}".format(
                        task.link_unique))
            elif self.is_shared():
                build_fun = self.context.shlib
            elif self.is_static():
                build_fun = self.context.stlib
            else:
                raise Exception("ERROR: Bad link option {}".format(
                    self.context.options.link))
        elif task.type_unique == 'program':
            build_fun = self.context.program
        elif task.type_unique == 'objects':
            build_fun = self.context.objects
        elif task.type_unique == 'task':
            for arg in task.args:
                if arg in ['source', 'target']:
                    nodes = helpers.filter_unique(
                        helpers.parameter_to_list(task.args[arg]))
                    for i, _ in enumerate(nodes):
                        if arg in ['source']:
                            nodes[i] = self.make_project_path(nodes[i])
                        if arg in ['target']:
                            nodes[i] = os.path.join(self.make_target_out(),
                                                    nodes[i])
                        nodes[i] = self.context.root.find_or_declare(
                            str(nodes[i])) if os.path.isabs(
                                nodes[i]
                            ) else self.context.srcnode.find_or_declare(
                                str(nodes[i]))
                    task.args[arg] = nodes
            self.context(name=task.name, **task.args)
            return
        else:
            raise Exception("ERROR: Bad target type {}".format(
                task.type_unique))

        if build_target.config.scripts:
            for callback in build_target.config.scripts:
                callback(self)

                if self.is_windows():
                    continue

                if config.type[0] not in ['library']:
                    continue

                if self.is_darwin():
                    lib_artifacts = list()
                    for target_name in targets:
                        decorated_target = self.make_decorated_target_from_context(
                            config=config, target_name=target_name)
                        artifacts = self.make_artifacts_list(
                            config=config, decorated_target=decorated_target)
                        for artifact in artifacts:
                            lib_artifacts.append(
                                self.create_artifact(
                                    path=artifact,
                                    location=self.make_out_path(),
                                    type='library',
                                    scope=None,
                                    target=target_name,
                                    decorated_target=decorated_target))
                    self.patch_darwin_binary_artifacts(
                        binary_artifacts=lib_artifacts,
                        source_artifacts=config.artifacts)
            return

        build_fun(defines=build_target.defines,
                  includes=build_target.includes,
                  source=build_target.source,
                  target=build_target.target[0],
                  name=build_target.name,
                  cxxflags=build_target.cxxflags,
                  cflags=build_target.cflags,
                  linkflags=build_target.linkflags,
                  ldflags=build_target.ldflags,
                  use=build_target.use,
                  uselib=build_target.uselib,
                  moc=build_target.moc,
                  features=build_target.features,
                  install_path=build_target.install_path,
                  vnum=build_target.vnum,
                  depends_on=build_target.depends_on,
                  lib=build_target.lib,
                  stlib=build_target.stlib,
                  libpath=build_target.libpath,
                  stlibpath=build_target.stlibpath,
                  cppflags=build_target.cppflags,
                  framework=build_target.framework,
                  frameworkpath=build_target.frameworkpath,
                  rpath=build_target.rpath,
                  cxxdeps=build_target.cxxdeps,
                  ccdeps=build_target.ccdeps,
                  linkdeps=build_target.linkdeps)

    def find_dylibs(self, paths):
        result = list()
        for path in paths:
            pattern = re.compile(r'.*\.dylib([\.].*)*$')
            path_basename = os.path.basename(path)
            if pattern.match(path_basename):
                result.append(path)
        return result

    def make_artifacts_list(self, config, decorated_target):
        artifacts_dev = self.make_binary_artifact_from_context(
            config,
            decorated_target,
            enable_dev_libs=True,
            enable_run_libs=True,
            enable_exes=False)

        artifacts_run = self.make_binary_artifact_from_context(
            config,
            decorated_target,
            enable_dev_libs=False,
            enable_run_libs=True,
            enable_exes=True)

        return helpers.filter_unique(artifacts_run + artifacts_dev)

    def cppcheck_target(self, task, targets, config):

        build_target = self.build_target_gather_config(task=task,
                                                       targets=targets,
                                                       config=config)

        all_includes = build_target.env_isystem + \
            build_target.env_includes + build_target.includes
        all_includes = ['-I' + str(d) for d in all_includes]

        all_defines = build_target.env_defines + build_target.defines
        all_defines = ['-D' + str(d) for d in all_defines]

        all_sources = build_target.source
        all_sources = [str(d) for d in all_sources]

        cppcheck_dir = self.make_build_path("cppcheck")
        helpers.make_directory(cppcheck_dir)

        enable = 'all'
        if self.project.cppcheck_enable:
            enable = ','.join(self.project.cppcheck_enable)

        options = []
        if self.context.options.output_file:
            output_path = os.path.join(self.get_project_dir(),
                                       self.context.options.output_file)
            options += [
                '--xml', '--xml-version=2', '--output-file=' + output_path
            ]

        command = [
            'cppcheck', '--enable=' + enable,
            '--suppress=missingIncludeSystem', '--quiet', '-v'
        ] + options + all_defines + all_sources

        self.context(rule=' '.join(command),
                     always=True,
                     name=task.name,
                     cwd=cppcheck_dir)

    def call_build_target(self, build_target_fun, build_recursively=False):
        self.built_tasks = []
        tasks_and_targets = self.get_tasks_and_targets_to_process()

        if self.context.options.export:
            # Iterate over exported tasks to preload all the required
            # dependencies and help constructing the correct slug for the
            # binary folder name
            tasks_and_targets_bis = self.get_tasks_and_targets_to_process(
                tasks_source=self.project.exports)
            for task, targets in tasks_and_targets_bis:
                _, _ = self.iterate_over_task(task=task, targets=targets)

        for task, targets in tasks_and_targets:
            if task.header_only:
                continue
            _, _ = self.iterate_over_task(task=task,
                                          targets=targets,
                                          build_method=build_target_fun,
                                          build_recursively=build_recursively)

    def cppcheck(self):
        cppcheck_dir = self.make_golem_path("cppcheck")
        if os.path.exists(cppcheck_dir):
            helpers.remove_tree(self, cppcheck_dir)

        self.call_build_target(self.cppcheck_target)

    def clang_tidy_target(self, task, targets, config):

        build_target = self.build_target_gather_config(task=task,
                                                       targets=targets,
                                                       config=config)

        clang_tidy_dir = self.make_golem_path('clang-tidy')

        self.append_compiler_commands(build_target)

        checks = '*'
        if self.project.clang_tidy_checks:
            checks = ','.join(self.project.clang_tidy_checks)

        command = [
            'clang-tidy', '-quiet', '-checks=' + checks,
            '-p=' + str(clang_tidy_dir)
        ]

        command += [str(s) for s in build_target.source]

        self.context(rule=' '.join(command),
                     always=True,
                     name=task.name,
                     cwd=clang_tidy_dir)

    def clang_tidy(self):
        clang_tidy_dir = self.make_golem_path('clang-tidy')
        if os.path.exists(clang_tidy_dir):
            helpers.remove_tree(self, clang_tidy_dir)
        helpers.make_directory(clang_tidy_dir)

        self.initialize_compiler_commands()

        self.call_build_target(self.clang_tidy_target)

        compiler_commands_path = os.path.join(clang_tidy_dir,
                                              'compile_commands.json')
        self.save_compiler_commands(compiler_commands_path)

    def vswhere_get_installation_path(self):
        cmd = [
            'cmd', '/c', 'vswhere', '-latest', '-products', '*', '-property',
            'installationPath'
        ]
        print(' '.join(cmd))
        prg_path = os.environ.get(
            'ProgramFiles(x86)',
            os.environ.get('ProgramFiles', 'C:\\Program Files (x86)'))

        ret = subprocess.Popen(cmd,
                               cwd=os.path.join(prg_path,
                                                'Microsoft Visual Studio',
                                                'Installer'),
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
        out, _ = ret.communicate()
        if ret.returncode:
            raise RuntimeError("ERROR: " + ' '.join(cmd))
        lines = out.decode(sys.stdout.encoding).splitlines()
        if not lines[0]:
            raise RuntimeError(
                "No result when requesting installationPath to vswhere.exe")
        msvc_path = lines[0]
        return msvc_path

    def run_command_with_msvisualcpp(self, command, cwd):
        msvc_path = self.vswhere_get_installation_path()

        vcvars = msvc_path + '\\VC\\Auxiliary\\Build\\vcvarsall.bat'
        call_msvc = [
            'call', '"' + vcvars + '"', self.context.env['MSVC_TARGETS'][0],
            '&&'
        ]

        cmd = call_msvc + command

        build_cmd = ' '.join(cmd)
        if subprocess.call(build_cmd, cwd=cwd, shell=True):
            return 1

    def run_command(self, command, cwd, env=None):
        if env:
            my_env = os.environ.copy()
            for k, v in env.items():
                my_env[k] = v
            if subprocess.call(command, cwd=cwd, shell=self.is_windows(), env=my_env):
                return 1
        else:
            if subprocess.call(command, cwd=cwd, shell=self.is_windows()):
                return 1

    def run_build_command(self, command, cwd, env=None):
        if self.is_windows():
            ret = self.run_command_with_msvisualcpp(command=command, cwd=cwd)
        else:
            ret = self.run_command(command=command, cwd=cwd, env=env)
        if ret:
            print("Error when running command \"" + ' '.join(command) +
                  "\" in directory \"" + str(cwd) + "\"")
            return 1

    def get_vs_version(self):
        return self.context.env.MSVC_VERSION

    def find_msvc_toolset_number(self, vs_version):
        toolsets = {
            "16": "142",
            "15": "141",
            "14": "140",
            "12": "120",
            "11": "110",
            "10": "100",
            "9": "90",
            "8": "80"
        }
        if vs_version is None:
            vs_version = self.get_vs_version()

        vs_version = str(vs_version)

        if len(vs_version) < 2:
            raise RuntimeError("Bad vs version")

        vs_version = vs_version[:2]

        if vs_version not in toolsets:
            raise RuntimeError(
                "Cannot find any platform toolset for vs version: {}".format(
                    vs_version))

        return toolsets[vs_version]

    def find_msvc_toolset(self, vs_version):
        return 'v{}'.format(
            self.find_msvc_toolset_number(vs_version=vs_version))

    def get_current_msvc_toolset(self):
        return self.find_msvc_toolset(vs_version=self.get_vs_version())

    def run_msbuild_command(self,
                            project_path,
                            configuration=None,
                            platform=None,
                            target='Rebuild',
                            toolset=None,
                            build_path=None):

        if not os.path.exists(project_path):
            raise RuntimeError(
                "Cannot find any project or solution file at: {}".format(
                    project_path))

        if configuration is None:
            configuration = 'Release' if self.is_release() else 'Debug'
        if platform is None:
            platform = self.get_arch()
        if toolset is None:
            toolset = self.get_current_msvc_toolset()

        commands = [
            'msbuild', project_path,
            '-p:Configuration={}'.format(configuration),
            '-p:Platform={}'.format(platform),
            '-p:PlatformToolset={}'.format(toolset), '-t:{}'.format(target)
        ]

        if build_path is None:
            build_path = self.get_build_path()

        print("Run build command: " + ' '.join(commands))

        ret = self.run_build_command(command=commands, cwd=build_path)
        if ret:
            raise RuntimeError("Error when msbuild command: " +
                               ' '.join(commands))

    def find_artifacts(self, path, recursively=False, types=None):
        files_grabbed = []
        file_types = [
            '*.pdb', '*.dll', '*.lib', '*.a', '*.so', '*.so.*', '*.dylib',
            '*.dylib.*'
        ]
        if types:
            file_types = types
        if recursively == False:
            for files in file_types:
                files_grabbed.extend(glob.glob(os.path.join(path, files)))
            return files_grabbed
        else:
            for files in file_types:
                for root, _, filenames in os.walk(path):
                    for filename in fnmatch.filter(filenames, files):
                        files_grabbed.append(os.path.join(root, filename))
        return files_grabbed

    def copy_binary_artifacts(self,
                              source_path,
                              destination_path,
                              recursively=False):

        files = self.find_artifacts(source_path, recursively)

        for file in files:
            print("Copy file " + str(file))
            helpers.copy_file(file, destination_path)

    def copy_binary_artifacts_from_build(self,
                                         source_path,
                                         destination_path,
                                         recursively=False):

        artifact_types = None
        if self.is_windows():
            if self.is_static():
                artifact_types = ['*.pdb', '*.lib']
            else:
                artifact_types = ['*.pdb', '*.dll', '*.lib']
        elif self.is_darwin():
            if self.is_static():
                artifact_types = ['*.a']
            else:
                artifact_types = ['*.dylib', '*.dylib.*']
        else:
            if self.is_static():
                artifact_types = ['*.a']
            else:
                artifact_types = ['*.so', '*.so.*']

        files = self.find_artifacts(path=source_path,
                                    recursively=recursively,
                                    types=artifact_types)

        for file in files:
            print("Copy file " + str(file))
            helpers.copy_file(file, destination_path)

    def export_binaries(self, build_path=None, recursively=False):
        print("Exporting binary files")

        if build_path is None:
            build_path = self.get_build_path()

        if not os.path.exists(build_path):
            print("Found nothing at {}".format(build_path))
            return

        out_path = self.make_out_path()
        if not os.path.exists(out_path):
            os.makedirs(out_path)

        self.copy_binary_artifacts(build_path, out_path, recursively)

    def prepare_include_export(self, include_path=None):
        if include_path is None:
            include_path = 'include'
        include_dir = self.make_project_path(include_path)
        if not os.path.exists(include_dir):
            os.makedirs(include_dir)
        return include_dir

    def export_headers(self, source_path, include_path=None):
        print("Exporting headers")

        include_dir = self.prepare_include_export(include_path)

        if not os.path.isdir(source_path):
            raise Exception("Error: Can't find directory " + str(source_path))

        print("Copy directory " + str(source_path))
        shutil.copytree(
            source_path,
            os.path.join(include_dir, helpers.directory_basename(source_path)),
            dirs_exist_ok=True,
            symlinks=True)

    def export_file_to_headers(self, file_path, include_path=None):
        print("Exporting header file")

        include_dir = self.prepare_include_export(include_path)

        if not os.path.exists(file_path):
            raise Exception("Error: Can't find header " + str(file_path))

        print("Copy file {}".format(file_path))
        helpers.copy_file(file_path, include_dir)

    def cmake_build(self,
                    source_path=None,
                    build_path=None,
                    targets=None,
                    variant=None,
                    link=None,
                    arch=None,
                    options=None,
                    install_prefix=None,
                    prefix_path=None,
                    env=None):
        if source_path is None:
            source_path = self.get_project_dir()

        if build_path is None:
            build_path = self.get_build_path()

        if not os.path.exists(build_path):
            os.makedirs(build_path)

        if variant is None:
            if self.is_debug():
                variant = 'Debug'
            else:
                variant = 'Release'
        opt_variant = '-DCMAKE_BUILD_TYPE=' + variant

        opt_link = '-DBUILD_SHARED_LIBS='
        if link is not None:
            if link == 'shared':
                opt_link += 'ON'
            elif link == 'static':
                opt_link += 'OFF'
            else:
                raise Exception("Error: Bad argument link=" + str(link))
        elif self.is_static():
            opt_link += 'OFF'
        else:
            opt_link += 'ON'

        opt_arch = ['-A']
        if self.is_x64():
            opt_arch.append('x64')
        else:
            opt_arch.append('x86')

        if not self.is_windows():
            opt_arch = []

        prefix_dir = os.path.join(build_path, 'install')
        if not os.path.exists(prefix_dir):
            os.makedirs(prefix_dir)

        opt_install_prefix = []
        if install_prefix is not None:
            opt_install_prefix += ['-DCMAKE_INSTALL_PREFIX=' + install_prefix]

        opt_prefix_path = []
        if prefix_path is not None:
            opt_prefix_path += ['-DCMAKE_PREFIX_PATH=' + prefix_path]

        opt_options = []
        if options is not None:
            opt_options += options

        cmake_command = ['cmake', source_path] + opt_arch + [
            opt_variant, opt_link
        ] + opt_install_prefix + opt_prefix_path + opt_options

        print("Run CMake command: " + ' '.join(cmake_command))

        ret = self.run_build_command(command=cmake_command, cwd=build_path, env=env)
        if ret:
            raise RuntimeError("Error when running CMake command: " +
                               ' '.join(cmake_command))

        if targets is None:
            targets = []
        else:
            targets = ['--target'] + targets

        cmake_command = ['cmake', '--build', '.', '--config', variant
                         ] + targets
        print("Run build command: " + ' '.join(cmake_command))

        ret = self.run_command(command=cmake_command, cwd=build_path, env=env)
        if ret:
            raise RuntimeError("Error when running CMake command: " +
                               ' '.join(cmake_command))

        if install_prefix is not None:
            cmake_command = ['cmake', '--install']
            print("Run install command: " + ' '.join(cmake_command))

            ret = self.run_command(command=cmake_command, cwd=build_path, env=env)
            if ret:
                raise RuntimeError("Error when running CMake command: " +
                                    ' '.join(cmake_command))

    def save_options(self):
        self.context.env.OPTIONS = json.dumps(self.context.options.__dict__)

    def restore_options_env(self, env):

        options = json.loads(env.OPTIONS)
        if not self.context.options.targets:
            self.context.options.targets = options['targets']
        else:
            options['targets'] = self.context.options.targets

        options['output_file'] = self.context.options.output_file

        if not self.context.options.only_update_dependencies_regex:
            self.context.options.only_update_dependencies_regex = options[
                'only_update_dependencies_regex']
        else:
            options[
                'only_update_dependencies_regex'] = self.context.options.only_update_dependencies_regex

        return options

    def restore_options(self):
        self.context.options.__dict__ = self.restore_options_env(
            self.context.env)

    def ensures_qt_is_installed(self):
        if not self.context.options.qtdir and self.is_linux(
        ) and self.distribution() == 'debian' and self.release() == 'stretch':
            self.requirements_debian_install([
                'qt5-default', 'qtwebengine5-dev', 'libqt5x11extras5-dev',
                'qtbase5-private-dev'
            ])

    def make_android_ndk_path(self, path=None):
        android_ndk_path = self.context.options.android_ndk

        if 'ANDROID_NDK_ROOT' in os.environ and os.environ['ANDROID_NDK_ROOT']:
            android_ndk_path = os.environ['ANDROID_NDK_ROOT']

        if path is not None:
            android_ndk_path = os.path.join(android_ndk_path, path)

        return android_ndk_path

    def has_android_ndk_path(self):
        return self.make_android_ndk_path() != ''

    def check_android_ndk_path(self):
        path = self.make_android_ndk_path()
        assert path != ''
        assert os.path.exists(path)

    def make_android_ndk_host(self):
        return 'linux-x86_64'

    def make_android_compiler_path(self):
        default_arch = 'arm64_v8a'
        default_compiler = 'clang++'

        android_ndk_path = self.make_android_ndk_path()

        anrdoid_current_host = self.make_android_ndk_host()
        path_to_android_compiler_base = os.path.join(
            'toolchains/llvm/prebuilt/', anrdoid_current_host, 'bin')

        android_arch = self.make_android_arch()
        android_ndk_platform = self.make_android_ndk_platform()

        if android_arch == default_arch:
            path_to_android_compiler = os.path.join(
                path_to_android_compiler_base, default_compiler)
        else:
            path_to_android_compiler = os.path.join(
                path_to_android_compiler_base, android_arch +
                'linux-androideabi' + android_ndk_platform + '-clang++')

        path_to_android_compiler = os.path.join(android_ndk_path,
                                                path_to_android_compiler)

        return path_to_android_compiler

    def make_android_sdk_path(self):
        android_sdk_path = self.context.options.android_sdk

        if 'ANDROID_HOME' in os.environ and os.environ['ANDROID_HOME']:
            android_sdk_path = os.environ['ANDROID_HOME']

        if 'ANDROID_SDK_ROOT' in os.environ and os.environ['ANDROID_SDK_ROOT']:
            android_sdk_path = os.environ['ANDROID_SDK_ROOT']

        return android_sdk_path

    def has_android_sdk_path(self):
        return self.make_android_sdk_path() != ''

    def check_android_sdk_path(self):
        path = self.make_android_sdk_path()
        assert path != ''
        assert os.path.exists(path)

    def make_android_jdk_path(self):
        android_jdk_path = self.context.options.android_jdk

        if 'JAVA_HOME' in os.environ and os.environ['JAVA_HOME']:
            android_jdk_path = os.environ['JAVA_HOME']

        return android_jdk_path

    def has_android_jdk_path(self):
        return self.make_android_jdk_path() != ''

    def check_android_jdk_path(self):
        path = self.make_android_jdk_path()
        assert path != ''
        assert os.path.exists(path)

    def make_android_ndk_platform(self):
        android_ndk_platform = self.context.options.android_ndk_platform

        if 'ANDROID_NDK_PLATFORM' in os.environ and os.environ[
                'ANDROID_NDK_PLATFORM']:
            android_ndk_platform = os.environ['ANDROID_NDK_PLATFORM']

        return android_ndk_platform

    def has_android_ndk_platform(self):
        return self.make_android_ndk_platform() != ''

    def check_android_ndk_platform(self):
        android_ndk_platform = self.make_android_ndk_platform()
        assert android_ndk_platform != ''
        assert helpers.RepresentsInt(android_ndk_platform)

    def make_android_sdk_platform(self):
        android_sdk_platform = self.context.options.android_sdk_platform

        if 'ANDROID_SDK_PLATFORM' in os.environ and os.environ[
                'ANDROID_SDK_PLATFORM']:
            android_sdk_platform = os.environ['ANDROID_SDK_PLATFORM']

        return android_sdk_platform

    def has_android_sdk_platform(self):
        return self.make_android_sdk_platform() != ''

    def check_android_sdk_platform(self):
        android_sdk_platform = self.make_android_sdk_platform()
        assert android_sdk_platform != ''
        assert helpers.RepresentsInt(android_sdk_platform)

    def make_android_sdk_build_tools_version(self):
        return "28.0.3"

    def make_android_arch(self):
        android_arch = self.context.options.android_arch

        if 'ANDROID_ARCH' in os.environ and os.environ['ANDROID_ARCH']:
            android_arch = os.environ['ANDROID_ARCH']

        return android_arch

    def has_android_arch(self):
        return self.make_android_arch() != ''

    def check_android_arch(self):
        android_arch = self.make_android_arch()
        assert android_arch != ''

    def configure_compiler(self):

        if self.is_android():
            self.check_android_ndk_platform()
            self.check_android_arch()
            self.check_android_ndk_path()

            path_to_android_compiler = self.make_android_compiler_path()
            assert os.path.exists(path_to_android_compiler)
            self.context.env.CXX = path_to_android_compiler

        if 'CXX' in os.environ and os.environ['CXX']:  # Pull in the compiler
            self.context.env.CXX = os.environ['CXX']  # override default

    def make_android_toolchain_target(self):
        return "aarch64-none-linux-android"

    def make_android_toolchain_version(self):
        return "4.9"

    def make_android_toolchain_target_directory(self):
        return "aarch64-linux-android-" + self.make_android_toolchain_version()

    def make_android_toolchain_include_directory(self):
        return "aarch64-linux-android"

    def make_android_toolchain_path(self):

        toolchain_target_arch_directory = self.make_android_toolchain_target_directory(
        )
        toolchain_host_directory = self.make_android_ndk_host()
        toolchain_path = os.path.join("toolchains",
                                      toolchain_target_arch_directory,
                                      "prebuilt", toolchain_host_directory)

        return self.make_android_ndk_path(toolchain_path)

    def make_android_platform_arch_name(self):
        return "arch-arm64"

    def make_android_sysroot_path_for_linker(self):
        return self.make_android_ndk_path(
            os.path.join("platforms",
                         "android-" + self.make_android_ndk_platform(),
                         self.make_android_platform_arch_name()))

    def append_android_cxxflags(self):
        if not self.is_android():
            return

        flags = [
            "-D__ANDROID_API__=" + self.make_android_ndk_platform(),
            "-target",
            self.make_android_toolchain_target(),
            "-gcc-toolchain",
            self.make_android_toolchain_path(),
            "-DANDROID_HAS_WSTRING",
            "--sysroot=" + self.make_android_ndk_path("sysroot"),
            "-isystem",
            self.make_android_ndk_path(
                "sysroot/usr/include/" +
                self.make_android_toolchain_include_directory()),
            "-isystem",
            self.make_android_ndk_path("sources/cxx-stl/llvm-libc++/include"),
            "-isystem",
            self.make_android_ndk_path("sources/android/support/include"),
            "-isystem",
            self.make_android_ndk_path(
                "sources/cxx-stl/llvm-libc++abi/include"),
            "-fstack-protector-strong",
            "-DANDROID",
        ]

        if self.project.qt and os.path.exists(self.context.options.qtdir):
            flags += [
                "-I" + os.path.join(self.context.options.qtdir,
                                    "mkspecs/android-clang")
            ]

        self.context.env.CXXFLAGS += flags
        self.context.env.CFLAGS += flags

    def append_android_linkflags(self):
        if not self.is_android():
            return

        self.context.env.LINKFLAGS += [
            "-D__ANDROID_API__=" + self.make_android_ndk_platform(), "-target",
            self.make_android_toolchain_target(), "-gcc-toolchain",
            self.make_android_toolchain_path(), "-Wl,--exclude-libs,libgcc.a",
            "--sysroot=" + self.make_android_sysroot_path_for_linker()
        ]

    def make_android_arch_hyphens(self):
        return self.make_android_arch().replace('_', '-')

    def append_android_ldflags(self):
        if not self.is_android():
            return

        android_libs_path = self.make_android_ndk_path(
            "sources/cxx-stl/llvm-libc++/libs/" +
            self.make_android_arch_hyphens())
        self.context.env.LDFLAGS += [
            "-L" + android_libs_path,
            os.path.join(android_libs_path,
                         "libc++.so." + self.make_android_ndk_platform()),
        ]

    def package_android(self, package_build_context):
        targets = list()

        self.check_android_sdk_path()
        self.check_android_sdk_platform()
        self.check_android_jdk_path()
        assert self.context.options.qtdir != '' and os.path.exists(
            self.context.options.qtdir)

        print("Check package's targets")

        depends = package_build_context.configuration.packages

        assert len(targets) == 1

        target_binaries = []
        for target in targets:
            target_binaries += self.make_artifacts_from_context(
                package_build_context.configuration, target)

        target_binary = None
        for target in target_binaries:
            if str(target).endswith('.so') or str(target).endswith(
                    '.dll') or str(target).endswith('.dylib'):
                target_binary = os.path.join(self.make_out_path(), target)
        assert target_binary is not None

        target_dependencies = []
        for target in self.get_targets_to_process(
                package_build_context.configuration.use):
            for target_name in self.make_artifacts_from_context(
                    package_build_context.configuration, target):
                if str(target_name).endswith('.so') or str(
                        target_name).endswith('.dll') or str(
                            target_name).endswith('.dylib'):
                    target_dependencies.append(
                        os.path.join(self.make_out_path(), target_name))

        for dep_name in package_build_context.configuration.deps:
            for dep in self.project.deps:
                if dep_name == dep.name:
                    if str(dep_name).endswith('.so') or str(dep_name).endswith(
                            '.dll') or str(dep_name).endswith('.dylib'):
                        target_dependencies.append(
                            os.path.join(
                                self.make_out_path(),
                                self.make_artifacts_from_context(
                                    package_build_context.configuration, dep)))

        # Don't run this script as root

        print("Gather package metadata")
        package_name = package_build_context.package.name
        package_description = package_build_context.package.description

        print("Clean-up")
        package_directory = self.make_output_path('dist')
        helpers.remove_tree(self, package_directory)

        # Strip binaries, libraries, archives

        print("Prepare package")
        package_directory = helpers.make_directory(
            os.path.join(package_directory, package_name))
        bin_directory = helpers.make_directory(
            package_directory,
            os.path.join('libs', self.make_android_arch_hyphens()))

        print("Copying " + str(self.make_out_path()) + " to " +
              str(bin_directory))
        helpers.copy_file(target_binary, bin_directory)
        for target in target_dependencies:
            helpers.copy_file(target, bin_directory)

        android_package_file = self.make_build_path('android-package.json')
        print("Create android package file" + str(android_package_file))

        #target_binary = os.path.realpath(os.path.join(bin_directory, os.path.basename(target_binary)))
        target_binary = os.path.realpath(target_binary)
        extra_libs = []
        for target in target_dependencies:
            #extra_libs.append(os.path.realpath(os.path.join(bin_directory, os.path.basename(target))))
            extra_libs.append(os.path.realpath(target))

        qt_path = str(self.context.options.qtdir)
        ndk_path = str(self.make_android_ndk_path())
        sdk_path = str(self.make_android_sdk_path())

        def remove_last_slash(string):
            if string[-1] == '/':
                string = string[:-1]
            return string

        qt_path = remove_last_slash(qt_path)
        ndk_path = remove_last_slash(ndk_path)
        sdk_path = remove_last_slash(sdk_path)

        data = OrderedDict({
            "description": package_description,  # One sentence description
            "qt": qt_path,
            "sdk": sdk_path,
            "sdkBuildToolsRevision": self.
            make_android_sdk_build_tools_version(),
            "ndk": ndk_path,
            "toolchain-prefix": "llvm",
            "tool-prefix": "llvm",
            "toolchain-version": self.make_android_toolchain_version(),
            "ndk-host": self.make_android_ndk_host(),
            "target-architecture": self.make_android_arch_hyphens(),
            "android-extra-libs": ",".join(extra_libs),
            "stdcpp-path": self.make_android_ndk_path(
                "sources/cxx-stl/llvm-libc++/libs/" +
                self.make_android_arch_hyphens() + "/libc++_shared.so"),
            "useLLVM": True,
            "application-binary": target_binary
        })

        qml_enabled = False
        if qml_enabled:
            qml_path = ""
            qml_path = remove_last_slash(qml_path)
            data["qml-root-path"] = qml_path

        with open(android_package_file, 'w') as outfile:
            json.dump(data, outfile, indent=4, sort_keys=True)

        print("Build package")
        command = [
            os.path.join(self.context.options.qtdir, 'bin/androiddeployqt'),
            '--input', android_package_file, '--output', package_directory,
            '--android-platform',
            'android-' + self.make_android_sdk_platform(), '--jdk',
            self.make_android_jdk_path(), '--gradle'
        ]

        if self.is_release() and False:
            command += ["--sign", "", "--storepass", "", "--keypass", ""]
        helpers.run_task(command, cwd=self.get_output_path())

    def make_basic_dependency_repo_path(self, name, url, branch='main'):
        dependency = Dependency(name=name,
                                targets=None,
                                repository=url,
                                version=branch)
        dependency.resolved_version = branch
        dependency.update_cache_dir(context=self)
        repo_path = os.path.join(
            dependency.cache_dir.location,
            helpers.generate_recipe_id(dependency.repository))
        return repo_path

    def clone_repository(self, path, url, branch):
        if not os.path.exists(path):
            os.makedirs(path)
            helpers.run_task(['git', 'clone', '--', url, '.'], cwd=path)
        else:
            helpers.run_task(['git', 'fetch', 'origin'], cwd=path)

        helpers.run_task(['git', 'reset', '--hard', 'origin/' + branch],
                         cwd=path)

    def clone_master_dependencies_repository(self, url):
        branch_version = 'main'
        repo_path = self.make_basic_dependency_repo_path(name='master',
                                                         url=url,
                                                         branch=branch_version)

        if not self.deps_resolve:
            return repo_path

        self.clone_repository(path=repo_path, url=url, branch=branch_version)

        return repo_path

    def clone_recipes_repository(self, url):
        branch_version = 'main'
        repo_path = self.make_basic_dependency_repo_path(name='recipes',
                                                         url=url,
                                                         branch=branch_version)

        if self.context.options.no_recipes_repositories_fetch or not self.deps_resolve:
            return repo_path

        self.clone_repository(path=repo_path, url=url, branch=branch_version)

        return repo_path

    def load_recipes_repositories(self):
        recipe_repositories_env_key = 'GOLEM_RECIPES_REPOSITORIES'

        if recipe_repositories_env_key in os.environ:
            recipes_repositories = os.environ[recipe_repositories_env_key].split(
                '|')
        else:
            # Default recipes repository
            recipes_repositories = ['https://github.com/GolemCpp/recipes.git']

        repos_paths = []
        for url in recipes_repositories:
            repo_path = self.clone_recipes_repository(url=url)
            repos_paths.append(repo_path)

        return repos_paths

    def load_recipe(self):
        recipe_id = self.context.options.recipe

        recipes_repos_paths = self.load_recipes_repositories()

        if not recipe_id and self.project is None:
            recipe_url = self.load_git_remote_origin_url()
            if not recipe_url:
                return
            recipe_id = helpers.generate_recipe_id(recipe_url)

        if not recipe_id:
            return

        found_recipe_dir = None
        for repo in recipes_repos_paths:
            directory = os.path.join(repo, recipe_id)
            if os.path.exists(directory):
                found_recipe_dir = directory

        if not found_recipe_dir:
            raise RuntimeError(
                "ERROR: no project file found ('golem.json' or 'golemfile.py')"
            )

        self.load_project(found_recipe_dir)

        if self.project is None:
            raise RuntimeError(
                "ERROR: unable to use recipe from {}".format(found_recipe_dir))

    def load_git_remote_origin_url(self):
        if self.repository is not None:
            return self.repository
        self.repository = ''
        try:
            remote_url = subprocess.check_output(
                ['git', 'config', '--get', 'remote.origin.url'],
                cwd=self.get_project_dir()).decode(sys.stdout.encoding)
            remote_url = remote_url.split('\n')
            self.repository = remote_url[0] if remote_url else None
        except Exception:
            pass
        return self.repository

    def msvc_vcvars_cmd(self):
        cmd = [
            'cmd', '/c', 'vswhere', '-latest', '-products', '*', '-property',
            'installationPath'
        ]
        print(' '.join(cmd))
        ret = subprocess.Popen(
            cmd,
            cwd='C:\\Program Files (x86)\\Microsoft Visual Studio\\Installer',
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        out, _ = ret.communicate()
        if ret.returncode:
            print("ERROR: " + ' '.join(cmd))
            return -1
        lines = out.decode(sys.stdout.encoding).splitlines()
        if not lines[0]:
            return 1
        msvc_path = lines[0]
        print(msvc_path)

        vcvars = msvc_path + '\\VC\\Auxiliary\\Build\\vcvarsall.bat'
        call_msvc = 'call "' + vcvars + '" ' + \
            self.context.env['MSVC_TARGETS'][0] + ' && '
        print(call_msvc)
        return call_msvc

    def is_qt_enabled(self, config):
        return self.is_qt5_used(config) or self.is_qt6_used(config) or 'qt5' in config.wfeatures

    def is_qt5_used(self, config):
        return any([feature.startswith("QT5") for feature in config.features])

    def is_qt6_used(self, config):
        return any([feature.startswith("QT6") for feature in config.features])

    def configure(self):

        self.cache_conf = self.make_cache_conf()

        self.load_recipe()

        tasks_and_targets = self.get_tasks_and_targets_to_process()

        is_qt6_used = False

        for task, _ in tasks_and_targets:
            if (self.is_qt_enabled(config=task)):
                self.project.enable_qt()
            if (self.is_qt6_used(config=task)):
                is_qt6_used = True

        # features list
        features_to_load = ['compiler_c', 'compiler_cxx']

        # qt check
        if self.project.qt:
            self.ensures_qt_is_installed()
            features_to_load.append('qt5')
            self.context.want_qt6 = is_qt6_used
            if os.path.exists(self.project.qtdir):
                self.context.options.qtdir = self.project.qtdir

        self.context.setenv('main')
        self.configure_compiler()
        if self.is_windows():
            self.context.env.MSVC_TARGETS = [
                'x86' if self.get_arch() == 'x86' else 'x64'
            ]
        self.context.load(features_to_load)
        self.save_options()

        if self.context.options.force_version:
            self.version.force_version(self.context.options.force_version)

    def build_path(self, dep=None):
        if self.is_windows():
            return self.osname()[:1] + ('64' if self.get_arch(
            ) == 'x64' else '32') + self.compiler_min() + self.runtime_min(
                dep) + self.link_min(dep) + self.variant_min(dep)
        else:
            return self.osname() + '-' + self.arch_min() + '-' + self.compiler(
            ) + '-' + self.runtime_min(dep) + '-' + self.link_min(
                dep) + '-' + self.variant_min(dep)

    def build_path_build(self, dep=None):
        if self.is_windows():
            return self.build_path(dep) + 'b'
        else:
            return self.build_path(dep) + '-build'

    def find_dependency(self, dep_name):
        for dep in self.project.deps:
            if dep_name == dep.name:
                return dep

    def find_dependency_includes(self, dep_name):
        dep_include = []
        cache_conf = self.cache_conf
        for dep in self.project.deps:
            if dep_name == dep.name:
                cache_dir = self.find_dep_cache_dir(dep, cache_conf)
                dep_include.append(
                    self.get_dep_include_location(dep, cache_dir))
        return dep_include

    def find_dependency_libraries(self, dep_name):
        dep_lib_paths = []
        cache_conf = self.cache_conf
        for dep in self.project.deps:
            if dep_name == dep.name:
                cache_dir = self.find_dep_cache_dir(dep, cache_conf)
                dep_lib_paths.append(
                    self.get_dep_artifact_location(dep, cache_dir))
        return dep_lib_paths

    def find_dependency_artifacts_dev(self, dep_name, target_name=None):
        results = []
        for dep in self.project.deps:
            if dep_name == dep.name:
                dep_config = self.read_dep_configs(dep=dep,
                                                   cache_dir=dep.cache_dir,
                                                   target_name=target_name)
                results.append(dep_config.artifacts_dev)

        if not results:
            return None

        return results[0]

    def find_dependency_libraries_files(self, dep_name, target_name=None):
        lib_paths = []
        artifacts_dev = self.find_dependency_artifacts_dev(
            dep_name=dep_name, target_name=target_name)
        if not artifacts_dev:
            raise RuntimeError(
                "Cannot find any files for target {} from dependency {}".
                format(dep_name, target_name))
        file_types = ['.lib', '.a', '.so', '.dylib']
        for artifact in artifacts_dev:
            _, extension = os.path.splitext(artifact)
            if extension in file_types:
                lib_paths.append(artifact)
        return lib_paths

    def build_dependency(self, dep_name):
        config = Configuration()
        config.deps = [dep_name]
        self.recursively_link_dependencies(config)
        return config

    def find_dep_artifact_location(self, dep_name):
        cache_dir = self.cache_conf
        for dep in self.project.deps:
            if dep_name == dep.name:
                return self.get_dep_artifact_location(dep, cache_dir)
        return None

    def build(self):
        vscode_dir = self.get_vscode_path()
        vscode_compiler_commands_path = self.make_vscode_path('compile_commands.json')

        if self.context.options.vscode:
            if not os.path.exists(vscode_dir):
                helpers.make_directory(vscode_dir)
            if os.path.exists(vscode_compiler_commands_path):
                os.remove(vscode_compiler_commands_path)
            self.initialize_compiler_commands()
            self.initialize_vscode_configs()

        clangd_dir = self.get_clangd_path()
        clangd_compiler_commands_path = self.make_clangd_path('compile_commands.json')

        if self.context.options.clangd:
            if not os.path.exists(clangd_dir):
                helpers.make_directory(clangd_dir)
            if os.path.exists(clangd_compiler_commands_path):
                os.remove(clangd_compiler_commands_path)
            self.initialize_compiler_commands()
            self.initialize_clangd_configs()

        compile_commands_dir = self.get_compile_commands_path()
        compile_commands_compiler_commands_path = self.make_compile_commands_path('compile_commands.json')

        if self.context.options.compile_commands:
            if not os.path.exists(compile_commands_dir):
                helpers.make_directory(compile_commands_dir)
            if os.path.exists(compile_commands_compiler_commands_path):
                os.remove(compile_commands_compiler_commands_path)
            self.initialize_compiler_commands()
            self.initialize_compile_commands_configs()

        self.call_build_target(self.build_target, build_recursively=True)

        if self.context.options.vscode:
            self.save_compiler_commands(vscode_compiler_commands_path)
            self.generate_vscode_config(vscode_compiler_commands_path)

        if self.context.options.clangd:
            self.save_compiler_commands(clangd_compiler_commands_path)
            self.generate_clangd_config(clangd_compiler_commands_path)

        if self.context.options.compile_commands:
            self.save_compiler_commands(compile_commands_compiler_commands_path)
            self.generate_compile_commands_config(compile_commands_compiler_commands_path)

        for targetname in self.context.options.targets.split(','):
            if targetname and not targetname in [
                    target.name for target in self.project.targets
            ]:
                if self.is_windows():
                    self.context(rule="type nul >> ${TGT}", target=targetname)
                else:
                    self.context(rule="touch ${TGT}", target=targetname)

    def get_asked_exports(self):
        return self.context.options.targets.split(
            ',') if self.context.options.targets else [
                target.name for target in self.project.exports
            ]

    def find_dep(self, name):
        found_dep = None
        for dep in self.project.deps:
            if dep.name == name:
                found_dep = dep
                break
        return found_dep

    def find_dep_cache_include(self, dep):
        cache_dir = self.find_dep_cache_dir(dep, self.cache_conf)
        return self.get_dep_include_location(dep, cache_dir)

    def merge_export_config_against_build_condition(self,
                                                    export,
                                                    exporting=False):
        found_build_target = None
        for build_target in self.project.targets:
            if build_target.name == export.name:
                found_build_target = build_target
                break
        return export.merge_configs(self,
                                    condition=found_build_target,
                                    exporting=exporting)

    def export(self):
        targets = self.get_asked_exports()
        for export in self.project.exports:
            if export.name in targets:

                config = self.merge_export_config_against_build_condition(
                    export, exporting=True)

                outpath = self.context.options.export

                if not outpath:
                    outpath = self.make_output_path('export')

                if not os.path.exists(outpath):
                    os.makedirs(outpath)

                includes = config.includes

                outpath_include = os.path.join(outpath, 'include')
                if not os.path.exists(outpath_include):
                    os.makedirs(outpath_include)

                for include in includes:
                    shutil.copytree(
                        self.make_project_path(include),
                        outpath_include,
                        dirs_exist_ok=True)

                # NOTE: Disable export of libs in a separate directory
                #outpath_lib = os.path.join(outpath, self.build_path())
                #if not os.path.exists(outpath_lib):
                #    os.makedirs(outpath_lib)

                #out_path = self.make_out_path()
                #if os.path.exists(out_path):
                #    copy_tree(self.make_out_path(), outpath_lib)

    def merge_local_dependent_used_target_configs(self,
                                                  config,
                                                  exporting=False):
        for use_name in config.use:
            for export in self.project.exports:
                if use_name == export.name:
                    export_config = self.merge_export_config_against_build_condition(
                        export)
                    config.merge(self, [export_config], exporting=True)

    def resolve_local_configs(self, targets):
        configs = dict()
        for target in targets:

            is_exporting = target.export and self.context.options.export

            config = target.merge_configs(self, exporting=is_exporting)

            self.merge_local_dependent_used_target_configs(
                config, exporting=is_exporting)

            configs[target.name] = config
        return configs

    def resolve_target_deps(self, target):
        configs = self.resolve_local_configs([target])
        config = configs[target.name]

        def callback(config, dep):
            dep.configure(self, config)

        self.recursively_apply_to_deps(config, callback)

    def resolve_configs_recursively(self, targets):
        configs = self.resolve_local_configs(targets)
        for target in targets:
            config = configs[target.name]

            def callback(config, dep):
                dep.configure(self, config)

            self.recursively_apply_to_deps(config, callback)

            is_exporting = target.export and self.context.options.export

            if is_exporting:
                for project_target in self.project.targets:
                    if target.name == project_target.name:
                        self.resolve_target_deps(project_target)
        return configs

    def build_local_dependencies(self, targets):
        dependencies = dict()
        configs = self.resolve_local_configs(targets)
        for target in targets:
            config = configs[target.name]

            def callback(config, dep):
                dep.build(self, config)
                if target.name not in dependencies:
                    dependencies[target.name] = list()
                dependencies[target.name].append(dep)

            self.recursively_apply_to_deps(config, callback)

        return dependencies

    def resolve_global_config(self, targets):
        configs = self.resolve_configs_recursively(targets)

        master_config = Configuration()
        for _, config in list(configs.items()):
            master_config.merge(self, [config], exporting=True)
        return master_config

    def get_targets_from_task(self, task):
        config = task.merge_configs(self)
        if not config.targets and task.export and self.context.options.export:
            related_build_task = self.find_related_build_task(task=task)
            if related_build_task:
                related_build_task_config = related_build_task.merge_configs(
                    self)
                config.targets = related_build_task_config.targets.copy()
        return self.list_target_names_from_context(config=config, target=task)

    def resolve_asked_targets(self, tasks_source=None):
        if tasks_source is None:
            tasks_source = self.get_targets_or_exports()

        # Task names are virtual targets (referring to 0,n targets)

        targets = []
        for task in tasks_source:
            targets += [task.name]

        if not self.context.options.targets:
            return targets

        # To check given targets are valid we add all possible targets to the list

        for task in tasks_source:
            targets += self.get_targets_from_task(task)

        targets = helpers.filter_unique(targets)

        # Check all targets given in options exist
        # (Special case for header_only targets)

        asked_targets = self.context.options.targets.split(',')
        for asked_target in asked_targets:
            found_target = asked_target not in targets
            is_header_only_target = asked_target in [
                t.name for t in self.project.exports if t.header_only
            ]
            if found_target and not is_header_only_target:
                raise RuntimeError(
                    "Cannot find any target named {} between {}".format(
                        asked_target, targets))

        return asked_targets

    def get_task_from_target(self, target, tasks_source=None):
        if tasks_source is None:
            tasks_source = self.get_targets_or_exports()

        tasks = []
        for task in tasks_source:
            if target == task.name:
                tasks.append(task)
        if not tasks:
            for task in tasks_source:
                if target in self.get_targets_from_task(task):
                    tasks.append(task)
        if len(tasks) > 1:
            raise RuntimeError(
                "Ambiguous target name {} between tasks {}".format(
                    target, [task.name for task in tasks]))

        if not tasks:
            tasks = [
                t for t in self.project.exports
                if (t.header_only and target == t.name)
            ]

        if len(tasks) > 1:
            raise RuntimeError(
                "Ambiguous target name {} between tasks {}".format(
                    target, [task.name for task in tasks]))

        if not tasks:
            raise RuntimeError("Can't find target name {}".format(target))

        return tasks[0]

    def get_tasks_from_targets(self, targets, tasks_source=None):
        if tasks_source is None:
            tasks_source = self.get_targets_or_exports()

        result_tasks = dict()
        result_targets = dict()
        for target in targets:
            task = self.get_task_from_target(target=target,
                                             tasks_source=tasks_source)

            if task.name not in result_targets:
                result_targets[task.name] = []

            result_tasks[task.name] = task
            if target != task.name:
                result_targets[task.name].append(target)

        result = []
        for key, value in result_targets.items():
            current_task = result_tasks[key]
            current_targets = value
            result.append((current_task, current_targets))
        return result

    def get_tasks_from_names(self, names, tasks_source=None):
        if tasks_source is None:
            tasks_source = self.get_targets_or_exports()

        return [task for task in tasks_source if task.name in names]

    def find_related_build_task(self, task):
        build_tasks = []
        build_tasks_done = []
        for build_task in self.project.targets:
            if build_task.name == task.name:
                build_tasks.append(build_task)
                build_tasks_done.append(build_task.name)
        if len(build_tasks_done) > 1:
            raise RuntimeError("Ambiguous build task {}".format(task.name))
        return build_tasks[0] if build_tasks else None

    def process_internal_deps(self,
                              config,
                              build_method=None,
                              build_recursively=False):
        tasks_use = self.get_tasks_from_names(
            names=config.use, tasks_source=self.project.exports)
        for export_task in tasks_use:
            export_task_config, _ = self.process_export_task(
                task=export_task,
                targets=None,
                build_method=build_method,
                build_recursively=build_recursively)
            export_task_config.type = []
            export_task_config.targets = []
            config.merge(context=self, configs=[export_task_config])

    def make_outpath(self):
        if not self.context.options.export:
            return ''
        outpath = self.context.options.export
        if not os.path.exists(outpath):
            os.makedirs(outpath)
        return outpath

    def make_outpath_lib(self):
        if not self.context.options.export:
            return ''
        outpath_lib = self.make_out_path()

        if not os.path.exists(outpath_lib):
            os.makedirs(outpath_lib)
        return outpath_lib

    def make_outpath_conf(self):
        if not self.context.options.export:
            return ''
        outpath = self.context.options.export
        outpath_conf = os.path.join(outpath, self.build_path(), 'conf')
        if not os.path.exists(outpath_conf):
            os.makedirs(outpath_conf)
        return outpath_conf

    def make_target_artifact(self, config, decorated_target, out_path=None):
        decorated_target_path = os.path.dirname(decorated_target)
        decorated_target_base = os.path.basename(decorated_target)

        if out_path is not None:
            target_path = os.path.join(out_path, decorated_target_path)
        else:
            target_path = decorated_target_path

        if self.is_windows():
            target_artifact = '{}.lib'.format(decorated_target_base)
        elif self.is_darwin():
            if self.is_config_shared(config):
                target_artifact = 'lib{}.dylib'.format(decorated_target_base)
            else:
                target_artifact = 'lib{}.a'.format(decorated_target_base)
        else:
            if self.is_config_shared(config):
                target_artifact = 'lib{}.so'.format(decorated_target_base)
            else:
                target_artifact = 'lib{}.a'.format(decorated_target_base)
        target_artifact_path = os.path.join(target_path, target_artifact)

        return target_artifact_path, target_path, target_artifact

    def update_export_config_from_build_config(self, export_config,
                                               build_config):

        out_path = self.make_out_path()

        export_config.targets = build_config.targets.copy()

        if build_config.header_only:
            export_config.header_only = True

        if not export_config.type:
            export_config.type = build_config.type.copy()

        if not export_config.artifacts_generators and build_config.artifacts_generators:
            export_config.artifacts_generators = build_config.artifacts_generators.copy(
            )

        if not export_config.target_decorators and build_config.target_decorators:
            export_config.target_decorators = build_config.target_decorators.copy(
            )

        target_names = export_config.targets.copy()
        model_config = export_config.copy()
        export_target_configs = []

        for target_name in target_names:
            export_target_config = model_config.copy()
            export_target_config.targets = [target_name]

            decorated_target = self.make_decorated_target_from_context(
                export_target_config, target_name)

            target_artifact_path, target_path, _ = self.make_target_artifact(
                config=export_target_config,
                decorated_target=decorated_target,
                out_path=out_path)

            if not export_target_config.header_only:
                export_target_config.rpath_link.append(target_path)

            if self.is_config_shared(export_target_config):
                if target_artifact_path not in export_target_config.lib:
                    export_target_config.lib.append(target_artifact_path)
                if target_path not in export_target_config.libpath:
                    export_target_config.libpath.append(target_path)
            else:
                if target_artifact_path not in export_target_config.stlib:
                    export_target_config.stlib.append(target_artifact_path)
                if target_path not in export_target_config.stlibpath:
                    export_target_config.stlibpath.append(target_path)

            artifacts_dev = self.make_binary_artifact_from_context(
                export_target_config,
                decorated_target,
                enable_dev_libs=True,
                enable_run_libs=True,
                enable_exes=False)

            artifacts_run = self.make_binary_artifact_from_context(
                export_target_config,
                decorated_target,
                enable_dev_libs=False,
                enable_run_libs=True,
                enable_exes=True)

            for artifact in helpers.filter_unique(artifacts_run +
                                                  artifacts_dev):
                export_target_config.artifacts.append(
                    self.create_artifact(
                        path=artifact,
                        location='',
                        type=build_config.type[0],
                        scope='dev' if artifact not in artifacts_run else None,
                        target=target_name,
                        decorated_target=decorated_target))

            export_target_config.artifacts_dev = helpers.filter_unique(
                build_config.artifacts_dev +
                export_target_config.artifacts_dev)
            export_target_config.artifacts_run = helpers.filter_unique(
                build_config.artifacts_run +
                export_target_config.artifacts_run)
            export_target_config.rpath_link = helpers.filter_unique(
                build_config.rpath_link + export_target_config.rpath_link)
            export_target_config.packages = helpers.filter_unique(
                build_config.packages + export_target_config.packages)
            export_target_config.packages_dev = helpers.filter_unique(
                build_config.packages_dev + export_target_config.packages_dev)
            export_target_config.licenses = helpers.filter_unique(
                build_config.licenses + export_target_config.licenses)
            export_target_config.qmldirs = helpers.filter_unique(
                build_config.qmldirs + export_target_config.qmldirs)
            export_target_config.artifacts_dev = helpers.filter_unique(
                artifacts_dev + export_target_config.artifacts_dev)
            export_target_config.artifacts_run = helpers.filter_unique(
                artifacts_run + export_target_config.artifacts_run)
            export_target_config.artifacts = helpers.filter_unique(
                build_config.artifacts + export_target_config.artifacts)
            export_target_config.wfeatures = helpers.filter_unique(
                build_config.wfeatures + export_target_config.wfeatures)

            export_config.merge(context=self, configs=[export_target_config])
            export_target_configs.append(export_target_config)

        return export_config, export_target_configs

    def process_external_deps(self, config):
        def callback(config, dep):
            if not self.deps_build:
                dep.configure(self, config)
            else:
                dep.build(self, config)

        self.recursively_apply_to_deps(config, callback)

    def create_artifact(self,
                        path,
                        location,
                        type,
                        scope=None,
                        target=None,
                        decorated_target=None):
        repository = self.load_git_remote_origin_url()

        return Artifact(
            path=path,
            location=location,
            type=type,
            scope=scope,
            repository=repository,
            target=target,
            decorated_target=decorated_target,
            resolved_version=self.context.options.force_version
            if self.context.options.force_version else self.version.gitlong,
            resolved_hash=self.version.githash)

    def generate_configuration(self, task, targets):
        config = task.merge_configs(self)
        static_configs = self.project.read_configurations(self)
        config.merge(context=self, configs=static_configs)
        config.targets = self.get_targets_from_task(task)

        if task.templates:
            for template in task.templates:
                if template.target:
                    config.artifacts.append(
                        self.create_artifact(path=template.target,
                                             location='',
                                             type='file'))

        for license_path in config.licenses:
            license_artifact = self.create_artifact(path=license_path,
                                                    location='',
                                                    type='license')
            if license_artifact not in config.artifacts:
                config.artifacts.append(license_artifact)

        return config

    def process_export_task(self,
                            task,
                            targets=None,
                            build_method=None,
                            build_recursively=False):
        config = self.generate_configuration(task=task, targets=targets)

        config_targets = []

        related_build_task = self.find_related_build_task(task=task)

        if related_build_task:
            required_targets = targets if targets else config.targets
            related_build_config = self.process_build_task(
                task=related_build_task,
                targets=required_targets,
                build_method=build_method,
                build_recursively=build_recursively)

            config, config_targets = self.update_export_config_from_build_config(
                export_config=config, build_config=related_build_config)

        for c in [config] + config_targets:
            self.process_internal_deps(
                config=c,
                build_method=build_method if build_recursively else None,
                build_recursively=build_recursively)

        for c in [config] + config_targets:
            self.process_external_deps(config=c)

        return config, config_targets

    def process_build_task(self,
                           task,
                           targets=None,
                           build_method=None,
                           build_recursively=False):
        config = self.generate_configuration(task=task, targets=targets)

        self.process_internal_deps(
            config=config,
            build_method=build_method if build_recursively else None,
            build_recursively=build_recursively)

        self.process_external_deps(config=config)

        if build_method and task.name not in self.built_tasks:
            self.built_tasks.append(task.name)
            asked_targets = targets if targets else config.targets
            build_method(task=task, targets=asked_targets, config=config)

        return config

    def iterate_over_task(self,
                          task,
                          targets=None,
                          build_method=None,
                          build_recursively=False):
        if task.export:
            if task.args is not None:
                config = self.generate_configuration(task=task,
                                                     targets=targets)
                targets = helpers.filter_unique(
                    helpers.parameter_to_list(task.args['target']))
                for target in targets:
                    artifact_file = self.create_artifact(path=target,
                                                         location='',
                                                         type='file')
                    if artifact_file not in config.artifacts:
                        config.artifacts.append(artifact_file)
                return config, []
            else:
                return self.process_export_task(
                    task=task,
                    targets=targets,
                    build_method=build_method,
                    build_recursively=build_recursively)
        else:
            return self.process_build_task(
                task=task,
                targets=targets,
                build_method=build_method,
                build_recursively=build_recursively), []

    def make_cache_prefix(self):
        return "${GOLEM_CACHE_DIR}"

    def make_cache_dir_paths(self, paths):
        results = []
        for path in paths:
            new_path = path
            cache_prefix = self.make_cache_prefix()
            if not path.startswith(cache_prefix) and os.path.isabs(new_path):

                common_path = None

                for cache_dir in self.cache_conf.locations:
                    common_path = os.path.commonpath(
                        [path, cache_dir.location])
                    if common_path != cache_dir.location:
                        common_path = None
                    else:
                        break

                if common_path:
                    new_path = os.path.relpath(path=path, start=common_path)
                    new_path = os.path.join(cache_prefix, new_path)

            results.append(new_path)
        return results

    def translate_cache_dir_paths(self, paths):
        results = []
        for path in paths:
            new_path = path
            cache_prefix = self.make_cache_prefix()
            if path.startswith(cache_prefix):

                candidate_path = None

                for cache_dir in self.cache_conf.locations:
                    candidate_path = path.replace(cache_prefix,
                                                  cache_dir.location,
                                                  len(cache_prefix))
                    if not os.path.exists(candidate_path):
                        candidate_path = None
                    else:
                        break

                if candidate_path:
                    new_path = candidate_path
                #else:
                #    raise RuntimeError(
                #        "Can't find path in any cache directories {}".format(
                #            path))

            results.append(new_path)
        return results

    @staticmethod
    def make_absolute_artifacts(artifacts, repo_path, out_path):
        results = []
        for artifact in artifacts:
            if not artifact.location:
                if artifact.type == 'license':
                    artifact.location = repo_path
                else:
                    artifact.location = out_path
            results.append(artifact)
        return results

    def make_config_absolute(self, config, old_out_path, new_out_path):
        def make_absolute_paths(paths, base_path):
            results = []
            for path in paths:
                new_path = path
                cache_prefix = self.make_cache_prefix()
                if not os.path.isabs(new_path) and not path.startswith(
                        cache_prefix):
                    new_path = os.path.join(base_path, new_path)
                results.append(new_path)
            return results

        def replace_paths(paths, old_path, new_path):
            results = []
            for path in paths:
                if path != old_path:
                    results.append(path)
                else:
                    results.append(new_path)
            return results

        config.artifacts_dev = make_absolute_paths(config.artifacts_dev,
                                                   new_out_path)
        config.artifacts_run = make_absolute_paths(config.artifacts_run,
                                                   new_out_path)
        config.licenses = make_absolute_paths(config.licenses,
                                              self.get_project_dir())
        config.qmldirs = make_absolute_paths(config.qmldirs,
                                             self.get_project_dir())
        config.rpath_link = replace_paths(config.rpath_link, old_out_path,
                                          new_out_path)

        config.lib = replace_paths(config.lib, old_out_path, new_out_path)
        config.stlib = replace_paths(config.stlib, old_out_path, new_out_path)
        config.libpath = replace_paths(config.libpath, old_out_path,
                                       new_out_path)
        config.stlibpath = replace_paths(config.stlibpath, old_out_path,
                                         new_out_path)
        config.artifacts = Context.make_absolute_artifacts(
            artifacts=config.artifacts,
            repo_path=self.get_project_dir(),
            out_path=new_out_path)

    def cleanup_old_build_files(self, config):
        if not self.context.options.export:
            return

        export_path = self.make_outpath()
        export_path_build = self.get_dep_build_location(dep=None,
                                                        cache_dir=None,
                                                        base=export_path)

        export_path_lib = self.make_outpath_lib()
        dirs_to_remove = []
        for (dirpath, dirnames, _) in os.walk(export_path_build):
            for dirname in dirnames:
                if not dirname.startswith('bin'):
                    continue
                path = os.path.join(dirpath, dirname)
                path = os.path.realpath(path)
                export_path_lib = os.path.realpath(export_path_lib)
                export_path_lib_basename = os.path.basename(export_path_lib)
                if not dirname.startswith(export_path_lib_basename):
                    dirs_to_remove.append(path)
            break
        for path in dirs_to_remove:
            print("Remove {}".format(path))
            helpers.remove_tree(self, path)

    def write_config_file(self, task, config, target=None):
        export_path = self.make_outpath()
        export_path_lib = self.make_outpath_lib()
        export_path_conf = self.make_outpath_conf()

        config.includes = []
        config.isystem += [os.path.join(export_path, 'include')]

        out_path = self.make_out_path()
        self.make_config_absolute(config=config,
                                  old_out_path=out_path,
                                  new_out_path=export_path_lib)

        config_filename = self.make_dep_artifact_filename(
            task, target, self.load_git_remote_origin_url())

        outpath_target = os.path.join(export_path_conf, config_filename)
        TargetConfigurationFile.save_file(path=outpath_target,
                                          project=self.project,
                                          configuration=config,
                                          context=self)

    def find_corresponding_targets_to_exports(self, exports):
        targets = []
        targets_done = []
        for export in exports:
            for target in self.project.targets:
                if target.name == export.name and target.name not in targets_done:
                    targets.append(target)
                    targets_done.append(target.name)
        return targets

    def resolve_recursively(self):
        task_targets_list = self.get_tasks_and_targets_to_process()
        for task, targets in task_targets_list:
            config, config_targets = self.iterate_over_task(task=task,
                                                            targets=targets)

            if self.context.options.export:
                self.write_config_file(task=task, config=config, target=None)

                for config in config_targets:
                    self.write_config_file(task=task,
                                           config=config,
                                           target=config.targets[0])
            self.cleanup_old_build_files(config=config)

    def get_targets_or_exports(self):
        return self.project.targets if (
            not self.context.options.export
            or self.build_on) else self.project.exports

    def map_name_to_objects(self, names, objects, object_name):
        mapped_objects = []
        for name in names:
            found_objects = [obj for obj in objects if name == obj.name]
            if found_objects:
                mapped_objects.append(found_objects[0])
            else:
                found_objects = [
                    obj for obj in self.project.exports if name == obj.name
                ]
                if not found_objects:
                    raise RuntimeError(
                        "Can't find any {} configuration named \"{}\"".format(
                            object_name, name))

        return mapped_objects

    def get_tasks_and_targets_to_process(self, tasks_source=None):
        targets = self.resolve_asked_targets(tasks_source=tasks_source)
        task_targets_list = self.get_tasks_from_targets(
            targets, tasks_source=tasks_source)
        return task_targets_list

    def get_targets_to_process(self, asked_targets=None, source_targets=None):
        if source_targets is None:
            source_targets = self.get_targets_or_exports()

        if asked_targets is None:
            asked_targets = self.get_asked_targets(
                source_targets=source_targets)

        targets_to_find = asked_targets
        targets_to_process = []

        while True:
            found_targets = self.map_name_to_objects(targets_to_find,
                                                     source_targets, 'target')

            targets_to_find = []
            targets_to_process = found_targets + targets_to_process

            for target in found_targets:
                for target_use in target.use:
                    if target_use not in targets_to_find:
                        already_in_process = False
                        for t in targets_to_process:
                            if target_use == t.name:
                                already_in_process = True
                                break
                        if not already_in_process:
                            targets_to_find.append(target_use)

            if not targets_to_find:
                break

        return targets_to_process

    def get_asked_targets(self, source_targets=None):
        if source_targets is None:
            source_targets = self.get_targets_or_exports()
        return self.context.options.targets.split(
            ',') if self.context.options.targets else [
                target.name for target in source_targets
            ]

    class PackageTaskTargets:
        def __init__(self, export_task, targets):
            self.export_task = export_task
            self.targets = targets
            self.config = None

        def append(self, targets):
            self.targets = helpers.filter_unique(self.targets.copy() +
                                                 targets.copy())

        def generate_config(self, context):
            config, _ = context.iterate_over_task(task=self.export_task,
                                                  targets=self.targets)
            config.artifacts = Context.make_absolute_artifacts(
                artifacts=config.artifacts,
                repo_path=os.path.abspath(context.get_project_dir()),
                out_path=os.path.abspath(context.make_out_path()))
            self.config = config

    class PackageBuildContext:
        def __init__(self, context, package, task, targets):
            self.context = context
            self.package = package
            self.tasks_and_targets = dict()
            self.append(task=task, targets=targets)
            self.configuration = Configuration()
            self.targets_and_configs = dict()

        def append(self, task, targets):
            if task.name not in self.tasks_and_targets:
                self.tasks_and_targets[task.name] = Context.PackageTaskTargets(
                    export_task=self.context.make_export_task(task),
                    targets=targets)
            else:
                self.tasks_and_targets[task.name].append(targets=targets)

        def process_config(self):
            for _, task_targets in self.tasks_and_targets.items():
                task_targets.generate_config(context=self.context)
                self.configuration.merge(context=self.context,
                                         configs=[task_targets.config])
                for target_name in task_targets.config.targets:
                    self.targets_and_configs[target_name] = task_targets.config

    def make_export_task(self, task):
        found_export_task = None
        for export_task in self.project.exports:
            if task.name == export_task.name:
                found_export_task = export_task
                break

        if not found_export_task:
            found_export_task = Target(type=None,
                                       export=True,
                                       name=task.name,
                                       args=task.args)
        return found_export_task

    def get_packages_to_process(self, asked_packages=None):

        packages_to_process = dict()
        tasks_and_targets = self.get_tasks_and_targets_to_process(
            tasks_source=self.project.targets)
        for task, targets in tasks_and_targets:
            for package in self.project.packages:
                task_targets = self.get_targets_from_task(
                    task=task) if not targets else targets

                intersection_targets_package_targets = list(
                    set(task_targets) & set(package.targets))

                if not intersection_targets_package_targets:
                    continue

                if package.name not in packages_to_process:
                    packages_to_process[
                        package.name] = Context.PackageBuildContext(
                            context=self,
                            package=package,
                            task=task,
                            targets=intersection_targets_package_targets)
                    continue

                packages_to_process[package.name].append(
                    task=task, targets=intersection_targets_package_targets)

        return list(packages_to_process.values())

    def get_asked_packages(self):
        return self.context.options.packages.split(
            ',') if self.context.options.packages else [
                package.name for package in self.project.packages
            ]

    def requirements(self):
        if self.is_windows():
            self.requirements_windows()
        elif self.is_darwin():
            self.requirements_darwin()
        elif self.is_linux():
            self.requirements_debian()

    def requirements_windows(self):
        pass

    def requirements_darwin(self):
        pass

    def requirements_debian_install(self, packages):
        packages = list(sorted(set(packages)))
        print('Packages required to be installed: {}'.format(packages))
        print('Looking for installed packages...')

        packages_to_install = []
        found_installed_packages = []
        installed_packages = subprocess.check_output(
            ['apt', 'list', '--installed']).decode(sys.stdout.encoding)
        for package in packages:
            if installed_packages.find(package + '/') == -1:
                packages_to_install.append(package)
            else:
                found_installed_packages.append(package)

        if len(found_installed_packages) > 0:
            print('Found already installed packages: {}'.format(
                found_installed_packages))

        if len(packages_to_install) > 0:
            print('Install the following packages: {}'.format(
                packages_to_install))
            helpers.run_task(['sudo', 'apt', 'install', '-y'] +
                             packages_to_install)
        else:
            print('Nothing to install')

    def requirements_debian(self):
        packages_dev = []
        packages = []

        tasks_and_targets = self.get_tasks_and_targets_to_process()
        for task, targets in tasks_and_targets:
            config, _ = self.iterate_over_task(task=task, targets=targets)
            packages_dev += config.packages_dev
            packages += config.packages

        packages = packages_dev if len(packages_dev) > 0 else packages

        self.requirements_debian_install(packages)

        print('Done')

    def dependencies(self):
        tasks_and_targets = self.get_tasks_and_targets_to_process()
        for task, targets in tasks_and_targets:
            config, _ = self.iterate_over_task(task=task, targets=targets)
            self.cleanup_old_build_files(config=config)

            if not self.context.options.no_copy_artifacts and self.deps_build:
                binary_artifacts = [
                    a for a in config.artifacts.copy()
                    if a.type in ['library', 'program']
                ]

                for binary_artifact in binary_artifacts:
                    binary_artifact.location = self.make_out_path()

                if self.is_darwin():
                    self.patch_darwin_binary_artifacts(
                        binary_artifacts=binary_artifacts,
                        prefix_path='@executable_path')
                elif self.is_linux():
                    self.patch_linux_binary_artifacts(
                        binary_artifacts=binary_artifacts,
                        prefix_path='$ORIGIN',
                        relative_path=True)

    def patch_darwin_binary_artifacts(self,
                                      binary_artifacts,
                                      prefix_path=None,
                                      source_artifacts=[],
                                      relative_path=False):

        if not self.is_darwin():
            raise RuntimeError("Patching binary artifacts only works on macOS")

        path_patched = list()
        for binary_artifact in binary_artifacts:
            real_path_artifact = os.path.realpath(
                binary_artifact.absolute_path)
            _, extension = os.path.splitext(real_path_artifact)

            if real_path_artifact in path_patched:
                continue
            path_patched.append(real_path_artifact)

            if not os.path.exists(binary_artifact.absolute_path):
                continue

            print("otool -L {}".format(binary_artifact.absolute_path))
            otool_infos = subprocess.check_output(
                ['otool', '-L', binary_artifact.absolute_path],
                cwd=self.get_build_path()).decode('utf-8')
            paths = re.findall(r'^\s*(.*) \(', otool_infos, re.MULTILINE)

            id_path = ''
            lib_paths = ''

            if not paths:
                continue

            is_static_library = binary_artifact.type in [
                'library'
            ] and extension in ['.a']
            is_shared_library = binary_artifact.type in [
                'library'
            ] and not is_static_library
            is_program = binary_artifact.type in ['program']

            if is_shared_library:
                id_path = paths[0]
                if len(paths) > 1:
                    lib_paths = paths[1:]
            elif is_program or is_static_library:
                lib_paths = paths

            if not id_path and is_shared_library:
                continue

            print("ID: {}".format(id_path))
            if id_path:
                id_path_basename = os.path.basename(id_path)
                binary_artifact_dirname = os.path.dirname(
                    binary_artifact.absolute_path)
                if prefix_path:
                    binary_artifact_dirname = os.path.dirname(
                        os.path.join(prefix_path, binary_artifact.path))
                expected_binary_artifact_id = os.path.join(
                    binary_artifact_dirname, id_path_basename)
                if id_path != expected_binary_artifact_id:
                    print(
                        "Change ID to {}".format(expected_binary_artifact_id))
                    helpers.run_task([
                        'install_name_tool', '-id',
                        expected_binary_artifact_id,
                        binary_artifact.absolute_path
                    ],
                                     cwd=self.get_build_path())

            print("Dependencies: {}".format(lib_paths))

            for lib_path in lib_paths:
                lib_basename = os.path.basename(lib_path)

                found_artifact = None
                for binary_artifact_bis in binary_artifacts + source_artifacts:
                    if os.path.basename(
                            binary_artifact_bis.absolute_path) == lib_basename:
                        found_artifact = binary_artifact_bis
                        break

                if found_artifact is None:
                    continue

                expected_lib_path = found_artifact.absolute_path
                if relative_path:
                    expected_lib_path = os.path.relpath(
                        path=found_artifact.absolute_path,
                        start=os.path.dirname(binary_artifact.absolute_path))
                    if prefix_path:
                        expected_lib_path = os.path.join(
                            prefix_path, expected_lib_path)
                else:
                    if prefix_path:
                        expected_lib_path = os.path.join(
                            prefix_path, found_artifact.path)

                if expected_lib_path == lib_path:
                    continue

                print("Change dependency path {} -> {}".format(
                    lib_path, expected_lib_path))
                helpers.run_task([
                    'install_name_tool', '-change', lib_path,
                    expected_lib_path, binary_artifact.absolute_path
                ],
                                 cwd=self.get_build_path())

    def patch_linux_binary_artifacts(self,
                                     binary_artifacts,
                                     prefix_path=None,
                                     source_artifacts=[],
                                     relative_path=False,
                                     search_paths=None,
                                     libraries=None,
                                     simulate=False):

        if not self.is_linux():
            raise RuntimeError("Patching binary artifacts only works on linux")

        patchelf_command = [
            'patchelf'
        ]
        if self.is_flatpak():
            patchelf_command = [ 'flatpak-spawn', '--host' ] + patchelf_command

        rpath_results = list()
        path_patched = list()
        for binary_artifact in binary_artifacts:
            real_path_artifact = os.path.realpath(
                binary_artifact.absolute_path)
            _, extension = os.path.splitext(real_path_artifact)

            if real_path_artifact in path_patched:
                continue
            path_patched.append(real_path_artifact)

            if not os.path.exists(
                    binary_artifact.absolute_path) and not simulate:
                continue

            is_static_library = binary_artifact.type in [
                'library'
            ] and extension in ['.a']

            if is_static_library:
                continue

            library_list = list()

            if libraries is None and os.path.exists(
                    binary_artifact.absolute_path):
                readelf_infos = subprocess.check_output(
                    ['readelf', '-d', binary_artifact.absolute_path],
                    cwd=self.get_build_path()).decode('utf-8')
                library_list = re.findall(
                    r'^.*NEEDED\)\s*Shared library: \[([^\]]*)\]',
                    readelf_infos, re.MULTILINE)
            else:
                library_list = libraries.copy()

            if not library_list:
                continue

            if search_paths is None:
                search_paths = list()
                if 'QTLIBS' in self.context.env and os.path.exists(
                        self.context.env.QTLIBS):
                    search_paths = [self.context.env.QTLIBS]

            lib_paths = list()

            for library in library_list:

                found_artifact = None
                for binary_artifact_bis in binary_artifacts + source_artifacts:
                    if binary_artifact_bis.type not in ['library']:
                        continue
                    if os.path.basename(
                            binary_artifact_bis.absolute_path) == library:
                        found_artifact = binary_artifact_bis
                        break

                if found_artifact is None:
                    for search_path in search_paths:
                        if os.path.exists(os.path.join(search_path, library)):
                            if search_path not in lib_paths:
                                lib_paths.append(search_path)
                    continue

                expected_lib_path = found_artifact.absolute_path
                if relative_path:
                    expected_lib_path = os.path.relpath(
                        path=found_artifact.absolute_path,
                        start=os.path.dirname(binary_artifact.absolute_path))
                    if prefix_path:
                        expected_lib_path = os.path.join(
                            prefix_path, expected_lib_path)
                else:
                    if prefix_path:
                        expected_lib_path = os.path.join(
                            prefix_path, found_artifact.path)

                expected_lib_path = os.path.dirname(expected_lib_path)
                if expected_lib_path not in lib_paths:
                    lib_paths.append(expected_lib_path)

            total_diff = lib_paths.copy()

            if not simulate:
                current_rpath = subprocess.check_output(
                    patchelf_command + [
                        '--print-rpath',
                        binary_artifact.absolute_path
                    ],
                    cwd=self.get_build_path()).decode('utf-8').splitlines()[0]

                current_rpath = current_rpath.split(
                    ':') if current_rpath else []

                diff_list1_list2 = list(set(current_rpath) - set(lib_paths))
                diff_list2_list1 = list(set(lib_paths) - set(current_rpath))
                total_diff = diff_list1_list2 + diff_list2_list1

            if lib_paths:
                rpath = ':'.join(lib_paths)
                if not simulate and total_diff:
                    print("Set rpath {} to {}".format(
                        rpath, binary_artifact.absolute_path))
                    helpers.run_task(patchelf_command + [
                        '--set-rpath', rpath,
                        binary_artifact.absolute_path
                    ],
                                     cwd=self.get_build_path())
                rpath_results += lib_paths
            else:
                if not simulate and total_diff:
                    print("Remove rpath from {}".format(
                        binary_artifact.absolute_path))
                    helpers.run_task(patchelf_command + [
                        '--remove-rpath',
                        binary_artifact.absolute_path
                    ],
                                     cwd=self.get_build_path())
                rpath_results += []

        return rpath_results

    def package(self):

        print("Check asked package")

        packages_to_process = self.get_packages_to_process()

        if not packages_to_process:
            raise RuntimeError(
                "Can't find any package associated to the targets: {}".format(
                    self.context.options.targets))

        for package_build_context in packages_to_process:
            package_build_context.process_config()
            if self.is_android():
                self.package_android(
                    package_build_context=package_build_context)
            elif self.is_windows():
                package_msi(self=self,
                            package_build_context=package_build_context)
            elif self.is_darwin():
                package_dmg(self=self,
                            package_build_context=package_build_context)
            elif self.is_linux():
                self.package_debian(
                    package_build_context=package_build_context)

    def package_darwin(self, package_build_context):
        raise RuntimeError("Not implemented yet")

    def get_target_artifacts(self, target):
        config = target.merge_configs(self)
        artifacts_list = []

        def internal(config, dep, artifacts_list=artifacts_list):
            cache_dir = self.find_dep_cache_dir(dep, self.cache_conf)
            artifacts_list += self.list_dep_binary_artifacts(
                config, dep, cache_dir)

        self.recursively_apply_to_deps(config, internal)

        return artifacts_list + self.list_target_binary_artifacts(
            config, target)

    def package_debian(self, package_build_context):

        print("Check package's targets")

        depends = package_build_context.configuration.packages.copy()
        depends = helpers.filter_unique(depends)

        deb_package = package_build_context.package.deb_package
        depends = helpers.filter_unique(deb_package.depends + depends)

        # Don't run this script as root

        print("Gather package metadata")
        prefix = "/usr/local" if deb_package.prefix is None else deb_package.prefix

        subdirectory = prefix

        if deb_package.subdirectory:
            subdirectory = os.path.join(prefix, deb_package.subdirectory)

        package_name = package_build_context.package.name
        package_section = deb_package.section
        package_priority = deb_package.priority
        package_maintainer = deb_package.maintainer
        package_description = deb_package.description
        package_homepage = deb_package.homepage

        version = Version(working_dir=self.get_project_dir(),
                          build_number=self.get_build_number())

        build_number = self.get_build_number(default=0)
        package_version = version.semver

        package_arch = self.get_arch_for_linux()
        package_depends = ', '.join(depends)

        print("Clean-up")
        package_directory = self.make_output_path('dist')
        helpers.remove_tree(self, package_directory)

        # Install documentation

        # Compression man pages

        # Copy systemd unit if any

        print("Prepare package")
        package_directory = helpers.make_directory(package_directory)

        prefix_directory = os.path.realpath(
            helpers.make_directory(package_directory, '.' + prefix))

        subdirectory_directory = os.path.realpath(
            helpers.make_directory(package_directory, '.' + subdirectory))

        helpers.make_directory(subdirectory_directory)

        package_copy_skeleton = None

        if deb_package.copy_skeleton:
            for pair in deb_package.copy_skeleton:
                if not isinstance(pair, tuple) or len(pair) != 2:
                    raise RuntimeError(
                        "Package bad type in copy_skeleton: have to be tuple of size 2 (from path, to path)"
                    )

            package_copy_skeleton = [
                (os.path.join(self.get_project_dir(), path_pair[0]),
                 os.path.join(prefix_directory, path_pair[1]))
                for path_pair in deb_package.copy_skeleton
            ]

            for pair in package_copy_skeleton:
                if not os.path.exists(pair[0]):
                    raise RuntimeError(
                        "Package copy_skeleton source path doesn't exist: {}".
                        format(pair[0]))

            for pair in package_copy_skeleton:
                if os.path.isdir(pair[0]):
                    helpers.make_directory(pair[1])
                    helpers.copy_tree(pair[0], pair[1])
                else:
                    helpers.make_directory(os.path.dirname(pair[1]))
                    helpers.copy_file(pair[0], pair[1])

        package_skeleton = None

        if deb_package.skeleton:
            package_skeleton = os.path.join(self.get_project_dir(),
                                            deb_package.skeleton)

        if package_skeleton and not os.path.exists(package_skeleton):
            raise RuntimeError(
                "Package skeleton directory doesn't exist: {}".format(
                    package_skeleton))

        if package_skeleton:
            helpers.copy_tree(package_skeleton, prefix_directory)

        package_control = None

        if deb_package.control:
            package_control = os.path.join(self.get_project_dir(),
                                           deb_package.control)

        if package_control and not os.path.exists(package_control):
            raise RuntimeError(
                "Package control directory doesn't exist: {}".format(
                    package_control))

        debian_directory = helpers.make_directory(package_directory, 'DEBIAN')

        if package_control:
            helpers.copy_tree(package_control, debian_directory)

        artifacts = package_build_context.configuration.artifacts.copy()
        artifacts = [
            artifact for artifact in artifacts if artifact.scope is None
        ]

        binary_artifacts = list()

        for artifact in artifacts:
            local_dir = 'bin'
            if artifact.type == 'library':
                local_dir = 'lib'
            elif artifact.type == 'program':
                local_dir = 'bin'
            elif artifact.type == 'license':
                if artifact.location != self.get_project_dir():
                    dep_id = self.find_dependency_id(artifact.location)
                    local_dir = os.path.join(
                        'share', 'doc', package_build_context.package.name,
                        'licenses', dep_id)
                else:
                    local_dir = os.path.join(
                        'share', 'doc', package_build_context.package.name,
                        'licenses')
            else:
                local_dir = 'share'

            artifact_filename = os.path.basename(artifact.path)
            artifact_dirname = os.path.dirname(artifact.path)
            if artifact_dirname:
                local_dir = ''

            dst_directory = os.path.realpath(
                helpers.make_directory(
                    subdirectory_directory,
                    os.path.join(artifact_dirname, local_dir)))

            src = artifact.absolute_path
            dst = os.path.abspath(
                os.path.join(dst_directory, artifact_filename))
            dst_dir = os.path.dirname(dst)
            if not os.path.exists(dst_dir):
                print("Creating directories {}".format(dst_dir))
                os.makedirs(dst_dir)
            print("Copying {} to {}".format(src, dst))
            helpers.copy_file(src, dst)
            artifact.path = os.path.join(artifact_dirname, local_dir,
                                         artifact_filename)
            artifact.location = os.path.realpath(subdirectory_directory)
            if artifact.type in ['library', 'program']:
                binary_artifacts.append(artifact)

        # Strip binaries, libraries, archives

        if (self.is_release() and package_build_context.package.stripping is
                None) or (package_build_context.package.stripping is not None
                          and package_build_context.package.stripping):
            for artifact in artifacts:
                if artifact.type not in ['library', 'program']:
                    continue
                print("Stripping {}".format(artifact.absolute_path))
                helpers.run_task(['strip', artifact.absolute_path],
                                 cwd=subdirectory_directory)

        repository = self.load_git_remote_origin_url()
        targets_binaries = []
        targets_libpaths = ['lib']
        target_programs = []
        qt_binaries = []
        for artifact in artifacts:
            if artifact.type in ['library', 'program']:
                if artifact.target in package_build_context.package.targets and artifact.repository == repository:
                    targets_binaries.append(artifact.path)

                    target_config = None
                    if artifact.target in package_build_context.targets_and_configs:
                        target_config = package_build_context.targets_and_configs[
                            artifact.target]

                    if target_config and self.is_qt_enabled(
                            config=target_config):
                        qt_binaries.append(artifact.path)

                    if artifact.type in ['program']:
                        target_programs.append(artifact.path)

            if artifact.type in ['library']:
                target_path = os.path.dirname(artifact.path)
                if target_path:
                    targets_libpaths.append(target_path)

        targets_binaries = helpers.filter_unique(targets_binaries)
        targets_libpaths = helpers.filter_unique(targets_libpaths)

        for artifact in artifacts:
            if artifact.type not in ['library', 'program']:
                continue
            print("Remove rpath {}".format(artifact.absolute_path))
            helpers.run_task(
                patchelf_command + ['--remove-rpath', artifact.absolute_path],
                cwd=subdirectory_directory)

        targets_binaries_real_paths = list()
        unique_targets_binaries = list()
        for binary in targets_binaries:
            real_path = os.path.realpath(
                os.path.join(subdirectory_directory, binary))
            if real_path in targets_binaries_real_paths:
                continue
            targets_binaries_real_paths.append(real_path)
            unique_targets_binaries.append(binary)
        targets_binaries_symlinks = list()

        qt_targets_binaries_real_paths = list()
        qt_unique_targets_binaries = list()
        for binary in qt_binaries:
            real_path = os.path.realpath(
                os.path.join(subdirectory_directory, binary))
            if real_path in qt_targets_binaries_real_paths:
                continue
            qt_targets_binaries_real_paths.append(real_path)
            qt_unique_targets_binaries.append(binary)

        if 'qt5' in package_build_context.configuration.wfeatures:
            if not self.context.env.QMAKE:
                raise RuntimeError("Can't find path to qmake")
            if not self.context.env.QTLIBS:
                raise RuntimeError("Can't find path to Qt libraries")
            for binary in unique_targets_binaries:

                if binary not in qt_unique_targets_binaries:
                    print("{} is not a Qt binary".format(binary))
                    continue

                print("Run linuxdeployqt {}".format(binary))

                real_path = os.path.realpath(
                    os.path.join(subdirectory_directory, binary))
                if not os.path.exists(real_path):
                    raise RuntimeError(
                        "Cannot find binary path {}".format(real_path))

                binary_dir = os.path.dirname(binary)
                binary_filename = os.path.basename(binary)
                if os.path.basename(binary_dir) not in ['bin', 'lib']:
                    local_dir = ''
                    found_artifact = None
                    for artifact in artifacts:
                        if artifact.path == binary:
                            found_artifact = artifact

                    if not found_artifact:
                        raise Exception(
                            "Cannot find artifact corresponding to {}".format(
                                binary))

                    if found_artifact.type == 'library':
                        local_dir = 'lib'
                    else:
                        local_dir = 'bin'

                    symlink_path = os.path.join(subdirectory_directory,
                                                local_dir, binary_filename)
                    os.symlink(os.path.join(subdirectory_directory, binary),
                               symlink_path)
                    targets_binaries_symlinks.append(symlink_path)
                    binary = symlink_path

                command_env = os.environ.copy()
                ld_lib_path = 'LD_LIBRARY_PATH'
                if ld_lib_path not in command_env:
                    command_env[ld_lib_path] = ''
                command_env[ld_lib_path] = ':'.join([
                    os.path.join(subdirectory_directory, path)
                    for path in targets_libpaths
                ] + [self.context.env.QTLIBS]) + (
                    ':' + command_env[ld_lib_path]
                    if command_env[ld_lib_path] else '')

                helpers.run_task([
                    'linuxdeployqt', binary,
                    '-qmake=' + self.context.env.QMAKE[0]
                ] + [
                    '-qmldir={}'.format(
                        os.path.realpath(
                            os.path.join(self.get_project_dir(), qmldir)))
                    for qmldir in package_build_context.configuration.qmldirs
                ],
                                 cwd=subdirectory_directory,
                                 env=command_env)

                app_run_binary_dir = os.path.join(os.path.dirname(binary),
                                                  'AppRun')
                if os.path.exists(app_run_binary_dir):
                    os.remove(app_run_binary_dir)

                app_run_root = os.path.join(subdirectory_directory, 'AppRun')
                if os.path.exists(app_run_root):
                    os.remove(app_run_root)

                app_run_parent = os.path.join(subdirectory_directory, '..',
                                              'AppRun')
                if os.path.exists(app_run_parent):
                    os.remove(app_run_parent)

            qt_conf_path = os.path.join(subdirectory_directory, 'bin',
                                        'qt.conf')
            if not os.path.exists(qt_conf_path):
                with open(qt_conf_path, 'w') as qt_conf_file:
                    qt_conf_file.writelines([
                        "[Paths]\n",  # Header
                        "Prefix = ../\n",  # Prefix
                        "Plugins = plugins\n",  # Plugin
                        "Imports = qml\n",  # QML imports
                        "Qml2Imports = qml\n"  # QML imports
                    ])

        for symlink_path in targets_binaries_symlinks:
            os.remove(symlink_path)

        rpath = ':'.join(
            [os.path.join(subdirectory, path) for path in targets_libpaths])

        if deb_package.rpath:
            rpath = deb_package.rpath

        if rpath:
            print("RPATH is set on {}".format(rpath))
        else:
            print("No RPATH defined")

        if rpath:
            for artifact in artifacts:
                if artifact.type not in ['library', 'program']:
                    continue
                print("Set rpath on file {}".format(artifact.absolute_path))
                helpers.run_task(
                    ['patchelf', '--set-rpath', rpath, artifact.absolute_path],
                    cwd=subdirectory_directory)
        else:
            for artifact in artifacts:
                if artifact.type not in ['library', 'program']:
                    continue
                print("Remove rpath {}".format(artifact.absolute_path))
                helpers.run_task(
                    ['patchelf', '--remove-rpath', artifact.absolute_path],
                    cwd=subdirectory_directory)

        all_prefix_files = []
        for (dirpath, dirnames, filenames) in os.walk(subdirectory_directory):
            all_prefix_files.extend([
                os.path.realpath(os.path.join(dirpath, filename))
                for filename in filenames
            ])

        template_tempoary_dir = self.make_build_path('dist_templates')
        helpers.make_directory(template_tempoary_dir)

        for template in deb_package.templates:
            template_path = os.path.join(prefix_directory, template)

            if not os.path.exists(str(template_path)):
                raise RuntimeError(
                    "Cannot find any template file at {}".format(
                        str(template_path)))

            tmp_path = os.path.join(template_tempoary_dir, template)
            helpers.make_directory(os.path.dirname(tmp_path))
            helpers.copy_file(template_path, tmp_path)
            os.remove(template_path)

            template_src = self.context.root.find_node(tmp_path)
            template_dst = self.context.root.find_or_declare(template_path)

            self.context(features='subst',
                         source=template_src,
                         target=template_dst,
                         LIBRARY_PATHS=str(rpath),
                         BINARY_PATH=str(
                             os.path.join(subdirectory, target_programs[0])),
                         NAME=str(package_build_context.package.name),
                         PREFIX=str(prefix),
                         SUBDIRECTORY=str(subdirectory))

        class make_executable(Task.Task):
            always_run = True
            run_str = 'chmod +x ${SRC}'

        def create_task_make_executable(path):
            task = make_executable(env=self.context.env)
            task.set_inputs(path)
            self.context.add_to_group(task)

        debian_template_tempoary_dir = self.make_build_path(
            'dist_templates_debian')
        helpers.make_directory(debian_template_tempoary_dir)

        for (dirpath, dirnames, filenames) in os.walk(debian_directory):
            for filename in filenames:
                if filename not in [
                        'conffiles', 'postinst', 'postrm', 'preinst', 'prerm'
                ]:
                    continue

                template_path = os.path.join(dirpath, filename)
                tmp_path = os.path.join(debian_template_tempoary_dir, filename)
                helpers.make_directory(os.path.dirname(tmp_path))
                helpers.copy_file(template_path, tmp_path)
                os.remove(template_path)

                template_src = self.context.root.find_node(tmp_path)
                template_dst = self.context.root.find_or_declare(template_path)

                self.context(features='subst',
                             source=template_src,
                             target=template_dst,
                             LIBRARY_PATHS=str(rpath),
                             BINARY_PATH=str(
                                 os.path.join(subdirectory,
                                              target_programs[0])),
                             NAME=str(package_build_context.package.name),
                             PREFIX=str(prefix),
                             SUBDIRECTORY=str(subdirectory))

                create_task_make_executable(path=template_dst)
            break

        self.context.add_group()

        control_path = os.path.join(debian_directory, 'control')
        with open(control_path, 'w') as control_file:
            control_file.writelines([
                "Package: " + package_name + '\n',    # Foo
                "Version: " + package_version + '\n',   # 0.1.2
                "Section: " + package_section + '\n',   # misc
                "Priority: " + package_priority + \
                '\n',   # { optional | ... }
                "Architecture: " + package_arch + '\n',   # amd64, i386
                # list, of, dependencies, as, package, names
                "Depends: " + package_depends + '\n',
                "Maintainer: " + package_maintainer + \
                        '\n',  # { Company | Firstname LASTNAME }
                "Description: " + package_description + '\n',  # One sentence description
                "Homepage: " + package_homepage + '\n'   # https://company.com/
            ])

        print("Build package")
        output_filename = package_name + '_' + package_version + "_" + package_arch

        class fakeroot(Task.Task):
            always_run = True
            run_str = 'fakeroot dpkg-deb --build ${SRC} ${TGT}'

        task = fakeroot(env=self.context.env)
        task.set_inputs(self.context.root.find_node(package_directory))
        task.set_outputs(
            self.context.root.find_or_declare(
                os.path.realpath(
                    os.path.join(self.get_output_path(),
                                 output_filename + '.deb'))))
        self.context.add_to_group(task)

        self.context.execute_build()

        if not deb_package.rpath:
            paths_done = []
            for binary_artifact in binary_artifacts:
                if binary_artifact.path not in paths_done:
                    paths_done.append(binary_artifact.path)

            lib_directory = os.path.join(subdirectory_directory, 'lib')

            libraries_list = self.find_artifacts(path=lib_directory,
                                                 recursively=True,
                                                 types=('*.so', '*.so.*'))

            found_lib_artifacts = []
            for library in libraries_list:
                library_path = os.path.relpath(path=library,
                                               start=subdirectory_directory)
                library_location = subdirectory_directory
                library_artifact = self.create_artifact(
                    path=library_path,
                    location=library_location,
                    type='library')
                if library_artifact.path not in paths_done:
                    paths_done.append(library_artifact.path)
                    found_lib_artifacts.append(library_artifact)

            all_binary_artifacts = binary_artifacts + found_lib_artifacts
            for binary_artifact in all_binary_artifacts:
                self.patch_linux_binary_artifacts(
                    binary_artifacts=[binary_artifact],
                    prefix_path='$ORIGIN',
                    source_artifacts=all_binary_artifacts,
                    relative_path=True,
                    search_paths=[])

        system_name = self.osname()
        distribution_name = self.distribution()
        release_name = self.release()

        class File:
            def __init__(self, path, absolute_path, type='file'):
                self.path = path
                self.absolute_path = absolute_path
                self.type = type

        class System:
            def __init__(self):
                self.name = system_name
                self.distribution = distribution_name
                self.release = release_name
                self.version = platform.platform() + '-' + '-'.join(
                    platform.libc_ver())
                self.architecture = package_arch

        files_absolute_paths = []
        files = []
        for artifact in artifacts:
            artifact_file = File(path=artifact.path,
                                 absolute_path=artifact.absolute_path,
                                 type=artifact.type)
            files_absolute_paths.append(
                os.path.realpath(artifact.absolute_path))
            files.append(artifact_file)

        package_filename = output_filename + '.deb'

        package_path = os.path.realpath(
            os.path.join(self.get_output_path(), package_filename))

        package_file = File(path=package_filename,
                            absolute_path=package_path,
                            type='package')

        libraries_list = self.find_artifacts(path=subdirectory_directory,
                                             recursively=True,
                                             types=('*.so', '*.so.*',
                                                    '*.dylib', '*.dylib.*'))

        for file_path in all_prefix_files:
            if os.path.realpath(file_path) in files_absolute_paths:
                continue

            file_type = 'library' if file_path in libraries_list else 'file'

            if file_type == 'library':
                is_executable = (os.stat(file_path).st_mode & stat.S_IXUSR) > 0
                file_type = file_type if is_executable else 'file'

            artifact_file = File(path=os.path.relpath(
                path=file_path, start=subdirectory_directory),
                                 absolute_path=file_path,
                                 type=file_type)

            files_absolute_paths.append(file_path)
            files.append(artifact_file)

        class Context:
            def __init__(self):
                self.name = package_build_context.package.name
                self.binaries = targets_binaries
                self.libpaths = targets_libpaths
                self.targets = package_build_context.package.targets
                self.files = files
                self.version = version.semver
                self.major = version.major
                self.minor = version.minor
                self.patch = version.patch
                self.build_number = build_number
                self.hash = version.githash
                self.system = System()
                self.message = version.gitmessage
                self.package = package_file

        ctx = Context()
        for hook in package_build_context.package.hooks:
            hook(ctx)