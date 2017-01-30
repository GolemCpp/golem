#!/usr/bin/env python

import sys
sys.dont_write_bytecode = True

import os
import platform
import subprocess
import ConfigParser
import distutils.dir_util
import md5
import shutil
import imp
import io
import re
import copy
import types
import pickle

def print_obj(obj, depth = 5, l = ""):
	#fall back to repr
	if depth<0: return repr(obj)
	#expand/recurse dict
	if isinstance(obj, dict):
		name = ""
		objdict = obj
	else:
		#if basic type, or list thereof, just print
		canprint=lambda o:isinstance(o, (int, float, str, unicode, bool, types.NoneType, types.LambdaType))
		try:
			if canprint(obj) or sum(not canprint(o) for o in obj) == 0: return repr(obj)
		except TypeError, e:
			pass
		#try to iterate as if obj were a list
		try:
			return "[\n" + "\n".join(l + print_obj(k, depth=depth-1, l=l+"  ") + "," for k in obj) + "\n" + l + "]"
		except TypeError, e:
			#else, expand/recurse object attribs
			name = (hasattr(obj, '__class__') and obj.__class__.__name__ or type(obj).__name__)
			objdict = {}
			for a in dir(obj):
				if a[:2] != "__" and (not hasattr(obj, a) or not hasattr(getattr(obj, a), '__call__')):
					try: objdict[a] = getattr(obj, a)
					except Exception, e: objdict[a] = str(e)
	return name + " {\n" + "\n".join(l + repr(k) + ": " + print_obj(v, depth=depth-1, l=l+"  ") + "," for k, v in objdict.iteritems()) + "\n" + l + "}"


class CacheConf:
	def __init__(self):
		self.remote = ''
		self.location = os.path.join(os.path.expanduser("~"), '.cache', 'golem', 'builds')

	def __str__(self):
		return print_obj(self)

def make_dep_base(dep):
	return dep.name + "-" + str(dep.resolved_version if dep.resolved_version else dep.version)

class Dependency:
	def __init__(self, name = None, repository = None, version = None):
		self.name 		= '' if name is None else name
		self.repository	= '' if repository is None else repository
		self.version 	= '' if version is None else version
		self.resolved_version = ''

	def __str__(self):
		return print_obj(self)

	def resolve(self):
		if self.resolved_version:
			return self.resolved_version
		
		dep_version = ''
		if str(self.version) == 'latest':
			tags = subprocess.check_output(['git', 'ls-remote', '--tags', self.repository])
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
			hash = subprocess.check_output(['git', 'ls-remote', '--tags', self.repository, last])
			if not hash:
				print("ERROR: can't find " + last)
				return
			#dep_version = hash[:8]
			dep_version = last
		else:
			hash = subprocess.check_output(['git', 'ls-remote', '--heads', self.repository, str(self.version)])
			if hash:
				dep_version = hash[:8]
			else:
				dep_version = str(self.version)

		self.resolved_version = dep_version
		return self.resolved_version

class Condition:
	def __init__(self, variant = None, linking = None, runtime = None, osystem = None, arch = None, compiler = None):
		self.variant 	= [] if variant is None else variant 	# debug, release
		self.linking 	= [] if linking is None else linking 	# shared, static
		self.runtime 	= [] if runtime is None else runtime 	# shared, static
		self.osystem 	= [] if osystem is None else osystem 	# linux, windows, osx
		self.arch 		= [] if arch is None else arch		# x86, x64
		self.compiler 	= [] if compiler is None else compiler # gcc, clang, msvc

	def __str__(self):
		return print_obj(self)

	def __nonzero__(self):
		if self.variant or self.linking or self.runtime or self.osystem or self.arch or self.compiler:
			return True
		return False

class Configuration:
	def __init__(self, target = None, defines = None, includes = None, source = None, cxxflags = None, linkflags = None, system = None, features = None, deps = None, use = None, **kwargs):
		self.condition = Condition(**kwargs)

		self.target = '' if target is None else target

		self.defines = [] if defines is None else defines
		self.includes = [] if includes is None else includes
		self.source = [] if source is None else source

		self.cxxflags = [] if cxxflags is None else cxxflags
		self.linkflags = [] if linkflags is None else linkflags
		self.system = [] if system is None else system

		self.features = [] if features is None else features
		self.deps = [] if deps is None else deps
		self.use = [] if use is None else use

	def __str__(self):
		return print_obj(self)

	def append(self, config):
		
		if config.target:
			self.target = config.target

		self.defines += config.defines
		self.includes += config.includes
		self.source += config.source

		self.cxxflags += config.cxxflags
		self.linkflags += config.linkflags
		self.system += config.system

		self.features += config.features
		self.deps += config.deps
		self.use += config.use
	
	def merge(self, context, configs):
		for c in configs:
			if (	(not c.condition.variant or context.variant() in c.condition.variant)
				and (not c.condition.linking or context.link() in c.condition.linking)
				and (not c.condition.runtime or context.runtime() in c.condition.runtime)
				and (not c.condition.osystem or context.osname() in c.condition.osystem)
				and (not c.condition.arch or context.arch() in c.condition.arch)
				and (not c.condition.compiler or context.compiler() in c.condition.compiler)):
				self.append(c)
			
