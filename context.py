import os
import io
import re
import sys
import md5
import json
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
from helpers import *

class Context:
    def __init__(self, context):
        self.context = context
        self.module = Module(self.get_project_dir())
        self.project = self.module.project()

    def resolve(self):
        deps_cache_file = self.make_build_path('deps.cache')
        if os.path.exists(deps_cache_file):
            print 'Found deps.cache'
            cache = None
            with io.open(deps_cache_file, 'rb') as file:
                cache = pickle.load(file)
            self.project.deps_load(cache)
        else:
            print 'No deps.cache'
            cache = self.project.deps_resolve()
            make_directory(os.path.dirname(deps_cache_file))
            with io.open(deps_cache_file, 'wb') as file:
                pickle.dump(cache, file)

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
        cache_dir = self.context.options.cache_dir
        if not os.path.isabs(cache_dir):
            cache_dir = os.path.join(self.get_project_dir(), cache_dir)
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
        return [self.context.root.find_dir(x) if os.path.isabs(x) else self.context.srcnode.find_dir(x) for x in includes]

    def list_source(self, source):
        return [item for sublist in [self.context.root.find_dir(x).ant_glob('*.cpp') if os.path.isabs(x) else self.context.srcnode.find_dir(x).ant_glob('*.cpp') for x in source] for item in sublist]

    def list_moc(self, source):
        return [item for sublist in [self.context.root.find_dir(x).ant_glob('*.hpp') if os.path.isabs(x) else self.context.srcnode.find_dir(x).ant_glob('*.hpp') for x in source] for item in sublist]

    def list_qt_qrc(self, source):
        return [item for sublist in [self.context.root.find_dir(x).ant_glob('*.qrc') if os.path.isabs(x) else self.context.srcnode.find_dir(x).ant_glob('*.qrc') for x in source] for item in sublist]

    def list_qt_ui(self, source):
        return [item for sublist in [self.context.root.find_dir(x).ant_glob('*.ui') if os.path.isabs(x) else self.context.srcnode.find_dir(x).ant_glob('*.ui') for x in source] for item in sublist]

    @staticmethod
    def link_static():
        return 'static'
        
    @staticmethod
    def link_shared():
        return 'shared'
        
    def link(self):
        return self.context.options.link

    def distribution(self):
        if self.is_linux():
            return platform.linux_distribution()[0].lower()
        return None


    def release(self):
        if self.is_linux():
            import lsb_release
            return lsb_release.get_distro_information()['CODENAME'].lower()
        return None

    def link_min(self):
        return self.link()[:2]

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

    def artifact_suffix(self, config):
        if config.type == 'library':
            if self.is_shared():
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
        else:
            if self.is_windows():
                return ['.exe']
            else:
                return []

    def dev_artifact_suffix(self):
        if self.is_shared():
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
    def is_windows():
        return sys.platform.startswith('win32')

    @staticmethod
    def is_linux():
        return sys.platform.startswith('linux')

    @staticmethod
    def is_darwin():
        return sys.platform.startswith('darwin')

    @staticmethod
    def osname():
        osname = ''
        if Context.is_windows():
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
        context.load('compiler_cxx qt5')
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
            # Compiler Options https://msdn.microsoft.com/en-us/library/fwkeyyhe.aspx
            # Linker Options https://msdn.microsoft.com/en-us/library/y0zzbyt4.aspx

            # self.context.env.MSVC_VERSIONS = ['msvc 14.0']
            # self.context.env.CXXFLAGS.append('/MP') # compiles multiple source files by using multiple processes
            self.context.env.CXXFLAGS.append('/Gm-') # disable minimal rebuild
            self.context.env.CXXFLAGS.append('/Zc:inline') # compiler does not emit symbol information for unreferenced COMDAT functions or data
            self.context.env.CXXFLAGS.append('/Zc:forScope') # implement standard C++ behavior for for loops 
            self.context.env.CXXFLAGS.append('/Zc:wchar_t') # wchar_t as a built-in type 
            self.context.env.CXXFLAGS.append('/fp:precise') # improves the consistency of floating-point tests for equality and inequality 
            self.context.env.CXXFLAGS.append('/W4') # warning level 4
            self.context.env.CXXFLAGS.append('/sdl') # enables a superset of the baseline security checks provided by /GS
            self.context.env.CXXFLAGS.append('/GS') # detects some buffer overruns that overwrite things
            self.context.env.CXXFLAGS.append('/EHsc') # enable exception
            self.context.env.CXXFLAGS.append('/nologo') # suppress startup banner
            self.context.env.CXXFLAGS.append('/Gd') # specifies default calling convention
            self.context.env.CXXFLAGS.append('/analyze-') # disable code analysis
            self.context.env.CXXFLAGS.append('/WX-') # warnings are not treated as errors 
            self.context.env.CXXFLAGS.append('/FS') # serialized writes to the program database (PDB)
            # self.context.env.CXXFLAGS.append('/Fd:testing.pdb') # file name for the program database (PDB) defaults to VCx0.pdb
            
            self.context.env.CXXFLAGS.append('/std:c++latest') # enable all features as they become available, including feature removals
            self.context.env.CXXFLAGS.append('/bigobj')

            self.context.env.CXXFLAGS.append('/experimental:external') # enable use of /external:I
            
            self.context.env.LINKFLAGS.append('/errorReport:none') # do not send CL crash reports
            # self.context.env.LINKFLAGS.append('/OUT:"D:.dll"') # specifies the output file name
            # self.context.env.LINKFLAGS.append('/PDB:"D:.pdb"') # creates a program database (PDB) file
            # self.context.env.LINKFLAGS.append('/IMPLIB:"D:.lib"')
            # self.context.env.LINKFLAGS.append('/PGD:"D:.pgd"') # specifies a .pgd file for profile-guided optimizations
            self.context.env.LINKFLAGS.append('/NXCOMPAT') # tested to be compatible with the Windows Data Execution Prevention feature
            self.context.env.LINKFLAGS.append('/DYNAMICBASE') # generate an executable image that can be randomly rebased at load time 
            self.context.env.LINKFLAGS.append('/NOLOGO') # suppress startup banner
            self.context.env.MSVC_MANIFEST = False # disable waf manifest behavior
            # self.context.env.LINKFLAGS.append('/MANIFEST') # creates a side-by-side manifest file and optionally embeds it in the binary
            # self.context.env.LINKFLAGS.append('/MANIFESTUAC:"level=\'asInvoker\' uiAccess=\'false\'"')
            # self.context.env.LINKFLAGS.append('/ManifestFile:".dll.intermediate.manifest"')
            # self.context.env.LINKFLAGS.append('/SUBSYSTEM') # how to run the .exe file
            # self.context.env.LINKFLAGS.append('/DLL') # builds a DLL
            # self.context.env.LINKFLAGS.append('/TLBID:1') # resource ID of the linker-generated type library
            
            self.context.env.ARFLAGS.append('/NOLOGO')

            if self.is_x86():
                self.context.env.LINKFLAGS.append('/MACHINE:X86')
                self.context.env.ARFLAGS.append('/MACHINE:X86')
            else:
                self.context.env.LINKFLAGS.append('/MACHINE:X64')
                self.context.env.ARFLAGS.append('/MACHINE:X64')
                
            if self.is_x86():
                self.context.env.MSVC_TARGETS = ['x86']
            else:
                self.context.env.MSVC_TARGETS = ['x86_amd64'] # means x64 when using visual studio express for desktop
            
        else:
            if self.is_x86() == 'x86':
                self.context.env.CXXFLAGS.append('-m32')
            else:
                self.context.env.CXXFLAGS.append('-m64')

            self.context.env.CXXFLAGS.append('-std=c++17')

            self.context.env.CXXFLAGS += '-pedantic -Wall -Wextra -Wno-unused -Wcast-align -Wcast-qual -Wstrict-overflow=5 -Wlogical-op -Winline -Winit-self -Wswitch-default -Wswitch-enum -Wundef -Wredundant-decls -Wshadow -Wsign-conversion -Wsign-promo -Wold-style-cast -Woverloaded-virtual -Wdisabled-optimization -Wpointer-arith -Wwrite-strings -Wctor-dtor-privacy -Wformat=2 -Wmissing-declarations'.split()
            # FIX: Check the project configuration scaffolded with golem using -Wmissing-include-dirs

            self.context.env.CXXFLAGS.append('-pthread')
            self.context.env.LINKFLAGS.append('-pthread')
        
        if self.is_darwin():
            self.context.env.env.CXX	= ['clang++']
            self.context.env.CXXFLAGS.append('-stdlib=libc++')
            self.context.env.LINKFLAGS.append('-stdlib=libc++')

    def configure_debug(self):
        if self.is_windows():

            self.context.env.CXXFLAGS.append('/RTC1') # run-time error checks (stack frame & uninitialized used variables)
            # self.context.env.CXXFLAGS.append('/ZI') # produces a program database in a format that supports the Edit and Continue feature.
            self.context.env.CXXFLAGS.append('/Z7') # embeds the program database
            self.context.env.CXXFLAGS.append('/Od') # disable optimizations
            self.context.env.CXXFLAGS.append('/Oy-') # speeds function calls (should be specified after others /O args)

            if self.is_static():
                self.context.env.CXXFLAGS.append('/MTd')
            elif self.is_shared():
                self.context.env.CXXFLAGS.append('/MDd')

            self.context.env.LINKFLAGS.append('/MAP') # creates a mapfile
            self.context.env.LINKFLAGS.append('/MAPINFO:EXPORTS') # includes exports information in the mapfile
            self.context.env.LINKFLAGS.append('/DEBUG') # creates debugging information
            self.context.env.LINKFLAGS.append('/INCREMENTAL') # incremental linking

        else:
            self.context.env.CXXFLAGS.append('-g3')
            self.context.env.CXXFLAGS.append('-O0')

            self.context.env.CXXFLAGS += '-fprofile-arcs -ftest-coverage --coverage -fno-inline -fno-inline-small-functions -fno-default-inline -fno-elide-constructors'.split()
            self.context.env.LINKFLAGS.append('--coverage')

        self.context.env.DEFINES.append('DEBUG')

    def configure_release(self):
        if self.is_windows():
        
            # self.context.env.CXXFLAGS.append('/Zi') # produces a program database (PDB) does not affect optimizations

            # About COMDATs, linker requires that functions be packaged separately as COMDATs to EXCLUTE or ORDER individual functions in a DLL or .exe file.
            self.context.env.CXXFLAGS.append('/Gy') # allows the compiler to package individual functions in the form of packaged functions (COMDATs)
                                            
            self.context.env.CXXFLAGS.append('/GL') # enables whole program optimization
            self.context.env.CXXFLAGS.append('/O2') # generate fast code
            self.context.env.CXXFLAGS.append('/Oi') # request to the compiler to replace some function calls with intrinsics
            self.context.env.CXXFLAGS.append('/Oy-') # speeds function calls (should be specified after others /O args)

            if self.is_static():
                self.context.env.CXXFLAGS.append('/MT')
            elif self.is_shared():
                self.context.env.CXXFLAGS.append('/MD')

            # self.context.env.LINKFLAGS.append('/DEF:"D:.def"')
            self.context.env.LINKFLAGS.append('/LTCG') # perform whole-program optimization
            # self.context.env.LINKFLAGS.append('/LTCG:incremental') # perform incremental whole-program optimization
            self.context.env.ARFLAGS.append('/LTCG')
            self.context.env.LINKFLAGS.append('/OPT:REF') # eliminates functions and data that are never referenced
            self.context.env.LINKFLAGS.append('/OPT:ICF') # to perform identical COMDAT folding
            if self.is_x86():
                self.context.env.LINKFLAGS.append('/SAFESEH') # image will contain a table of safe exception handlers

        else:
            self.context.env.CXXFLAGS.append('-O3')

    def environment(self):
        
        # load all environment variables
        self.context.load_envs()

        # set environment variables according architecture
        if self.is_x86():
            self.context.env = self.context.all_envs['x86'].derive()
        else:
            self.context.env = self.context.all_envs['x64'].derive()

        # init default environment variables
        self.configure_init()
        self.configure_default()

        # set environment variables according variant
        if self.is_debug():
            self.configure_debug()
        else:
            self.configure_release()

        # copy cxxflags to cflags
        self.context.env.CFLAGS = self.context.env.CXXFLAGS

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
        return os.path.join(path, self.build_path())
    
    def get_dep_build_location(self, dep, cache_dir):
        path = self.get_dep_artifact_location(dep, cache_dir)
        return path + '-build'

    def get_dep_artifact_pkl(self, dep, cache_dir):
        path = self.get_dep_artifact_location(dep, cache_dir)
        return os.path.join(path, dep.name + '.pkl')
        
    def use_dep(self, config, dep, cache_dir, enable_env, has_artifacts):
        dep_path_build = self.get_dep_artifact_location(dep, cache_dir)
        dep_path_include = self.get_dep_include_location(dep, cache_dir)
            
        filepkl = open(os.path.join(dep_path_build, dep.name + '.pkl'), 'rb')
        dep_export_ctx = pickle.load(filepkl)
        depdeps = None
        if isinstance(dep_export_ctx, Configuration):
            depconfig = dep_export_ctx
        else:
            depdeps = dep_export_ctx[0]
            depconfig = dep_export_ctx[1]
        filepkl.close()
        depconfig.includes = []
        
        if config is not None:
            config_targets = config.targets
            config.merge(self.context, [depconfig])
            config.targets = config_targets

            if dep.targets:
                for target in dep.targets:
                    if not target in depconfig.targets:
                        raise RuntimeError("Cannot find target: " + target)
                depconfig.targets = dep.targets
                
            if enable_env:
                # use cache :)
                if not self.is_windows():
                    self.context.env['CXXFLAGS_' + dep.name]			= ['-isystem' + dep_path_include]
                else:
                    self.context.env['CXXFLAGS_' + dep.name]			= ['/external:I', dep_path_include]
                self.context.env['ISYSTEM_' + dep.name]				= self.list_include([dep_path_include])
                if not depconfig.header_only:
                    self.context.env['LIBPATH_' + dep.name]			= self.list_include([dep_path_build])
                    self.context.env['LIB_' + dep.name]				= self.make_target_name_from_context(depconfig, dep)
            
            config.use.append(dep.name)

        if depdeps is not None:
            self.project.deps = dict((obj.name, obj) for obj in (self.project.deps + depdeps)).values()

        if self.is_header_only(dep, cache_dir):
            return

        out_path = make_directory(self.make_out_path())
        expected_files = self.get_expected_files(config, dep, cache_dir, has_artifacts)
        for file in expected_files:
            if not os.path.exists(os.path.join(out_path, file)):
                copy_file(os.path.join(dep_path_build, file), out_path)

    def clean_repo(self, repo_path):
        subprocess.call(['git', 'reset', '--hard'], cwd=repo_path)
        subprocess.call(['git', 'clean', '-fxd'], cwd=repo_path)

    def clone_repo(self, dep, repo_path):
        version_branch = self.get_dep_version_branch(dep)
        # NOTE: Can't use ['--depth', '1'] because of git describe --tags

        os.makedirs(repo_path)
        ret = subprocess.call(['git', 'clone', '--recursive', '--branch', version_branch, '--', dep.repository, '.'], cwd=repo_path)
        if ret:
            raise RuntimeError("ERROR: cloning " + dep.repository + ' ' + version_branch)

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

        process = subprocess.Popen([
            'golem',
            command,
            '--targets=' + dep.name,
            '--runtime=' + self.context.options.runtime,
            '--link=' + self.context.options.link,
            '--arch=' + self.context.options.arch,
            '--variant=' + self.context.options.variant,
            '--export=' + dep_path,
            '--cache-dir=' + self.make_writable_cache_dir(),
            '--static-cache-dir=' + self.make_static_cache_dir(),
            '--dir=' + build_path
        ], cwd=repo_path, shell=self.is_windows(), stdout=subprocess.PIPE)
        
        for c in iter(lambda: process.stdout.read(1), ''):  # replace '' with b'' for Python 3
            sys.stdout.write(c)
        ret = process.wait()
        if ret != 0:
            raise RuntimeError("Return code {}".format(ret))

    def can_open_pkl(self, dep, cache_dir):
        pkl_path = self.get_dep_artifact_pkl(dep, cache_dir)
        return os.path.exists(pkl_path)

    def open_pkl(self, dep, cache_dir):
        pkl_path = self.get_dep_artifact_pkl(dep, cache_dir)
        return open(pkl_path, 'r')

    def read_pkl(self, dep, cache_dir):
        if self.can_open_pkl(dep, cache_dir):
            with self.open_pkl(dep, cache_dir) as filepkl:
                return pickle.load(filepkl)
        return None

    def read_dep_configs(self, dep, cache_dir):
        dep_pkl = self.read_pkl(dep, cache_dir)
        if dep_pkl is None:
            return None

        return dep_pkl[1]
    
    def make_target_name_from_context(self, config, target):

        if config.targets:
            return config.targets
        else:
            target_name = target.name + self.variant_suffix()

            if target.type == 'library':
                if self.is_windows():
                    target_name = 'lib' + target_name

            return [target_name]

    def make_target_from_context(self, config, target):
        target_name = self.make_target_name_from_context(config, target)
        if not self.is_windows():
            target_name = ['lib' + target for target in target_name]
        result = list()
        for filename in target_name:
            for suffix in self.artifact_suffix(config):
                result.append(filename + suffix)
        return result


    def get_expected_files(self, config, dep, cache_dir, has_artifacts):

        expected_files = [dep.name + '.pkl']

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
        
        config = deepcopy(config)
        config.merge(self.context, [dep_configs])
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
        has_artifacts = self.has_artifacts(command)

        expects_files = self.get_expected_files(config, dep, cache_dir, has_artifacts)
        is_header_only = self.is_header_only(dep, cache_dir)

        is_header_not_available = is_header_only and not os.path.exists(self.get_dep_include_location(dep, cache_dir))
        is_artifact_not_available = not is_header_only and not self.is_in_dep_artifact_in_cache_dir(dep, cache_dir, expects_files)

        if is_header_not_available or is_artifact_not_available:
            if cache_dir.is_static:
                raise RuntimeError("Cannot find artifacts from the static cache location " + cache_dir.location)
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

    def build_target(self, target):

        config = Configuration()
        config.merge(self, target.configs)

        for use_name in config.use:
            for export in self.project.exports:
                if use_name == export.name:
                    config.merge(self, export.configs)

        for dep_name in config.deps:
            for dep in self.project.deps:
                if dep_name == dep.name:
                    self.link_dependency(config, dep)
        
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
        listmoc = self.list_moc(self.make_project_path_array(config.includes + config.source)) if project_qt else []
        
        build_fun = None

        linkflags = config.linkflags

        if target.type == 'library':
            if self.is_shared():
                build_fun = self.context.shlib
            elif self.is_static():
                build_fun = self.context.stlib
            else:
                print "ERROR: no options found"
                return
        elif target.type == 'program':
            build_fun = self.context.program
            if Context.is_linux():
                linkflags += ['-Wl,--allow-shlib-undefined']
            elif Context.is_darwin():
                linkflags += ['-Wl,-undefined,suppress']
        else:
            print "ERROR: no options found"
            return

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

        ttarget = build_fun(
            defines			= config.defines,
            includes		= listinclude,
            source			= listsource + version_source,
            target			= os.path.join(self.make_target_out(), targetname),
            name			= target.name,
            cxxflags		= config.cxxflags + isystemflags,
            cflags			= config.cxxflags,
            linkflags		= linkflags,
            use				= config.use + config.features,
            moc 			= listmoc,
            features 		= 'qt5' if project_qt else '',
            install_path 	= None,
            vnum			= version_short,
            depends_on		= version_source
        )

        if config.system:
            self.dep_system(
                context		= ttarget,
                libs	= config.system
            )
        
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

    def configure(self):

        # features list
        features_to_load = ['compiler_cxx']

        # qt check
        if self.project.qt:
            features_to_load.append('qt5')
            if os.path.exists(self.project.qtdir):
                self.context.options.qtdir = self.project.qtdir

        # configure x86 context
        self.context.setenv('x86')
        if self.is_windows():
            # self.context.env.MSVC_VERSIONS = ['msvc 14.0']
            self.context.env.MSVC_TARGETS = ['x86']
        self.context.load(features_to_load)
        
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
        if self.is_windows():
            # self.context.env.MSVC_VERSIONS = ['msvc 14.0']
            self.context.env.MSVC_TARGETS = ['x86_amd64'] # means x64 when using visual studio express for desktop
        self.context.load(features_to_load)

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

        self.context.load('clang_compilation_database')

    def build_path(self):
        return self.osname() + '-' + self.arch_min() + '-' + self.compiler_min() + '-' + self.runtime_min() + '-' + self.link_min() + '-' + self.variant_min()

    def build(self):

        self.environment()

        requested_targets = self.context.targets.split(',') if self.context.targets else [target.name for target in self.project.targets]
        
        for targetname in requested_targets:
            for target in self.project.targets:
                if targetname == target.name:
                    self.build_target(target)

        self.module.script(self)

        for targetname in self.context.targets.split(','):
            if targetname and not targetname in [target.name for target in self.project.targets]:
                if self.is_windows():
                    self.context(rule="type nul >> ${TGT}", target=targetname)
                else:
                    self.context(rule="touch ${TGT}", target=targetname)

    def get_asked_exports(self):
        return self.context.options.targets.split(',') if self.context.options.targets else [target.name for target in self.project.exports]

    def export(self):
        targets = self.get_asked_exports()
        for export in self.project.exports:
            if export.name in targets:
                
                config = Configuration()
                config.merge(self, export.configs, exporting = True)

                outpath = self.context.options.export

                if not outpath:
                    outpath = self.make_output_path('export')

                if not os.path.exists(outpath):
                    os.makedirs(outpath)

                includes = config.includes
                config.includes = []

                outpath_include = os.path.join(outpath, 'include')
                if not os.path.exists(outpath_include):
                    os.makedirs(outpath_include)
                config.includes.append(outpath_include)

                for include in includes:
                    distutils.dir_util.copy_tree(self.make_project_path(include), outpath_include)

                outpath_lib = os.path.join(outpath, self.build_path())
                if not os.path.exists(outpath_lib):
                    os.makedirs(outpath_lib)

                out_path = self.make_out_path()
                if os.path.exists(out_path):
                    copy_tree(self.make_out_path(), outpath_lib)

                output = open(os.path.join(outpath_lib, export.name + '.pkl'), 'wb')
                export_deps = [obj for n in config.deps for obj in self.project.deps if obj.name == n]
                export_ctx = [export_deps, config]
                pickle.dump(export_ctx, output)
                output.close()

    def resolve_local_configs(self, targets):
        configs = dict()
        for target in targets:

            config = Configuration()
            config.merge(self, target.configs, exporting=True)

            for use_name in config.use:
                for export in self.project.exports:
                    if use_name == export.name:
                        config.merge(self, export.configs, exporting=True)

            configs[target.name] = config
        return configs

    def resolve_configs_recursively(self, targets):
        configs = self.resolve_local_configs(targets)
        for target in targets:
            config = configs[target.name]

            for dep_name in config.deps:
                for dep in self.project.deps:
                    if dep_name == dep.name:
                        dep.configure(self, config)
        return configs

    def resolve_local_dependencies(self, targets):
        dependencies = dict()
        configs = self.resolve_local_configs(targets)
        for target in targets:
            config = configs[target.name]

            for dep_name in config.deps:
                for dep in self.project.deps:
                    if dep_name == dep.name:
                        if target.name not in dependencies:
                            dependencies[target.name] = list()
                        dependencies[target.name].append(dep)

        return dependencies

    def resolve_global_config(self, targets):
        configs = self.resolve_configs_recursively(targets)

        master_config = Configuration()
        for target_name, config in configs.items():
            master_config.merge(self, [config], exporting=True)
        return master_config

    def resolve_recursively(self):
        targets_to_process = self.get_targets_to_process()
        config = self.resolve_global_config(targets_to_process)

        outpath = self.context.options.export
        outpath_lib = os.path.join(outpath, self.build_path())
        if not os.path.exists(outpath_lib):
            os.makedirs(outpath_lib)
        
        for target in targets_to_process:
            outpath_target = os.path.join(outpath_lib, target.name + '.pkl')
            outpath_directory = os.path.dirname(outpath_target)
            if not os.path.exists(outpath_directory):
                os.makedirs(outpath_directory)
            output = open(outpath_target, 'wb')
            export_deps = [obj for n in config.deps for obj in self.project.deps if obj.name == n]
            export_ctx = [export_deps, config]
            pickle.dump(export_ctx, output)
            output.close()

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

    def requirements_debian(self):
        targets_to_process = self.get_targets_to_process()
        config = self.resolve_global_config(targets_to_process)
        packages = config.packages_dev if len(config.packages_dev) > 0 else config.packages

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
            subprocess.check_output(['sudo', 'apt', 'install', '-y'] + packages_to_install)
        else:
            print('Nothing to install')

        print('Done')

    def dependencies(self):
        targets_to_process = self.get_targets_to_process()
        configs = self.resolve_local_configs(targets_to_process)
        dependencies = self.resolve_local_dependencies(targets_to_process)
        for target_name, dependencies_list in dependencies.items():
            for dependency in dependencies_list:
                dependency.build(self, configs[target_name])

    def package(self):

        print("Check asked package")

        packages_to_process = self.get_packages_to_process()
        
        for package in packages_to_process:
            if self.is_windows():
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
        removeTree(self, package_directory)

        # Install documentation

        # Compression man pages

        # Copy systemd unit if any

        # Strip binaries, libraries, archives

        print("Prepare package")
        package_directory = make_directory(package_directory)

        prefix_directory = make_directory(package_directory, '.' + prefix)

        bin_directory = make_directory(prefix_directory, 'bin')

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
        subprocess.check_output(['fakeroot', 'dpkg-deb', '--build', package_directory, output_filename + '.deb'], cwd=self.get_output_path())
