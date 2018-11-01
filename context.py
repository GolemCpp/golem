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
import distutils
import ConfigParser
from module import Module
from cache import CacheConf
from configuration import Configuration
import cache

def handleRemoveReadonly(func, path, exc_info):
    """
    Error handler for ``shutil.rmtree``.

    If the error is due to an access error (read only file)
    it attempts to add write permission and then retries.

    If the error is for another reason it re-raises the error.

    Usage : ``shutil.rmtree(path, onerror=handleRemoveReadonly)``
    """
    import stat
    if not os.access(path, os.W_OK):
        # Is the error an access error ?
        os.chmod(path, stat.S_IWUSR)
        func(path)
    else:
        raise RuntimeError("Can't access to \"{}\"".format(path))


def removeTree(ctx, path):
    if os.path.exists(path):
        if ctx.is_windows():
            # shutil.rmtree(build_dir, ignore_errors=False, onerror=handleRemoveReadonly)
            from time import sleep
            while os.path.exists(path):
                os.system("rmdir /s /q %s" % path)
                sleep(0.1)
        else:
            shutil.rmtree(path)


def make_directory(base, path=None):
    directory = base
    if path is not None:
        directory = os.path.join(directory, path)
    if not os.path.exists(directory):
        os.makedirs(directory)
    return directory

def make_dep_base(dep):
	return dep.name + "-" + str(dep.resolved_version if dep.resolved_version else dep.version)