class Target:
	def __init__(self):
		self.type = ''
		self.name = ''
		self.configs = []

	def __str__(self):
		return print_obj(self)

	def when(self, **kwargs):
		config = Configuration(**kwargs)
		self.configs.append(config)
		return config

class Project:
	def __init__(self):
		self.cache = []
		self.deps = []

		self.targets = []
		self.exports = []

		self.qt = False
		self.qtdir = ''

	def __str__(self):
		return print_obj(self)

	def deps_resolve(self):
		cache = []
		for dep in self.deps:
			dep.resolve()
			cache.append([dep.name, dep.version, dep.resolve()])
		return cache

	def deps_load(self, cache):
		for i, dep in enumerate(self.deps):
			for item in cache:
				if item[0] == dep.name and item[1] == dep.version:
					print item[0] + " : " + item[1] + " -> " + item[2]
					self.deps[i].resolved_version = item[2]
					break;
			if not self.deps[i].resolved_version:
				print dep.name + " : no cached version"

		sys.stdout.flush()

	def target(self, type, name, target = None, defines = None, includes = None, source = None, features = None, deps = None, use = None):
		newtarget = Target()
		newtarget.type = type
		newtarget.name = name
		
		config = Configuration()

		config.target = '' if target is None else target

		config.defines = [] if defines is None else defines
		config.includes = [] if includes is None else includes
		config.source = [] if source is None else source

		config.features = [] if features is None else features
		config.deps = [] if deps is None else deps
		config.use = [] if use is None else use

		newtarget.configs.append(config)

		if type == 'export':
			self.exports.append(newtarget)
			return newtarget

		if any([feature.startswith("QT5") for feature in config.features]):
			self.enable_qt()

		self.targets.append(newtarget)
		return newtarget

	def library(self, **kwargs):
		return self.target(type = 'library', **kwargs)

	def program(self, **kwargs):
		return self.target(type = 'program', **kwargs)

	def export(self, **kwargs):
		return self.target(type = 'export', **kwargs)

	def dependency(self, **kwargs):
		dep = Dependency(**kwargs)
		self.deps.append(dep)
		return dep

	def enable_qt(self, path = ''):
		self.qt = True
		self.qtdir = path

	def linux_check_packages(*packages):
		installed_packages = subprocess.check_output(['dpkg', '-l'])
		for package in packages:
			if not installed_packages.find(str(package)):
				subprocess.check_output(['sudo', 'apt-get', 'install', str(package)])

class Module:
	def __init__(self, path = None):
		self.path = '.' if path is None else path

		if sys.modules.get('project'):
			self.module = sys.modules.get('project')
		else:
			project_path = os.path.join(self.path, 'project.glm')

			if not os.path.exists(project_path):
				print "ERROR: can't find " + project_path
				return
			self.module = imp.load_source('project', project_path)

	def project(self):

		if not hasattr(self.module, 'configure'):
			print "ERROR: no configure function found"
			return

		project = Project()
		self.module.configure(project)
		return project

	def script(self, context):

		#if not hasattr(self.module, 'script'):
		#	print "ERROR: no script function found"
		#	return

		if hasattr(self.module, 'script'):
			self.module.script(context)

