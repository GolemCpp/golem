import os
import io
import re
import sys
import md5
import glob
import json
import fnmatch
import shutil
import pickle
import platform
import subprocess
import ConfigParser
import distutils
from distutils import dir_util
from copy import deepcopy
from module import Module
from cache import CacheConf, CacheDir
from configuration import Configuration
import cache
import helpers
from helpers import *
from project import Project
from build_target import BuildTarget
from dependency import Dependency
import copy
from target import TargetConfigurationFile

class Context:
    def __init__(self, context):
        self.context = context

        self.project_path = self.make_project_path("golem.json")
        if os.path.exists(self.project_path):
            json_object = None
            with io.open(self.project_path, 'r') as file:
                json_object = byteify(json.load(file))
            self.project = Project.unserialize_from_json(json_object)
            self.module = None

        self.project_path = self.make_project_path("golem.py")
        if not os.path.exists(self.project_path):
            self.project_path = self.make_project_path("project.glm")
        if os.path.exists(self.project_path):
            self.module = Module(self.get_project_dir())
            self.project = self.module.project()

        self.resolved_dependencies_path = None

    def load_resolved_dependencies(self):
        if self.resolved_dependencies_path is not None:
            return
        
        deps_cache_file_pickle = self.make_build_path('deps.cache')
        deps_cache_file_json = self.make_project_path('dependencies.json')

        if self.context.options.resolved_dependencies_directory is not None:
            deps_cache_file_json = os.path.join(self.context.options.resolved_dependencies_directory, 'dependencies.json')

        if os.path.exists(deps_cache_file_json):
            print('Found ' + str(deps_cache_file_json))
            self.load_dependencies_json(deps_cache_file_json)
            self.resolved_dependencies_path = deps_cache_file_json
        else:
            print("No dependencies cache found")

    
    def resolve_dependencies(self):
        deps_cache_file_pickle = self.make_build_path('deps.cache')
        deps_cache_file_json = self.make_project_path('dependencies.json')

        deps_cache_file_json_build = None
        if self.context.options.resolved_dependencies_directory is not None:
            deps_cache_file_json_build = os.path.join(self.context.options.resolved_dependencies_directory, 'dependencies.json')

        if not self.context.options.keep_resolved_dependencies:
            if os.path.exists(deps_cache_file_pickle):
                print("Cleaning up " + str(deps_cache_file_pickle))
                os.remove(deps_cache_file_pickle)

            if os.path.exists(deps_cache_file_json):
                print("Cleaning up " + str(deps_cache_file_json))
                os.remove(deps_cache_file_json)

            if deps_cache_file_json_build is not None and os.path.exists(deps_cache_file_json_build):
                print("Cleaning up " + str(deps_cache_file_json_build))
                os.remove(deps_cache_file_json_build)

        self.resolved_dependencies_path = None

        self.load_resolved_dependencies()

        if self.resolved_dependencies_path is None:
            save_path = deps_cache_file_json
            if self.context.options.resolved_dependencies_directory is not None:
                make_directory(self.context.options.resolved_dependencies_directory)
                save_path = os.path.join(self.context.options.resolved_dependencies_directory, 'dependencies.json')
            print("Saving dependencies in cache " + str(save_path))
            self.save_dependencies_json(save_path)
            self.resolved_dependencies_path = save_path

    def load_dependencies_json(self, path):
        cache = None
        with open(path, 'r') as fp:
            cache = byteify(json.load(fp))
        self.project.deps_load_json(cache)

    def save_dependencies_json(self, path):
        cache = self.project.deps_resolve_json()
        with open(path, 'w') as fp:
            json.dump(cache, fp, indent=4)

    def get_project_dir(self):
        return self.context.options.dir

    def make_cache_dir(self):
        cache_dir_list = []

        if self.context.options.cache_dir:

            cache_dir = self.context.options.cache_dir
            if not os.path.isabs(cache_dir):
                cache_dir = os.path.join(self.get_project_dir(), cache_dir)

            cache_dir_list.append(CacheDir(cache_dir, False))

        if self.context.options.static_cache_dir:
            static_cache_dir = self.context.options.static_cache_dir
            if not os.path.isabs(static_cache_dir):
                static_cache_dir = os.path.join(self.get_project_dir(), static_cache_dir)
            cache_dir_list.append(CacheDir(static_cache_dir, True))

        return cache_dir_list

    def make_writable_cache_dir(self):
        if self.context.options.cache_dir:
            cache_dir = self.context.options.cache_dir
            if not os.path.isabs(cache_dir):
                cache_dir = os.path.join(self.get_project_dir(), cache_dir)
        else:
            cache_dir = cache.default_cached_dir().location
        return cache_dir

    def make_static_cache_dir(self):
        static_cache_dir = self.context.options.static_cache_dir
        if not os.path.isabs(static_cache_dir):
            static_cache_dir = os.path.join(self.get_project_dir(), static_cache_dir)
        return static_cache_dir

    def make_project_path(self, path):
        return os.path.join(self.get_project_dir(), path)

    def make_project_path_array(self, array):
        return [self.make_project_path(x) for x in array]

    @staticmethod
    def hash_identifier(flags):
        m = md5.new()
        m.update(''.join(flags))
        return m.hexdigest()[:8]

    def list_include(self, includes):
        return [self.context.root.find_dir(str(x)) if os.path.isabs(x) else self.context.srcnode.find_dir(str(x)) for x in includes]

    def list_files(self, source, extentions):
        result = []
        for x in source:
            if os.path.isfile(x):
                file_node = self.context.root.find_node(str(x)) if os.path.isabs(x) else self.context.srcnode.find_node(str(x))
                result.append(file_node)
            elif os.path.isdir(x):
                file_nodes = [item for sublist in [self.context.root.find_dir(str(x)).ant_glob('**/*.' + extention) if os.path.isabs(x) else self.context.srcnode.find_dir(str(x)).ant_glob('**/*.' + extention) for x in [x] for extention in extentions] for item in sublist]
                result += file_nodes
        return result

    def list_source(self, source):
        return self.list_files(source, ['cpp', 'c', 'cxx', 'cc'])

    def list_moc(self, source):
        return self.list_files(source, ['hpp', 'h', 'hxx', 'hh'])

    def list_qt_qrc(self, source):
        return self.list_files(source, ['qrc'])

    def list_qt_ui(self, source):
        return self.list_files(source, ['ui'])

    @staticmethod
    def link_static():
        return 'static'
        
    @staticmethod
    def link_shared():
        return 'shared'
        
    def link(self, dep = None):
        return self.context.options.link if dep is None or not dep.link else dep.link_unique

    def distribution(self):
        if self.is_linux():
            return platform.linux_distribution()[0].lower()
        return None

    def release(self):
        if self.is_linux():
            import lsb_release
            return lsb_release.get_distro_information()['CODENAME'].lower()
        return None

    def link_min(self, dep = None):
        return self.link(dep)[:2]

    def is_static(self):
        return self.context.options.link == self.link_static()

    def is_shared(self):
        return self.context.options.link == self.link_shared()

    def runtime(self):
        return self.context.options.runtime

    def runtime_min(self):
        return self.runtime()[:2]

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
                return []
        elif config.type_unique == 'objects':
            return ['.o']
        else:
            return []

    def artifact_suffix(self, config, target):
        is_shared = self.is_shared() if not target.link else target.link_unique == 'shared'
        return self.artifact_suffix_mode(config, is_shared)

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
        is_shared = self.is_shared() if not target.link else target.link_unique == 'shared'
        return self.dev_artifact_suffix(is_shared)

    def is_debug(self):
        return self.context.options.variant == self.variant_debug()
            
    def is_release(self):
        return self.context.options.variant == self.variant_release()

    def variant_min(self):
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
        return self.context.env.CXX_NAME + '-' + '.'.join(self.context.env.CC_VERSION)

    def compiler_name(self):
        return self.context.env.CXX_NAME

    def compiler_version(self):
        return '.'.join(self.context.env.CC_VERSION)

    def compiler_min(self):
        return self.compiler()

    @staticmethod
    def machine():
        if os.name == 'nt' and sys.version_info[:2] < (2,7):
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
            'i386': 'x86',
            'i686': 'x86',
            'x86': 'x86'
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

    def get_arch_for_linux(self, arch = None):
        machine2bits = {
            'x64': 'amd64',
            'x86': 'i386'
        }
        return machine2bits.get(self.get_arch() if arch is None else arch.lower(), None)

    @staticmethod
    def options(context):
        context.load('compiler_c compiler_cxx qt5')
        context.add_option("--dir", action="store", default='.', help="Project location")
        context.add_option("--variant", action="store", default='debug', help="Runtime Linking")
        context.add_option("--runtime", action="store", default='shared', help="Runtime Linking")
        context.add_option("--link", action="store", default='shared', help="Library Linking")
        context.add_option("--arch", action="store", default=Context.osarch(), help="Target Architecture")

        context.add_option("--major", action="store_true", default=False, help="Release major version")
        context.add_option("--minor", action="store_true", default=False, help="Release minor version")
        context.add_option("--patch", action="store_true", default=False, help="Release patch version")

        context.add_option("--export", action="store", default='', help="Export folder")
        context.add_option("--packages", action="store", default='', help="Packages to process")

        context.add_option("--vscode", action="store_true", default=False, help="VSCode CppTools Properties")

        context.add_option("--cache-dir", action="store", default='', help="Cache directory location")
        context.add_option("--static-cache-dir", action="store", default='', help="Read-only cache directory location")
        
        if Context.is_windows(): 
            context.add_option("--nounicode", action="store_true", default=False, help="Unicode Support")
        else: 
            context.add_option("--nounicode", action="store_true", default=True, help="Unicode Support")
        
        context.add_option("--android-ndk", action="store", default='', help="Android NDK path")
        context.add_option("--android-sdk", action="store", default='', help="Android SDK path")
        context.add_option("--android-ndk-platform", action="store", default='', help="Android NDK platform version")
        context.add_option("--android-sdk-platform", action="store", default='', help="Android SDK platform version")
        context.add_option("--android-jdk", action="store", default='', help="JDK path to use when packaging Android app")
        context.add_option("--android-arch", action="store", default='', help="Android target architecture")

        context.add_option("--keep-resolved-dependencies", action="store", default=False, help="Keep resolved dependencies when set")
        context.add_option("--resolved-dependencies-directory", action="store", default=None, help="Resolved dependencies directory path")

    def configure_init(self):
        if not self.context.env.DEFINES:
            self.context.env.DEFINES=[]
        if not self.context.env.CXXFLAGS:
            self.context.env.CXXFLAGS=[]
        if not self.context.env.CFLAGS:
            self.context.env.CFLAGS=[]
        if not self.context.env.LINKFLAGS:
            self.context.env.LINKFLAGS=[]
        if not self.context.env.ARFLAGS:
            self.context.env.ARFLAGS=[]

    def find_cache_conf(self):
        settings_path = self.make_project_path('settings.glm')
        if not os.path.exists(settings_path):
            return None
        raise Exception("Not implemented")

        config = ConfigParser.RawConfigParser()
        config.read(settings_path)

        if not config.has_section('GOLEM'):
            return None

        cacheconf = CacheConf()
        cacheconf.locations = self.make_cache_dir()

        # cache remote
        if not config.has_option('GOLEM', 'cache.remote'):
            return None
        
        remote = config.get('GOLEM', 'cache.remote')

        if not remote:
            return None

        cacheconf.remote = remote.strip('\'"')

        # cache location
        #if config.has_option('GOLEM', 'cache.location'):
        #	location = config.get('GOLEM', 'cache.location')
            
        cacheconf.locations = [CacheDir(cacheconf.location.strip('\'"'))]

        # return cache configuration
        return cacheconf

    def configure_default(self):
        if not self.context.options.nounicode:
            self.context.env.DEFINES.append('UNICODE')

        if self.is_windows():
            if self.is_x86():
                self.context.env.LINKFLAGS.append('/MACHINE:X86')
                self.context.env.ARFLAGS.append('/MACHINE:X86')
            elif self.is_x64():
                self.context.env.LINKFLAGS.append('/MACHINE:X64')
                self.context.env.ARFLAGS.append('/MACHINE:X64')
                
            if self.is_x86():
                self.context.env.MSVC_TARGETS = ['x86']
            elif self.is_x64():
                self.context.env.MSVC_TARGETS = ['x86_amd64']

            self.context.env.MSVC_MANIFEST = False # disable waf manifest behavior

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
            self.context.env.CXX	= ['clang++']
            
    def configure_debug(self):

        if self.is_windows():
            if self.is_static():
                self.context.env.CXXFLAGS.append('/MTd')
                self.context.env.CFLAGS.append('/MTd')
            elif self.is_shared():
                self.context.env.CXXFLAGS.append('/MDd')
                self.context.env.CFLAGS.append('/MDd')

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

    def configure_release(self):

        self.context.env.DEFINES.append('NDEBUG')

        if self.is_windows():
            if self.is_static():
                self.context.env.CXXFLAGS.append('/MT')
                self.context.env.CFLAGS.append('/MT')
            elif self.is_shared():
                self.context.env.CXXFLAGS.append('/MD')
                self.context.env.CFLAGS.append('/MD')
        
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


    def environment(self, resolve_dependencies=False):
        
        # load all environment variables
        self.context.load_envs()

        x86_options = self.restore_options_env(self.context.all_envs['x86'])
        is_x86 = Context.osarch_parser(x86_options['arch']) == 'x86'

        # set environment variables according architecture
        if is_x86:
            self.context.env = self.context.all_envs['x86'].derive()
        else:
            self.context.env = self.context.all_envs['x64'].derive()

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

        if resolve_dependencies:
            self.resolve_dependencies()
        else:
            self.load_resolved_dependencies()

    def dep_system(self, context, libs):
        context.env['LIB'] += libs
        
    def dep_static_release(self, name, fullname, lib):
        
        self.context.env['INCLUDES_' + name]		= self.list_include(self.context, ['includes'])
        self.context.env['STLIBPATH_' + name]	= self.list_include(self.context, ['libpath'])
        self.context.env['STLIB_' + name]		= lib
        
    def dep_static(self, name, fullname, lib, libdebug):
        
        self.context.env['INCLUDES_' + name]		= self.list_include(self.context, ['includes'])
        self.context.env['STLIBPATH_' + name]	= self.list_include(self.context, ['libpath'])
        
        if self.is_debug():
            self.context.env['STLIB_' + name]	= libdebug
        else:
            self.context.env['STLIB_' + name]	= lib
            
        
    def dep_shared_release(self, name, fullname, lib):
        
        self.context.env['INCLUDES_' + name]		= self.list_include(self.context, ['includes'])
        self.context.env['LIBPATH_' + name]		= self.list_include(self.context, ['libpath'])
        self.context.env['LIB_' + name]			= lib
        
    def dep_shared(self, name, fullname, lib, libdebug):
        
        self.context.env['INCLUDES_' + name]		= self.list_include(self.context, ['includes'])
        self.context.env['LIBPATH_' + name]		= self.list_include(self.context, ['libpath'])
        
        if self.is_debug():
            self.context.env['LIB_' + name]		= libdebug
        else:
            self.context.env['LIB_' + name]		= lib


    def make_cache_conf(self):
        cache_conf = self.find_cache_conf()
        if not cache_conf:
            cache_conf = CacheConf()
            cache_conf.locations = self.make_cache_dir()

        if len(cache_conf.locations) == 0:
            cache_conf.locations.append(cache.default_cached_dir())

        return cache_conf

    def get_local_dep_pkl(self, dep):
        return os.path.join(self.make_out_path(), dep.name + '.pkl')

    def get_dep_version_branch(self, dep):
        dep_version_branch = dep.resolve()
        if dep.version != 'latest' and dep.resolved_version != dep.version:
            dep_version_branch = dep.version
        return dep_version_branch
        
    def get_dep_location(self, dep, cache_dir):
        path = make_dep_base(dep)
        return os.path.join(cache_dir.location, path)

    def get_dep_repo_location(self, dep, cache_dir):
        path = self.get_dep_location(dep, cache_dir)
        return os.path.join(path, 'repository')
    
    def get_dep_include_location(self, dep, cache_dir):
        path = self.get_dep_location(dep, cache_dir)
        return os.path.join(path, 'include')

    def get_dep_artifact_location(self, dep, cache_dir):
        path = self.get_dep_location(dep, cache_dir)
        return os.path.join(path, self.build_path(dep))
    
    def get_dep_build_location(self, dep, cache_dir):
        path = self.get_dep_artifact_location(dep, cache_dir)
        return path + '-build'

    def get_dep_artifact_json(self, dep, cache_dir):
        path = self.get_dep_artifact_location(dep, cache_dir)
        return os.path.join(path, dep.name + '.json')
        
    def use_dep(self, config, dep, cache_dir, enable_env, has_artifacts):
        dep_path_build = self.get_dep_artifact_location(dep, cache_dir)
        dep_path_include = self.get_dep_include_location(dep, cache_dir)
        
        dependency_dependencies = []
        dependency_configuration = Configuration()

        file_json_path = self.get_dep_artifact_json(dep, cache_dir)
        with open(file_json_path, 'r') as file_json:
            dep_export_ctx = byteify(json.load(file_json))
            target_configuration_file = TargetConfigurationFile.unserialize_from_json(dep_export_ctx)
            dependency_dependencies = target_configuration_file.dependencies
            dependency_configuration = target_configuration_file.configuration
        
        if config is not None:
            dependency_configuration.includes = []
            
            config_targets = copy.deepcopy(config.targets)
            config.merge(self, [dependency_configuration])
            config.targets = config_targets

            if dep.targets:
                for target in dep.targets:
                    if not target in dependency_configuration.targets:
                        raise RuntimeError("Cannot find target: " + target)
                dependency_configuration.targets = dep.targets
                
            if enable_env:
                # use cache :)
                if not self.is_windows():
                    self.context.env['CXXFLAGS_' + dep.name]			= ['-isystem' + dep_path_include]
                else:
                    self.context.env['CXXFLAGS_' + dep.name]			= ['/external:I' + dep_path_include]
                self.context.env['ISYSTEM_' + dep.name]				= self.list_include([dep_path_include])
                if not dependency_configuration.header_only:
                    is_static = self.is_static()
                    if dep.link:
                        is_static = dep.link_unique == 'static'
                    if is_static:
                        self.context.env['STLIBPATH_' + dep.name]			= self.list_include([dep_path_build])
                        if self.is_darwin():
                            self.context.env['LDFLAGS_' + dep.name]			= [os.path.join(dep_path_build, 'lib' + libname + self.artifact_suffix_dev(dep)) for libname in self.make_target_name_from_context(dependency_configuration, dep)]
                        else:
                            self.context.env['STLIB_' + dep.name]			= self.make_target_name_from_context(dependency_configuration, dep)
                    else:
                        self.context.env['LIBPATH_' + dep.name]			= self.list_include([dep_path_build])
                        self.context.env['LIB_' + dep.name]			= self.make_target_name_from_context(dependency_configuration, dep)
            
            config.use.append(dep.name)

        if dependency_dependencies is not None:
            self.project.deps = dict((obj.name, obj) for obj in (self.project.deps + dependency_dependencies)).values()

        out_path = make_directory(self.make_out_path())
        expected_files = self.get_expected_files(config, dep, cache_dir, has_artifacts)
        for file in expected_files:
            src_file_path = os.path.join(dep_path_build, file)
            expected_file_path = os.path.join(out_path, file)
            should_copy = not os.path.exists(os.path.join(out_path, file))
            if not should_copy:
                should_copy = os.path.getctime(expected_file_path) < os.path.getctime(src_file_path)
            if should_copy:
                print("Copy file {}".format(file))
                copy_file(src_file_path, out_path)
                if self.is_linux() and file.endswith('.so'):
                    src_file_path_glob = glob.glob(src_file_path + '.*')
                    for other_file_path in src_file_path_glob:
                        print("Copy file {}".format(os.path.basename(other_file_path)))
                        copy_file(other_file_path, out_path)
                    
    def clean_repo(self, repo_path):
        helpers.run_task(['git', 'reset', '--hard'], cwd=repo_path)
        helpers.run_task(['git', 'clean', '-fxd'], cwd=repo_path)

    def clone_repo(self, dep, repo_path):
        version_branch = self.get_dep_version_branch(dep)
        # NOTE: Can't use ['--depth', '1'] because of git describe --tags

        os.makedirs(repo_path)
        print("Cloning repository {} into {}".format(dep.repository, repo_path))
        helpers.run_task(['git', 'clone', '--recursive', '--branch', version_branch, '--', dep.repository, '.'], cwd=repo_path)

    def make_repo_ready(self, dep, cache_dir):
        repo_path = self.get_dep_repo_location(dep, cache_dir)

        if os.path.exists(repo_path):
            self.clean_repo(repo_path)
        else:
            self.clone_repo(dep, repo_path)

        return repo_path

    def run_dep_command(self, dep, cache_dir, command):
        dep_path = self.get_dep_location(dep, cache_dir)
        repo_path = self.make_repo_ready(dep, cache_dir)
        build_path = self.get_dep_build_location(dep, cache_dir)

        helpers.run_task([
            'golem',
            'configure',
            '--targets=' + dep.name,
            '--runtime=' + self.context.options.runtime,
            '--link=' + (self.context.options.link if not dep.link else dep.link_unique),
            '--arch=' + self.context.options.arch,
            '--variant=' + self.context.options.variant,
            '--export=' + dep_path,
            '--cache-dir=' + self.make_writable_cache_dir(),
            '--static-cache-dir=' + self.make_static_cache_dir(),
            '--dir=' + build_path,
            '--resolved-dependencies-directory=' + build_path
        ], cwd=repo_path)

        helpers.run_task([
            'golem',
            command,
            '--dir=' + build_path
        ], cwd=repo_path)

        if command == 'build':
            helpers.run_task([
                'golem',
                'export',
                '--dir=' + build_path
            ], cwd=repo_path)


    def can_open_json(self, dep, cache_dir):
        json_path = self.get_dep_artifact_json(dep, cache_dir)
        return os.path.exists(json_path)

    def open_json(self, dep, cache_dir):
        json_path = self.get_dep_artifact_json(dep, cache_dir)
        return open(json_path, 'r')

    def read_json(self, dep, cache_dir):
        if self.can_open_json(dep, cache_dir):
            with self.open_json(dep, cache_dir) as file_json:
                return byteify(json.load(file_json))
        return None

    def read_dep_configs(self, dep, cache_dir):
        dep_json = self.read_json(dep, cache_dir)
        if dep_json is None:
            return None
        return TargetConfigurationFile.unserialize_from_json(dep_json).configuration
    
    def make_target_name_from_context(self, config, target):

        if config.targets:
            return config.targets
        else:
            target_name = target.name + self.variant_suffix()

            if target.type_unique == 'library':
                if self.is_windows():
                    target_name = 'lib' + target_name

            return [target_name]

    def make_target_from_context(self, config, target):
        target_name = self.make_target_name_from_context(config, target)
        if not self.is_windows():
            target_name = ['lib' + t for t in target_name]
        result = list()
        for filename in target_name:
            for suffix in self.artifact_suffix(config, target):
                if suffix != '.dll' or not config.dlls:
                    result.append(filename + suffix)
        if '.dll' in self.artifact_suffix(config, target) and config.dlls:
            result += [dll + '.dll' for dll in config.dlls]

        for filename in config.static_targets:
            for suffix in self.artifact_suffix_mode(config=config, is_shared=False):
                if not self.is_windows():
                    filename = 'lib' + filename
                result.append(filename + suffix)
        for filename in config.shared_targets:
            for suffix in self.artifact_suffix_mode(config=config, is_shared=True):
                if not self.is_windows():
                    filename = 'lib' + filename
                if suffix != '.dll' or not config.dlls:
                    result.append(filename + suffix)
        return result


    def get_expected_files(self, config, dep, cache_dir, has_artifacts):

        expected_files = []

        json_file_path = self.get_dep_artifact_json(dep, cache_dir)
        if os.path.exists(json_file_path):
            expected_files.append(dep.name + '.json')
        else:
            expected_files.append(dep.name + '.pkl')

        if not has_artifacts:
            return expected_files
        
        dep_configs = self.read_dep_configs(dep, cache_dir)
        if dep_configs is None or dep_configs.header_only:
            return expected_files

        if dep.targets:
            for target in dep.targets:
                if not target in dep_configs.targets:
                    raise RuntimeError("Cannot find target: " + target)
            dep_configs.targets = dep.targets
        
        config = dep.merge_copy(self, [dep_configs])
        return expected_files + self.make_target_from_context(config, dep)

    def is_header_only(self, dep, cache_dir):

        dep_configs = self.read_dep_configs(dep, cache_dir)
        if dep_configs is None:
            return False
        
        return dep_configs.header_only

    def has_artifacts(self, command):
        return command in ['build', 'export']

    def dep_command(self, config, dep, cache_conf, command, enable_env):
        dep.resolve()

        cache_dir = self.find_dep_cache_dir(dep, cache_conf)

        json_path = self.get_dep_artifact_json(dep, cache_dir)
        if not os.path.exists(json_path) and command == "build":
            raise RuntimeError("Error: run golem resolve first! Can't find {}".format(json_path))

        has_artifacts = self.has_artifacts(command)

        expects_files = self.get_expected_files(config, dep, cache_dir, has_artifacts)
        is_header_only = self.is_header_only(dep, cache_dir)

        is_header_exportable_yet = command == 'build'
        is_header_not_available = is_header_exportable_yet and is_header_only and not os.path.exists(self.get_dep_include_location(dep, cache_dir))
        is_artifact_not_available = not is_header_only and not self.is_in_dep_artifact_in_cache_dir(dep, cache_dir, expects_files)

        if is_header_not_available or is_artifact_not_available:
            if cache_dir.is_static:
                raise RuntimeError("Cannot find artifacts {} for {} from the static cache location {}".format(expects_files, dep.name, cache_dir.location))
            self.run_dep_command(dep, cache_dir, command)

        self.use_dep(config, dep, cache_dir, enable_env, has_artifacts)

    def is_in_dep_artifact_in_cache_dir(self, dep, cache_dir, expects_files):
        path = self.get_dep_artifact_location(dep, cache_dir)

        is_in_artifact_dir = os.path.exists(path)
        for file in expects_files:
            is_in_artifact_dir = is_in_artifact_dir and os.path.exists(os.path.join(path, file))

        return is_in_artifact_dir


    def find_dep_cache_dir(self, dep, cache_conf):
        cache_dir = self.find_existing_dep_cache_dir(dep, cache_conf)

        if cache_dir is None:
            cache_dir = self.find_writable_cache_dir(dep, cache_conf)

        return cache_dir

    def is_dep_artifact_in_cache_dir(self, dep, cache_dir):
        path = self.get_dep_artifact_location(dep, cache_dir)
        return os.path.exists(path)

    def find_existing_dep_cache_dir(self, dep, cache_conf):
        for cache_dir in cache_conf.locations:
            if self.is_dep_artifact_in_cache_dir(dep, cache_dir):
                return cache_dir
        return None

    def find_writable_cache_dir(self, dep, cache_conf):
        for cache_dir in cache_conf.locations:
            if not cache_dir.is_static:
                return cache_dir
        raise RuntimeError("Can't find any writable cache location")

    def export_dependency(self, config, dep):
        self.dep_command(
            config, dep, self.make_cache_conf(), 'export', True)

    def link_dependency(self, config, dep):
        self.dep_command(
            config, dep, self.make_cache_conf(), 'build', True)

    def get_build_path(self):
        # return self.context.out_dir if (hasattr(self.context, 'out_dir') and self.context.out_dir) else self.context.options.out if (hasattr(self.context.options, 'out') and self.context.options.out) else ''
        return os.path.join(os.getcwd(), 'obj')

    def make_build_path(self, path):
        return os.path.join(self.get_build_path(), path)

    def make_target_out(self):
        return os.path.join('..', '..', 'bin')

    def make_out_path(self):
        return self.make_build_path(self.make_target_out())

    def make_output_path(self, path):
        return self.make_build_path(os.path.join('..', '..', path))

    def get_output_path(self):
        return self.make_output_path(".")

    def get_long_version(self, default = None):

        version_string = None
        
        try:
            version_string = subprocess.check_output(['git', 'describe', '--long', '--tags', '--dirty=-d'], cwd=self.get_project_dir())
            version_string = version_string.splitlines()[0]
            if version_string[0] == 'v':
                version_string = version_string[1:]
        except:
            version_string = default

        return version_string

    def get_version_major(self, version_string = None):

        if version_string is None:
            version_string = self.get_long_version()

        if version_string is None:
            return None

        return re.search('^([0-9]+)\\..*', version_string).group(1)

    def get_version_minor(self, version_string = None):

        if version_string is None:
            version_string = self.get_long_version()

        if version_string is None:
            return None

        return re.search('^[0-9]+\\.([0-9]+).*', version_string).group(1)

    def get_version_patch(self, version_string = None):

        if version_string is None:
            version_string = self.get_long_version()

        if version_string is None:
            return None

        return re.search('^[0-9]+\\.[0-9]+\\.([0-9]+).*', version_string).group(1)

    def get_version_revision(self, version_string = None):

        if version_string is None:
            version_string = self.get_long_version()

        if version_string is None:
            return None

        return re.search('^[0-9]+\\.[0-9]+\\.[0-9]+.(.*)', version_string).group(1)

    def get_version_hash(self, version_string = None):

        if version_string is None:
            version_string = self.get_long_version()

        if version_string is None:
            return None

        return re.search('^[0-9]+\\.[0-9]+\\.[0-9]+.(.*)', version_string).group(1)

    def get_short_version(self, version_string = None):

        if version_string is None:
            version_string = self.get_long_version()

        if version_string is None:
            return None
        
        version_major = self.get_version_major(version_string)
        version_minor = self.get_version_minor(version_string)
        version_patch = self.get_version_patch(version_string)

        return version_major + "." + version_minor + "." + version_patch

    def recursively_link_dependencies(self, config):
        self.recursively_apply_to_deps(config, self.link_dependency)

    def recursively_apply_to_deps(self, config, callback):
        deps_linked=[]
        deps_count=0
        while len(self.project.deps) != deps_count:
            deps_count = len(self.project.deps)
            for dep_name in config.deps:
                if dep_name in deps_linked:
                    continue
                for dep in self.project.deps:
                    if dep_name == dep.name:
                        callback(config, dep)
                        deps_linked.append(dep.name)

    def build_target_gather_config(self, target, static_configs):

        config = target.merge_configs(self)

        config.merge(self, static_configs)

        for use_name in config.use:
            for export in self.project.exports:
                if use_name == export.name:
                    export_config = self.merge_export_config_against_build_condition(export)
                    config.merge(self, [export_config])

        self.recursively_link_dependencies(config)
        
        targetname = self.make_target_name_from_context(config, target)[0]

        project_qt = False
        if any([feature.startswith("QT5") for feature in config.features]):
            project_qt = True

        if self.is_debug() and self.is_windows():
            for i, feature in enumerate(config.features):
                if feature.startswith("QT5"):
                    config.features[i] += "D"

        listinclude = self.list_include(self.make_project_path_array(config.includes))
        listsource = self.list_source(self.make_project_path_array(config.source)) + self.list_qt_qrc(self.make_project_path_array(config.source)) + self.list_qt_ui(self.make_project_path_array(config.source)) if project_qt else self.list_source(self.make_project_path_array(config.source))
        listmoc = self.list_moc(self.make_project_path_array(config.moc)) if project_qt else []    


        version_short = None
        version_source = []
        if target.version_template is not None:
            version_string = self.get_long_version(default='0.0.0')
            if version_string is not None:
                version_hash = self.get_version_hash(version_string)
                version_short = self.get_short_version(version_string)
                for version_template in target.version_template:
                    version_template_src = self.context.root.find_node(self.make_project_path(version_template))
                    version_template_dst = self.context.root.find_or_declare(self.make_build_path(os.path.basename(version_template) + '.cpp'))
                    self.context(
                        name			= version_template_dst,
                        features    	= 'subst',
                        source      	= version_template_src,
                        target      	= version_template_dst,
                        VERSION 		= version_string,
                        VERSION_SHORT 	= version_short,
                        VERSION_HASH	= version_hash
                    )
                    version_source.append(version_template_dst)
        
        isystemflags = []
        for key in self.context.env.keys():
            if key.startswith("INCLUDES_"):
                for path in self.context.env[key]:
                    if path.startswith('/usr'):
                        isystemflags.append('-isystem' + str(path))

        if self.is_windows():
            version_short = None

        target_type = None
        if target.type_unique == 'program' and self.is_android():
            target_type = 'library'
        else:
            target_type = target.type
            
        target_cxxflags = config.program_cxxflags if target_type == 'program' else config.library_cxxflags
        target_linkflags = config.program_linkflags if target_type == 'program' else config.library_linkflags

        stlibflags = config.stlib + (config.system if self.is_static() else [])

        if stlibflags:
            stlibflags = ['-l' + name for name in stlibflags]
            if not self.is_darwin() and self.compiler() != 'msvc':
                stlibflags = ['-Wl,-Bstatic'] + stlibflags + ['-Wl,-Bdynamic']
            
        env_cxxflags = self.context.env.CXXFLAGS
        env_defines = self.context.env.DEFINES
        env_includes = []
        for key in self.context.env.keys():
            if key.startswith("INCLUDES_"):
                for path in self.context.env[key]:
                    if not path.startswith('/usr'):
                        env_includes.append(str(path))
        env_isystem = []
        for key in self.context.env.keys():
            if key.startswith("ISYSTEM_"):
                for path in self.context.env[key]:
                    env_isystem.append(str(path))
        
        return BuildTarget(
            config          = config,

            defines			= config.defines,
            includes		= listinclude,
            source			= listsource + version_source,
            target			= os.path.join(self.make_target_out(), targetname),
            name			= target.name,
            cxxflags		= config.cxxflags + target_cxxflags + isystemflags,
            cflags			= config.cflags + target_cxxflags + isystemflags,
            linkflags		= config.linkflags + target_linkflags,
            ldflags         = stlibflags + config.ldflags,
            use				= config.use + config.features,
            uselib			= config.uselib,
            moc 			= listmoc,
            features 		= 'qt5' if project_qt else '',
            install_path 	= None,
            vnum			= version_short,
            depends_on		= version_source,
            lib             = config.lib + (config.system if self.is_shared() else []),
            libpath         = config.libpath,
            stlibpath       = config.stlibpath,
            cppflags        = config.cppflags,
            framework       = config.framework,
            frameworkpath   = config.frameworkpath,
            rpath           = config.rpath,
            cxxdeps         = config.cxxdeps,
            ccdeps          = config.ccdeps,
            linkdeps        = config.linkdeps,

            env_defines     = env_defines,
            env_cxxflags    = env_cxxflags,
            env_includes    = env_includes,
            env_isystem     = env_isystem)

    def generate_compiler_commands(self, build_target, path):

        compile_commands = []

        if os.path.exists(path):
            with open(path, 'r') as fp:
                compile_commands = byteify(json.load(fp))
        
        for source in build_target.source + self.list_moc(self.make_project_path_array(build_target.config.includes + build_target.config.source)):
            file = {
                "directory": self.get_build_path(),
                "arguments": [ "cl.exe" if Context.is_windows() else "/usr/bin/" + self.context.env.CXX_NAME ] 
                + build_target.env_cxxflags + build_target.cxxflags
                + [('/external:I' if Context.is_windows() else '-isystem') + str(d) for d in build_target.env_isystem] 
                + ['-I' + str(d) for d in build_target.env_includes] 
                + ['-I' + str(d) for d in build_target.includes] 
                + ['-D' + d for d in build_target.env_defines] 
                + ['-D' + d for d in build_target.defines]
                + [str(source), '-c'],
                "file": str(source)
            }
            compile_commands.append(file)

        with open(path, 'w') as fp:
            json.dump(compile_commands, fp, indent=4)

    def generate_vscode_config(self, compiler_commands_path):

        if self.context.options.vscode:
            from collections import OrderedDict
            data = OrderedDict({
                "configurations": [
                    {
                        "name": "Win32" if Context.is_windows() else "Linux",
                        "intelliSenseMode": "msvc-x64" if Context.is_windows() else "clang-x64",
                        "includePath": [],
                        "defines": [],
                        "compileCommands": self.make_build_path("compile_commands.json"),
                        "browse": {
                            "path": [],
                            "limitSymbolsToIncludedHeaders": True,
                            "databaseFilename": "${workspaceRoot}/.vscode/cache/.browse.VC.db"
                        }
                    }
                ]
            })
            properties_path = os.path.join(self.get_project_dir(), '.vscode', 'c_cpp_properties.json')
            with open(properties_path, 'w') as outfile:
                json.dump(data, outfile, indent=4, sort_keys=True)


    def build_target(self, target, static_configs):

        build_target = self.build_target_gather_config(target, static_configs)

        compiler_commands_path = self.make_build_path("compile_commands.json")
        self.generate_compiler_commands(build_target, compiler_commands_path)
        self.generate_vscode_config(compiler_commands_path)

        build_fun = None

        if target.type_unique == 'program' and self.is_android():
            build_fun = self.context.shlib
        elif target.type_unique == 'library':
            if target.link:
                if target.link_unique == 'shared':
                    build_fun = self.context.shlib
                elif target.link_unique == 'static':
                    build_fun = self.context.stlib
                else:   
                    raise Exception("ERROR: Bad link option {}".format(target.link_unique))
            elif self.is_shared():
                build_fun = self.context.shlib
            elif self.is_static():
                build_fun = self.context.stlib
            else:
                raise Exception("ERROR: Bad link option {}".format(self.context.options.link))
        elif target.type_unique == 'program':
            build_fun = self.context.program
        elif target.type_unique == 'objects':
            build_fun = self.context.objects
        else:
            raise Exception("ERROR: Bad target type {}".format(target.type_unique))

        build_fun(
            defines = build_target.defines,
            includes = build_target.includes,
            source = build_target.source,
            target = build_target.target,
            name = build_target.name,
            cxxflags = build_target.cxxflags,
            cflags = build_target.cflags,
            linkflags = build_target.linkflags,
            ldflags = build_target.ldflags,
            use = build_target.use,
            uselib = build_target.uselib,
            moc = build_target.moc,
            features = build_target.features,
            install_path = build_target.install_path,
            vnum = build_target.vnum,
            depends_on = build_target.depends_on,
            lib = build_target.lib,
            libpath = build_target.libpath,
            stlibpath = build_target.stlibpath,
            cppflags = build_target.cppflags,
            framework = build_target.framework,
            frameworkpath = build_target.frameworkpath,
            rpath = build_target.rpath,
            cxxdeps = build_target.cxxdeps,
            ccdeps = build_target.ccdeps,
            linkdeps = build_target.linkdeps
        )

    def cppcheck_target(self, target, static_configs):

        build_target = self.build_target_gather_config(target, static_configs)

        all_includes = build_target.env_isystem + build_target.env_includes + build_target.includes
        all_includes = ['-I' + str(d) for d in all_includes]

        all_defines = build_target.env_defines + build_target.defines
        all_defines = ['-D' + str(d) for d in all_defines]

        all_sources = build_target.source
        all_sources = [str(d) for d in all_sources]

        cppcheck_dir = self.make_build_path("cppcheck")
        helpers.make_directory(cppcheck_dir)

        command = [
            'cppcheck',
            '--enable=all',
            '--suppress=missingIncludeSystem',
            '--quiet'
        ] + all_defines + all_includes + all_sources

        self.context(rule=' '.join(command), always=True, name=target.name, cwd=cppcheck_dir)
            
    def call_build_target(self, build_target_fun):
        static_configs = self.project.read_configurations(self)
        
        for target in self.project.targets:
            build_target_fun(target, static_configs)

    def cppcheck(self):
        self.call_build_target(self.cppcheck_target)

    def clang_tidy_target(self, target, static_configs):

        build_target = self.build_target_gather_config(target, static_configs)

        clang_tidy_dir = self.make_build_path("clang-tidy")
        helpers.make_directory(clang_tidy_dir)

        compiler_commands_path = os.path.join(clang_tidy_dir, "compile_commands.json")
        self.generate_compiler_commands(build_target, compiler_commands_path)

        command = [
            'clang-tidy',
            '--checks=*',
            '-p=' + str(clang_tidy_dir)
        ]

        command += [str(s) for s in build_target.source]

        self.context(rule=' '.join(command), always=True, name=target.name, cwd=clang_tidy_dir)


    def clang_tidy(self):
        self.call_build_target(self.clang_tidy_target)
        
    def run_command_with_msvisualcpp(self, command, cwd):
        cmd = ['cmd', '/c', 'vswhere', '-latest',
            '-products', '*', '-property', 'installationPath']
        print ' '.join(cmd)
        ret = subprocess.Popen(cmd, cwd='C:\\Program Files (x86)\\Microsoft Visual Studio\\Installer',
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = ret.communicate()
        if ret.returncode:
            print "ERROR: " + ' '.join(cmd)
            return -1
        lines = out.splitlines()
        if not lines[0]:
            return 1
        msvc_path = lines[0]

        vcvars = msvc_path + '\\VC\\Auxiliary\\Build\\vcvarsall.bat'
        call_msvc = ['call', '"' + vcvars + '"',
                     self.context.env['MSVC_TARGETS'][0], '&&']

        cmd = call_msvc + command

        build_cmd = ' '.join(cmd)
        if subprocess.call(build_cmd, cwd=cwd, shell=True):
            return 1
    
    def run_command(self, command, cwd):
        if subprocess.call(command, cwd=cwd, shell=self.is_windows()):
            return 1
    
    def run_build_command(self, command, cwd):
        if self.is_windows():
            ret = self.run_command_with_msvisualcpp(command=command, cwd=cwd)
        else:
            ret = self.run_command(command=command, cwd=cwd)
        if ret:
            print("Error when running command \"" + ' '.join(command) + "\" in directory \"" + str(cwd) + "\"")
            return 1

    def find_artifacts(self, path, recursively=False):
        files_grabbed = []
        types = ('*.pdb', '*.dll', '*.lib', '*.a', '*.so', '*.so.*', '*.dylib', '*.dylib.*')
        if recursively == False:
            for files in types:
                files_grabbed.extend(
                    glob.glob(os.path.join(path, files)))
            return files_grabbed
        else:
            for files in types:
                for root, _, filenames in os.walk(path):
                    for filename in fnmatch.filter(filenames, files):
                        files_grabbed.append(os.path.join(root, filename))
        return files_grabbed

    def copy_binary_artifacts(self, source_path, destination_path, recursively=False):

        files = self.find_artifacts(source_path, recursively)

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
            include_path='include'
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
        distutils.dir_util.copy_tree(source_path, os.path.join(include_dir, helpers.directory_basename(source_path)), preserve_symlinks=1)

    def export_file_to_headers(self, file_path, include_path=None):
        print("Exporting header file")

        include_dir = self.prepare_include_export(include_path)

        if not os.path.exists(file_path):
            raise Exception("Error: Can't find header " + str(file_path))

        print("Copy file {}".format(file_path))
        helpers.copy_file(file_path, include_dir)

    def cmake_build(self, source_path=None, build_path=None, targets=None, variant=None, link=None, arch=None, options=None, install_prefix=None, prefix_path=None):
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

        cmake_command = ['cmake', source_path] + opt_arch + [opt_variant, opt_link] + opt_install_prefix + opt_prefix_path + opt_options

        print("Run CMake command: " + ' '.join(cmake_command))

        ret = self.run_build_command(command=cmake_command, cwd=build_path)
        if ret:
            raise RuntimeError("Error when running CMake command: " + ' '.join(cmake_command))

        if targets is None:
            targets = []
        else:
            targets = ['--target'] + targets

        cmake_command = ['cmake', '--build', '.', '--config', variant] + targets
        print("Run build command: " + ' '.join(cmake_command))

        ret = self.run_command(command=cmake_command, cwd=build_path)
        if ret:
            raise RuntimeError("Error when running CMake command: " + ' '.join(cmake_command))

        if install_prefix is not None:
            if not self.is_windows():
                cmake_command = ['make', 'install']
                print("Run install command: " + ' '.join(cmake_command))

                ret = self.run_command(command=cmake_command, cwd=build_path)
                if ret:
                    raise RuntimeError("Error when running CMake command: " + ' '.join(cmake_command))
            else:
                raise Exception("CMake install command not implemented on Windows")

    def save_options(self):
        self.context.env.OPTIONS = json.dumps(self.context.options.__dict__)
    
    def restore_options_env(self, env):
        def ascii_encode_dict(data):
            ascii_encode = lambda x: x.encode('ascii') if isinstance(x, unicode) else x
            return dict(map(ascii_encode, pair) for pair in data.items())
        options = json.loads(env.OPTIONS, object_hook=ascii_encode_dict)
        if not self.context.targets:
            self.context.targets = options['targets']
        else:
            options['targets'] = self.context.targets
        return options
    
    def restore_options(self):
        self.context.options.__dict__ = self.restore_options_env(self.context.env)

    def ensures_qt_is_installed(self):
        if not self.context.options.qtdir and self.is_linux() and self.distribution() == 'debian' and self.release() == 'stretch':
            self.requirements_debian_install([
                'qt5-default',
                'qtwebengine5-dev',
                'libqt5x11extras5-dev',
                'qtbase5-private-dev'
            ])


    def make_android_ndk_path(self, path = None):
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
        path_to_android_compiler_base = os.path.join('toolchains/llvm/prebuilt/', anrdoid_current_host, 'bin')

        android_arch = self.make_android_arch()
        android_ndk_platform = self.make_android_ndk_platform()

        if android_arch == default_arch:
            path_to_android_compiler = os.path.join(path_to_android_compiler_base, default_compiler)
        else:
            path_to_android_compiler = os.path.join(path_to_android_compiler_base, android_arch + 'linux-androideabi' + android_ndk_platform + '-clang++')

        path_to_android_compiler = os.path.join(android_ndk_path, path_to_android_compiler)

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

        if 'ANDROID_NDK_PLATFORM' in os.environ and os.environ['ANDROID_NDK_PLATFORM']:
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

        if 'ANDROID_SDK_PLATFORM' in os.environ and os.environ['ANDROID_SDK_PLATFORM']:
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

        if 'CXX' in os.environ and os.environ['CXX']: # Pull in the compiler
            self.context.env.CXX = os.environ['CXX'] # override default

    def make_android_toolchain_target(self):
        return "aarch64-none-linux-android"

    def make_android_toolchain_version(self):
        return "4.9"

    def make_android_toolchain_target_directory(self):
        return "aarch64-linux-android-" + self.make_android_toolchain_version()

    def make_android_toolchain_include_directory(self):
        return "aarch64-linux-android"

    def make_android_toolchain_path(self):

        toolchain_target_arch_directory= self.make_android_toolchain_target_directory()
        toolchain_host_directory = self.make_android_ndk_host()
        toolchain_path = os.path.join("toolchains", toolchain_target_arch_directory, "prebuilt", toolchain_host_directory)

        return self.make_android_ndk_path(toolchain_path)

    def make_android_platform_arch_name(self):
        return "arch-arm64"

    def make_android_sysroot_path_for_linker(self):
        return self.make_android_ndk_path(os.path.join("platforms", "android-" + self.make_android_ndk_platform(), self.make_android_platform_arch_name()))

    def append_android_cxxflags(self):
        if not self.is_android():
            return

        flags = [
            "-D__ANDROID_API__=" + self.make_android_ndk_platform(),
            "-target", self.make_android_toolchain_target(),
            "-gcc-toolchain", self.make_android_toolchain_path(),
            "-DANDROID_HAS_WSTRING",
            "--sysroot=" + self.make_android_ndk_path("sysroot"),
            "-isystem", self.make_android_ndk_path("sysroot/usr/include/" + self.make_android_toolchain_include_directory()),
            "-isystem", self.make_android_ndk_path("sources/cxx-stl/llvm-libc++/include"),
            "-isystem", self.make_android_ndk_path("sources/android/support/include"),
            "-isystem", self.make_android_ndk_path("sources/cxx-stl/llvm-libc++abi/include"),
            "-fstack-protector-strong",
            "-DANDROID",
        ]

        if self.project.qt and os.path.exists(self.context.options.qtdir):
            flags += [
                "-I" + os.path.join(self.context.options.qtdir, "mkspecs/android-clang")
            ]

        self.context.env.CXXFLAGS += flags
        self.context.env.CFLAGS += flags

    def append_android_linkflags(self):
        if not self.is_android():
            return

        self.context.env.LINKFLAGS += [
            "-D__ANDROID_API__=" + self.make_android_ndk_platform(),
            "-target", self.make_android_toolchain_target(),
            "-gcc-toolchain", self.make_android_toolchain_path(),
            "-Wl,--exclude-libs,libgcc.a",
            "--sysroot=" + self.make_android_sysroot_path_for_linker()
        ]

    def make_android_arch_hyphens(self):
        return self.make_android_arch().replace('_', '-')

    def append_android_ldflags(self):
        if not self.is_android():
            return

        android_libs_path = self.make_android_ndk_path("sources/cxx-stl/llvm-libc++/libs/" + self.make_android_arch_hyphens())
        self.context.env.LDFLAGS += [
            "-L" + android_libs_path,
            os.path.join(android_libs_path, "libc++.so." + self.make_android_ndk_platform()),
        ]

    def package_android(self, package):

        self.check_android_sdk_path()
        self.check_android_sdk_platform()
        self.check_android_jdk_path()
        assert self.context.options.qtdir != '' and os.path.exists(self.context.options.qtdir)
        
        print("Check package's targets")
        targets_to_process = self.get_targets_to_process(package.targets)
        config = self.resolve_global_config(targets_to_process)
        depends = config.packages

        assert len(targets_to_process) == 1

        target_binaries = []
        for target in targets_to_process:
            target_binaries += self.make_target_from_context(config, target)

        target_binary = None
        for target in target_binaries:
            if str(target).endswith('.so') or str(target).endswith('.dll') or str(target).endswith('.dylib'):
                target_binary = os.path.join(self.make_out_path(), target)
        assert target_binary is not None

        target_dependencies = []
        for target in self.get_targets_to_process(config.use):
            for target_name in self.make_target_from_context(config, target):
                if str(target_name).endswith('.so') or str(target_name).endswith('.dll') or str(target_name).endswith('.dylib'):
                    target_dependencies.append(os.path.join(self.make_out_path(), target_name))

        for dep_name in config.deps:
            for dep in self.project.deps:
                if dep_name == dep.name:
                    if str(dep_name).endswith('.so') or str(dep_name).endswith('.dll') or str(dep_name).endswith('.dylib'):
                        target_dependencies.append(os.path.join(self.make_out_path(), self.make_target_from_context(config, dep)))

        # Don't run this script as root

        print("Gather package metadata")
        package_name = package.name
        package_description = package.description

        print("Clean-up")
        package_directory = self.make_output_path('dist')
        remove_tree(self, package_directory)

        # Strip binaries, libraries, archives

        print("Prepare package")
        package_directory = make_directory(os.path.join(package_directory, package_name))
        bin_directory = make_directory(package_directory, os.path.join('libs', self.make_android_arch_hyphens()))

        print("Copying " + str(self.make_out_path()) + " to " + str(bin_directory))
        copy_file(target_binary, bin_directory)
        for target in target_dependencies:
            copy_file(target, bin_directory)

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

        from collections import OrderedDict
        data = OrderedDict({
            "description": package_description,	# One sentence description
            "qt": qt_path,
            "sdk": sdk_path,
            "sdkBuildToolsRevision": self.make_android_sdk_build_tools_version(),
            "ndk": ndk_path,
            "toolchain-prefix": "llvm",
            "tool-prefix": "llvm",
            "toolchain-version": self.make_android_toolchain_version(),
            "ndk-host": self.make_android_ndk_host(),
            "target-architecture": self.make_android_arch_hyphens(),
            "android-extra-libs": ",".join(extra_libs),
            "stdcpp-path": self.make_android_ndk_path("sources/cxx-stl/llvm-libc++/libs/" + self.make_android_arch_hyphens() + "/libc++_shared.so"),
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
            '--input', android_package_file,
            '--output', package_directory,
            '--android-platform', 'android-' + self.make_android_sdk_platform(),
            '--jdk', self.make_android_jdk_path(),
            '--gradle'
        ]

        if self.is_release() and False:
            command += [
                "--sign", "",
                "--storepass", "",
                "--keypass", ""
            ]
        helpers.run_task(command, cwd=self.get_output_path())


    def configure(self):

        # features list
        features_to_load = ['compiler_c', 'compiler_cxx']

        # qt check
        if self.project.qt:
            self.ensures_qt_is_installed()
            features_to_load.append('qt5')
            if os.path.exists(self.project.qtdir):
                self.context.options.qtdir = self.project.qtdir

        # configure x86 context
        self.context.setenv('x86')
        self.configure_compiler()
        if self.is_windows():
            # self.context.env.MSVC_VERSIONS = ['msvc 14.0']
            self.context.env.MSVC_TARGETS = ['x86']
        self.context.load(features_to_load)
        self.save_options()
        
        if self.is_debug() and self.is_windows():
            for key in self.context.env.keys():
                if key.startswith("INCLUDES_QT5"):
                    paths = []
                    for path in self.context.env[key]:
                        if path.endswith('d'):
                            paths.append(path[:-1])
                        else:
                            paths.append(path)
                    self.context.env[key] = paths

        # configure x64 context
        self.context.setenv('x64')
        self.configure_compiler()
        if self.is_windows():
            # self.context.env.MSVC_VERSIONS = ['msvc 14.0']
            self.context.env.MSVC_TARGETS = ['x86_amd64'] # means x64 when using visual studio express for desktop
        self.context.load(features_to_load)
        self.save_options()

        if self.is_debug() and self.is_windows():
            for key in self.context.env.keys():
                if key.startswith("INCLUDES_QT5"):
                    paths = []
                    for path in self.context.env[key]:
                        if path.endswith('d'):
                            paths.append(path[:-1])
                        else:
                            paths.append(path)
                    self.context.env[key] = paths

    def build_path(self, dep = None):
        return self.osname() + '-' + self.arch_min() + '-' + self.compiler_min() + '-' + self.runtime_min() + '-' + self.link_min(dep) + '-' + self.variant_min()

    def find_dependency_includes(self, dep_name):
        dep_include = []
        cache_conf = self.make_cache_conf()
        for dep in self.project.deps:
            if dep_name == dep.name:
                cache_dir = self.find_dep_cache_dir(dep, cache_conf)
                dep_include.append(self.get_dep_include_location(dep, cache_dir))
        return dep_include

    def build_dependency(self, dep_name):
        config = Configuration()
        config.deps = [dep_name]
        self.recursively_link_dependencies(config)
        return config

    def build(self):

        if os.path.exists(self.make_build_path('compile_commands.json')):
            os.remove(self.make_build_path('compile_commands.json'))

        self.call_build_target(self.build_target)

        if self.module is not None:
            ret = self.module.script(self)
            if ret:
                raise Exception("Build fail!")

        for targetname in self.context.options.targets.split(','):
            if targetname and not targetname in [target.name for target in self.project.targets]:
                if self.is_windows():
                    self.context(rule="type nul >> ${TGT}", target=targetname)
                else:
                    self.context(rule="touch ${TGT}", target=targetname)

    def get_asked_exports(self):
        return self.context.options.targets.split(',') if self.context.options.targets else [target.name for target in self.project.exports]

    def find_dep(self, name):
        found_dep = None
        for dep in self.project.deps:
            if dep.name == name:
                found_dep = dep
                break
        return found_dep
    
    def find_dep_cache_include(self, dep):
        cache_dir = self.find_dep_cache_dir(dep, self.make_cache_conf())
        return self.get_dep_include_location(dep, cache_dir)

    def merge_export_config_against_build_condition(self, export, exporting=False):
        found_build_target = None
        for build_target in self.project.targets:
            if build_target.name == export.name:
                found_build_target = build_target
        return export.merge_configs(self, condition=found_build_target, exporting=exporting)

    def export(self):
        targets = self.get_asked_exports()
        for export in self.project.exports:
            if export.name in targets:

                config = self.merge_export_config_against_build_condition(export, exporting=True)

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
                    distutils.dir_util.copy_tree(self.make_project_path(include), outpath_include)

                outpath_lib = os.path.join(outpath, self.build_path())
                if not os.path.exists(outpath_lib):
                    os.makedirs(outpath_lib)

                out_path = self.make_out_path()
                if os.path.exists(out_path):
                    copy_tree(self.make_out_path(), outpath_lib)

    def resolve_local_configs(self, targets):
        configs = dict()
        for target in targets:

            config = target.merge_configs(self, exporting=True)

            for use_name in config.use:
                for export in self.project.exports:
                    if use_name == export.name:
                        export_config = self.merge_export_config_against_build_condition(export)
                        config.merge(self, [export_config], exporting=True)

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
            
            if target.export and self.context.options.export:
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
        for _, config in configs.items():
            master_config.merge(self, [config], exporting=True)
        return master_config

    def resolve_recursively(self):
        targets_to_process = self.get_targets_to_process()
        configs = self.resolve_configs_recursively(targets_to_process)

        outpath = self.context.options.export
        outpath_lib = os.path.join(outpath, self.build_path())
        if not os.path.exists(outpath_lib):
            os.makedirs(outpath_lib)
        
        for target in targets_to_process:
            config = configs[target.name]

            config.includes = []
            outpath_include = os.path.join(outpath, 'include')
            config.includes.append(outpath_include)

            outpath_target = os.path.join(outpath_lib, target.name + '.json')
            outpath_directory = os.path.dirname(outpath_target)
            if not os.path.exists(outpath_directory):
                os.makedirs(outpath_directory)

            with open(outpath_target, 'w') as output:
                target_configuration_file = TargetConfigurationFile(project=self.project, configuration=config)
                json.dump(target_configuration_file, output, default=TargetConfigurationFile.serialize_to_json,
                          sort_keys=True, indent=4)

    def get_targets_or_exports(self):
        return self.project.targets if not self.context.options.export else self.project.exports

    def get_targets_to_process(self, asked_targets = None):
        if asked_targets is None:
            asked_targets = self.get_asked_targets()

        targets_to_process = []
        for asked_target in asked_targets:
            found_targets = [available_target for available_target in self.get_targets_or_exports() if asked_target == available_target.name]
            if found_targets:
                targets_to_process.append(found_targets[0])
            else:
                raise RuntimeError("Can't find any target configuration named \"{}\"".format(asked_target))
        return targets_to_process

    def get_asked_targets(self):
        return self.context.options.targets.split(',') if self.context.options.targets else [target.name for target in self.get_targets_or_exports()]

    def get_packages_to_process(self, asked_packages = None):
        if asked_packages is None:
            asked_packages = self.get_asked_packages()

        packages_to_process = []
        for asked_package in asked_packages:
            found_packages = [available_package for available_package in self.project.packages if asked_package == available_package.name]
            if found_packages:
                packages_to_process.append(found_packages[0])
            else:
                raise RuntimeError("Can't find any package configuration named \"{}\"".format(asked_package))
        return packages_to_process

    def get_asked_packages(self):
        return self.context.options.packages.split(',') if self.context.options.packages else [package.name for package in self.project.packages]

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
        installed_packages = subprocess.check_output(['dpkg', '-l'])
        for package in packages:
            if installed_packages.find(package) == -1:
                packages_to_install.append(package)
            else:
                found_installed_packages.append(package)
        
        if len(found_installed_packages) > 0:
            print('Found already installed packages: {}'.format(found_installed_packages))

        if len(packages_to_install) > 0:
            print('Install the following packages: {}'.format(packages_to_install))
            helpers.run_task(['sudo', 'apt', 'install', '-y'] + packages_to_install)
        else:
            print('Nothing to install')

    def requirements_debian(self):
        targets_to_process = self.get_targets_to_process()
        config = self.resolve_global_config(targets_to_process)
        packages = config.packages_dev if len(config.packages_dev) > 0 else config.packages

        self.requirements_debian_install(packages)

        print('Done')

    def dependencies(self):
        targets_to_process = self.get_targets_to_process()
        self.build_local_dependencies(targets_to_process)

    def package(self):

        print("Check asked package")

        packages_to_process = self.get_packages_to_process()
        
        for package in packages_to_process:
            if self.is_android():
                self.package_android(package)
            elif self.is_windows():
                self.package_windows(package)
            elif self.is_darwin():
                self.package_darwin(package)
            elif self.is_linux():
                self.package_debian(package)

    def package_windows(self, package):
        raise RuntimeError("Not implemented yet")

    def package_darwin(self, package):
        raise RuntimeError("Not implemented yet")

    def package_debian(self, package):

        print("Check package's targets")

        targets_to_process = self.get_targets_to_process(package.targets)
        config = self.resolve_global_config(targets_to_process)
        depends = config.packages

        # Don't run this script as root

        print("Gather package metadata")
        prefix = "/usr/local" if package.prefix is None else package.prefix

        package_name = package.name
        package_section = package.section
        package_priority = package.priority
        package_maintainer = package.maintainer
        package_description = package.description
        package_homepage = package.homepage

        package_version = self.get_long_version(default='0.0.0')
        package_arch = self.get_arch_for_linux()
        package_depends = ', '.join(depends)

        print("Clean-up")
        package_directory = self.make_output_path('dist')
        remove_tree(self, package_directory)

        # Install documentation

        # Compression man pages

        # Copy systemd unit if any

        # Strip binaries, libraries, archives

        print("Prepare package")
        package_directory = make_directory(package_directory)

        prefix_directory = make_directory(package_directory, '.' + prefix)

        bin_directory = make_directory(prefix_directory, 'bin')

        print("Copying " + str(self.make_out_path()) + " to " + str(bin_directory))
        copy_tree(self.make_out_path(), bin_directory)

        debian_directory = make_directory(package_directory, 'DEBIAN')

        control_path = os.path.join(debian_directory, 'control')
        with open(control_path, 'w') as control_file:
            control_file.writelines([
                    "Package: " + package_name + '\n',				# Foo
                    "Version: " + package_version + '\n',			# 0.1.2
                    "Section: " + package_section + '\n',			# misc
                    "Priority: " + package_priority + '\n',			# { optional | ... }
                    "Architecture: " + package_arch + '\n',			# amd64, i386
                    "Depends: " + package_depends + '\n',			# list, of, dependencies, as, package, names
                    "Maintainer: " + package_maintainer + '\n',		# { Company | Firstname LASTNAME }
                    "Description: " + package_description + '\n',	# One sentence description
                    "Homepage: " + package_homepage + '\n'			# https://company.com/
                ])

        print("Build package")
        output_filename = package_name + '_' + package_version + "_" + package_arch
        helpers.run_task(['fakeroot', 'dpkg-deb', '--build', package_directory, output_filename + '.deb'], cwd=self.get_output_path())