class Context:
	def __init__(self, context):
		self.context = context
		self.module = Module(self.get_project_dir())
		self.project = self.module.project()

	def resolve(self):
		deps_cache_file = self.make_build_path('deps.cache')
		if os.path.exists(deps_cache_file):
			cache = None
			with io.open(deps_cache_file, 'rb') as file:
				cache = pickle.load(file)
			self.project.deps_load(cache)
		else:
			cache = self.project.deps_resolve()
			with io.open(deps_cache_file, 'wb') as file:
				pickle.dump(cache, file)

	def get_project_dir(self):
		return self.context.options.dir

	def make_cache_dir(self):
		cache_dir = self.context.options.cache_dir
		if not os.path.isabs(cache_dir):
			cache_dir = os.path.join(self.get_project_dir(), cache_dir)
		return cache_dir

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

		context.add_option("--vscode", action="store_true", default=False, help="VSCode CppTools Properties")

		context.add_option("--cache-dir", action="store", default=cache.default_cached_dir(), help="Cache directory location")
		
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
		cacheconf.location = self.make_cache_dir()

		# cache remote
		if not config.has_option('GOLEM', 'cache.remote'):
			return None
		
		remote = config.get('GOLEM', 'cache.remote')

		if not remote:
			return None

		cacheconf.remote = remote.strip('\'"')

		# cache location
		if config.has_option('GOLEM', 'cache.location'):
			location = config.get('GOLEM', 'cache.location')
			
		cacheconf.location = cacheconf.location.strip('\'"')

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

	def link_dependency(self, config, dep):

		cache_conf = self.find_cache_conf()
		if not cache_conf:
			cache_conf = CacheConf()
			cache_conf.location = self.make_cache_dir()
		
		cache_location = cache_conf.location
		cache_repo = cache_conf.remote
		
		cache_dir = cache_location
		if not os.path.exists(cache_dir):
			os.makedirs(cache_dir)

		dep_version = dep.resolve()
		dep_version_branch = dep_version
		if dep.version != 'latest' and dep_version != dep.version:
			dep_version_branch = dep.version

		dep_path_base = make_dep_base(dep)
		dep_path = os.path.join(cache_dir, dep_path_base)

		dep_path_include = os.path.join(dep_path, 'include')
		dep_path_build = os.path.join(dep_path, self.build_path())

		#if os.path.exists(dep_path):
		#	removeTree(self, dep_path)
		#os.makedirs(dep_path)
		if not os.path.exists(dep_path):
			os.makedirs(dep_path)

		should_copy = False
		beacon_build_done = os.path.join(self.make_out_path(), dep.name + '.pkl')

		if not os.path.exists(beacon_build_done):
			should_copy = True

			if not os.path.exists(dep_path_build):
				print "INFO: can't find the dependency " + dep.name
				print "Search in the cache repository..."

				should_build = True
				# search the corresponding branch in the cache repo (with the right version)
				if cache_repo:
					ret = subprocess.call(['git', 'ls-remote', '--heads', '--exit-code', cache_repo, dep_path_build])
					if not ret:
						should_build = False
						
				if should_build:
					print "Nothing in cache, have to build..."

					# building
					build_dir = os.path.join(dep_path, 'build')
					if os.path.exists(build_dir):
						removeTree(self, build_dir)
					os.makedirs(build_dir)
					
					# removed ['--depth', '1'] because of git describe --tags
					ret = subprocess.call(['git', 'clone', '--recursive', '--branch', dep_version_branch, '--', dep.repository, '.'], cwd=build_dir)
					if ret:
						print "ERROR: cloning " + dep.repository + ' ' + dep_version_branch
						return

					if self.is_windows():
						ret = subprocess.check_output(['golem', '--targets=' + dep.name, '--runtime=' + self.context.options.runtime, '--link=' + self.context.options.link, '--arch=' + self.context.options.arch, '--variant=' + self.context.options.variant, '--export=' + dep_path, '--cache-dir=' + self.make_cache_dir()], cwd=build_dir, shell=True)
					else:
						ret = subprocess.check_output(['golem', '--targets=' + dep.name, '--runtime=' + self.context.options.runtime, '--link=' + self.context.options.link, '--arch=' + self.context.options.arch, '--variant=' + self.context.options.variant, '--export=' + dep_path, '--cache-dir=' + self.make_cache_dir()], cwd=build_dir)
					print ret

					# caching
					#ret = subprocess.call(['git', 'clone', '--depth', '1', '--', cache_repo, '.'], cwd=dep_path)
					#if ret:
					#	print "ERROR: git clone --depth 1 -- " + cache_repo + ' .'
					#	return
					#ret = subprocess.call(['git', 'checkout', '-b', target.name], cwd=dep_path)
					#if ret:
					#	print "ERROR: git checkout -b " + target.name
					
					#bin_dir = os.path.join(golem_dir, 'out')
					#bin_dir = os.path.join(bin_dir, self.context.options.variant)

					#if not os.path.exists(bin_dir):
					#	print "ERROR: no binaries found in the dependency build"
					#	return

					#distutils.dir_util.copy_tree(bin_dir, dep_path)

					#include_dir = os.path.join(build_dir, 'include')

					#if not os.path.exists(include_dir):
					#	print "ERROR: no include found in the dependency build"
					#	return
					
					#distutils.dir_util.copy_tree(include_dir, dep_path_include)

				else:
					# branch found, have to clone it
					ret = subprocess.call(['git', 'clone', '--depth', '1', '--branch', target.name, '--', cache_repo, '.'], cwd=dep_path)
					if ret:
						print "ERROR: git clone --depth 1 --branch " + target.name + ' -- ' + cache_repo + ' .'
						return

				
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
		
		config_target = config.target
		config.merge(self.context, [depconfig])
		config.target = config_target

		# use cache :)
		if not self.is_windows():
			self.context.env['CXXFLAGS_' + dep.name]			= ['-isystem' + dep_path_include]
		else:
			self.context.env['CXXFLAGS_' + dep.name]			= ['/external:I', dep_path_include]
		self.context.env['ISYSTEM_' + dep.name]				= self.list_include([dep_path_include])
		if not hasattr(depconfig, 'header_only') or depconfig.header_only is not None and not depconfig.header_only:
			self.context.env['LIBPATH_' + dep.name]			= self.list_include([dep_path_build])
			self.context.env['LIB_' + dep.name]				= self.make_target_by_config_name(depconfig, dep)
		
		config.use.append(dep.name)
		if depdeps is not None:
			self.project.deps = dict((obj.name, obj) for obj in (self.project.deps + depdeps)).values()

		if should_copy:
			distutils.dir_util.copy_tree(dep_path_build, self.make_out_path())

	def make_target_by_config(self, config, target):
		if config.target:
			return config.target
		else:
			return target.name + self.variant_suffix()

	def make_target_by_config_name(self, config, target):
		if config.target:
			return config.target
		else:
			target_name = target.name + self.variant_suffix()

			if self.is_windows():
				target_name = 'lib' + target_name

			return target_name


	def make_target_name(self, config, target):

		target_name = self.make_target_by_config(config, target)

		if target.type == 'library':
			if self.is_windows():
				target_name = 'lib' + target_name

		return target_name

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
		
		targetname = self.make_target_name(config, target)

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

	def export(self):
		targets = self.context.options.targets.split(',') if self.context.options.targets else [target.name for target in self.project.exports]
		for export in self.project.exports:
			if export.name in targets:
				
				config = Configuration()
				config.merge(self, export.configs, exporting = True)

				outpath = self.context.options.export

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

				distutils.dir_util.copy_tree(self.make_out_path(), outpath_lib)

				output = open(os.path.join(outpath_lib, export.name + '.pkl'), 'wb')
				export_deps = [obj for n in config.deps for obj in self.project.deps if obj.name == n]
				export_ctx = [export_deps, config]
				pickle.dump(export_ctx, output)
				output.close()

	def requirements(self):
		targets_to_process = []
		asked_targets = self.context.options.targets.split(',') if self.context.options.targets else [target.name for target in self.project.targets]
		for asked_target in asked_targets:
			for available_target in self.project.targets:
				if asked_target == available_target.name:
					targets_to_process.append(available_target)
				else:
					raise RuntimeError("Can't find any target configuration named \"{}\"".format(asked_target))
		
		packages = []
		master_config = Configuration()
		for target in targets_to_process:

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

			master_config.merge(self, [config])
		packages += master_config.packages_dev if len(master_config.packages_dev) > 0 else master_config.packages
		print('Packages required to be installed: {}'.format(packages))
		print('Looking for installed packages...')

		packages_to_install = []
		installed_packages = subprocess.check_output(['dpkg', '-l'])
		for package in packages:
			if not installed_packages.find(package):
				packages_to_install.append(package)
			else:
				print('Found installed package: {}'.format(package))
		
		if len(packages_to_install) > 0:
			print('Install the following packages: {}'.format(packages_to_install))
			subprocess.check_output(['sudo', 'apt', 'install', '-y'] + packages_to_install)
		print('Done')

	def package(self):

		# Check asked package

		packages_to_process = []
		asked_packages = self.context.options.targets.split(',') if self.context.options.targets else [package.name for package in self.project.packages]
		for asked_package in asked_packages:
			for available_package in self.project.packages:
				if asked_package == available_package.name:
					packages_to_process.append(available_package)
				else:
					raise RuntimeError("Can't find any package configuration named \"{}\"".format(asked_package))
		
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

		# Check package's targets

		targets_to_process = []
		asked_targets = package.targets
		for asked_target in asked_targets:
			for available_target in self.project.targets:
				if asked_target == available_target.name:
					targets_to_process.append(available_target)
				else:
					raise RuntimeError("Can't find any target configuration named \"{}\" for package named \"{}\"".format(asked_target, package.name))

		depends = []
		master_config = Configuration()
		for target in targets_to_process:

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

			master_config.merge(self, [config])
		depends += master_config.packages

		# Don't run this script as root

		# Gather package metadata
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

		# Clean-up
		package_directory = self.make_output_path('dist')
		removeTree(self, package_directory)

		# Install documentation

		# Compression man pages

		# Copy systemd unit if any

		# Strip binaries, libraries, archives

		# Prepare package
		package_directory = make_directory(package_directory)

		prefix_directory = make_directory(package_directory, '.' + prefix)

		bin_directory = make_directory(prefix_directory, 'bin')

		distutils.dir_util.copy_tree(self.make_out_path(), bin_directory)

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

		# Build package
		output_filename = package_name + '_' + package_version + "_" + package_arch
		subprocess.check_output(['fakeroot', 'dpkg-deb', '--build', package_directory, output_filename + '.deb'], cwd=self.get_output_path())