class Context:
	def __init__(self, context):
		self.context = context
		self.module = Module(self.get_project_dir())
		self.project = self.module.project()
		self.resolve()

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

	def is_x86(self):
		return Context.osarch_parser(self.context.options.arch) == 'x86'

	def is_x64(self):
		return Context.osarch_parser(self.context.options.arch) == 'x64'

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

			self.context.env.MSVC_VERSIONS = ['msvc 14.0']
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

			self.context.env.CXXFLAGS.append('-std=c++14')

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
			self.context.env.CXXFLAGS.append('-g')
			self.context.env.CXXFLAGS.append('-O0')

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
		
		self.context.env['INCLUDES_' + name]		= list_include(self.context, ['includes'])
		self.context.env['STLIBPATH_' + name]	= list_include(self.context, ['libpath'])
		self.context.env['STLIB_' + name]		= lib
		
	def dep_static(self, name, fullname, lib, libdebug):
		
		self.context.env['INCLUDES_' + name]		= list_include(self.context, ['includes'])
		self.context.env['STLIBPATH_' + name]	= list_include(self.context, ['libpath'])
		
		if self.is_debug():
			self.context.env['STLIB_' + name]	= libdebug
		else:
			self.context.env['STLIB_' + name]	= lib
			
		
	def dep_shared_release(self, name, fullname, lib):
		
		self.context.env['INCLUDES_' + name]		= list_include(self.context, ['includes'])
		self.context.env['LIBPATH_' + name]		= list_include(self.context, ['libpath'])
		self.context.env['LIB_' + name]			= lib
		
	def dep_shared(self, name, fullname, lib, libdebug):
		
		self.context.env['INCLUDES_' + name]		= list_include(self.context, ['includes'])
		self.context.env['LIBPATH_' + name]		= list_include(self.context, ['libpath'])
		
		if self.is_debug():
			self.context.env['LIB_' + name]		= libdebug
		else:
			self.context.env['LIB_' + name]		= lib

	def link_dependency(self, config, dep):

		cache_conf = self.find_cache_conf()
		if not cache_conf:
			cache_conf = CacheConf()
		
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
		#	shutil.rmtree(dep_path)
		#os.makedirs(dep_path)
		if not os.path.exists(dep_path):
			os.makedirs(dep_path)

		should_copy = False
		beacon_build_done = self.make_build_path(dep_path_base + '.build')

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
					build_dir = os.path.join(cache_dir, 'build')
					if os.path.exists(build_dir):
						shutil.rmtree(build_dir)
					os.makedirs(build_dir)
					
					ret = subprocess.call(['git', 'clone', '--recursive', '--depth', '1', '--branch', dep_version_branch, '--', dep.repository, '.'], cwd=build_dir)
					if ret:
						print "ERROR: cloning " + dep.repository + ' ' + dep_version_branch
						return

					ret = subprocess.check_output(['python', 'project.glm', '--targets=' + dep.name, '--runtime=' + self.context.options.runtime, '--link=' + self.context.options.link, '--arch=' + self.context.options.arch, '--variant=' + self.context.options.variant, '--export=' + dep_path], cwd=build_dir)
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
		depconfig = pickle.load(filepkl)
		filepkl.close()
		
		config_target = config.target
		config.merge(self.context, [depconfig])
		config.target = config_target

		# use cache :)
		self.context.env['INCLUDES_' + dep.name]		= self.list_include([dep_path_include])
		self.context.env['LIBPATH_' + dep.name]			= self.list_include([dep_path_build])
		self.context.env['LIB_' + dep.name]				= self.make_target_by_config(depconfig, dep)
		config.use.append(dep.name)

		if should_copy:
			distutils.dir_util.copy_tree(dep_path_build, self.make_out_path())
			with io.open(self.make_build_path(dep_path_base + '.build'), 'wb') as file:
				file.write('done')

	def make_target_by_config(self, config, target):
		if config.target:
			return config.target
		else:
			return target.name + self.variant()


	def make_target_name(self, config, target):

		target_name = self.make_target_by_config(config, target)

		if target.type == 'library':
			if self.is_windows():
				target_name = 'lib' + target_name

		return target_name

	def get_build_path(self):
		return self.context.out_dir if self.context.out_dir else self.context.options.out if self.context.options.out else ''

	def make_build_path(self, path):
		return os.path.join(self.get_build_path(), path)

	def make_target_out(self):
		return 'out'

	def make_out_path(self):
		return self.make_build_path(self.make_target_out())

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

		listinclude = self.list_include(self.make_project_path_array(config.includes))
		listsource = self.list_source(self.make_project_path_array(config.source)) + self.list_qt_qrc(self.make_project_path_array(config.source)) + self.list_qt_ui(self.make_project_path_array(config.source)) if project_qt else self.list_source(self.make_project_path_array(config.source))
		listmoc = self.list_moc(self.make_project_path_array(config.includes + config.source)) if project_qt else []
		
		build_fun = None

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
		else:
			print "ERROR: no options found"
			return
		
		ttarget = build_fun(
			defines			= config.defines,
			includes		= listinclude,
			source			= listsource,
			target			= os.path.join(self.make_target_out(), targetname),
			name			= target.name,
			cxxflags		= config.cxxflags,
			cflags			= config.cxxflags,
			linkflags		= config.linkflags,
			use				= config.use + config.features,
			moc 			= listmoc,
			features 		= 'qt5' if project_qt else '',
			install_path 	= None
		)

		if config.system:
			self.dep_system(
				context		= ttarget,
				libs	= config.system
			)

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
			self.context.env.MSVC_VERSIONS = ['msvc 14.0']
			self.context.env.MSVC_TARGETS = ['x86']
		self.context.load(features_to_load)

		# configure x64 context
		self.context.setenv('x64')
		if self.is_windows():
			self.context.env.MSVC_VERSIONS = ['msvc 14.0']
			self.context.env.MSVC_TARGETS = ['x86_amd64'] # means x64 when using visual studio express for desktop
		self.context.load(features_to_load)

	def build_path(self):
		return self.osname() + '-' + self.arch_min() + '-' + self.compiler_min() + '-' + self.runtime_min() + '-' + self.link_min() + '-' + self.variant_min()

	def build(self):

		self.environment()

		for target in self.project.targets:
			self.build_target(target)

		self.module.script(self)

		for targetname in self.context.targets.split(','):
			if targetname and not targetname in [target.name for target in self.project.targets]:
				self.context(rule="touch ${TGT}", target=targetname)

	def export(self):
		
		targets = self.context.options.targets.split(',') if self.context.options.targets else [target.name for target in self.project.exports]
		for export in self.project.exports:
			if export.name in targets:
				
				config = Configuration()
				config.merge(self, export.configs)

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
				pickle.dump(config, output)
				output.close()

	def repo_clear(self, path):
		output = subprocess.check_output(['git', 'status', '-s'], cwd=path)
		if output:
			print(output)
			return False
		return True

	def repo_dirty(self, path):
		return not repo_clear(path)

	def format(self):
		paths = []
		for target in self.project.targets:
			for config in target.configs:
				paths += config.includes
				paths += config.source
		paths = [self.make_project_path(path) for path in paths]
		ret = subprocess.call(['python', 'astyle'] + paths)
		if ret:
			print "ERROR: astyle " + str(paths)
			return

	# commit build (all) to specific repository (according project file)
	def release(self):
		project_path = os.path.join(self.get_project_dir(), 'project.glm')
		if not os.path.exists(project_path):
			print "ERROR: no project file found " + project_path
			return

		if self.context.options.major:
			bumping = 'major'
		elif self.context.options.minor:
			bumping = 'minor'
		elif self.context.options.patch:
			bumping = 'patch'
		else:
			print('Usage: release { major | minor | patch }')
			return
		
		with io.open(project_path, 'rb') as f:
			file_content = f.read().decode('utf-8')
		match = re.search('VERSION\s*=\s*(.*)', file_content)

		if not match:
			print "ERROR: No VERSION found in the project file"
			print "Before trying to Release, you should define a VERSION variable in your project. VERSION is a string using Semantic Versioning. Example: VERSION = 'v1.0.0'"
			return
		else:
			found = True
			version = match.group(1).strip('\'"')

		if repo_dirty(self.get_project_dir()):
			print("Your repository is dirty. You have to commit before releasing!")
			return

		parse = re.compile(r"(?P<major>\d+)\.?(?P<minor>\d+)?\.?(?P<patch>\d+)?(\-(?P<release>[a-z]+))?", re.VERBOSE)
		match = parse.search(version)
		
		parsed = {}
		if not match:
			print("Unrecognized version format")
			return
		
		for key, value in match.groupdict().items():
			if key == 'release':
				if value is None:
					parsed[key] = None
				else:
					parsed[key] = str(value)
			else:
				if value is None:
					parsed[key] = 0
				else:
					parsed[key] = int(value)

		bumped = False

		for key, value in parsed.items():
			if bumped:
				parsed[key] = 0
			elif key == bumping:
				parsed[key] = value + 1
				bumped = True

		serialized = 'v{major}.{minor}.{patch}'
		
		if parsed['release'] is not None:
			serialized += '-{release}'

		newversion = serialized.format(**parsed)
		
		default_message = "Bump " + str(version) + " to " + newversion
		message = default_message

		file_content = re.sub('^VERSION\s*=\s*(.*)', 'VERSION = \'' + newversion + '\'', file_content, flags=re.MULTILINE)
		
		with io.open(project_path, 'wb') as f:
			file_content = file_content.encode('utf-8')
			f.write(file_content)
		
		output = subprocess.check_output(['git', 'add', 'project.glm'], cwd=self.get_project_dir())
		if output:
			print output

		output = subprocess.check_output(['git', 'commit', '-m', message], cwd=self.get_project_dir())
		if output:
			print output
		
		output = subprocess.check_output(['git', 'tag', '-a', newversion, '-m', message], cwd=self.get_project_dir())
		if output:
			print output
			
		print "Released " + newversion


def get_context(context):
	global global_context
	if not 'global_context' in globals():
		global_context = Context(context)

	global_context.context = context
	return global_context

def options(context):
	Context.options(context)

def configure(context):
	ctx = get_context(context)
	ctx.configure()

def build(context):
	ctx = get_context(context)
	ctx.build()

def format(context):
	ctx = get_context(context)
	ctx.format()

def release(context):
	ctx = get_context(context)
	ctx.release()

def export(context):
	ctx = get_context(context)
	ctx.export()