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

def make_project_path(bld, path):
	return os.path.join(bld.options.dir, path)

def make_project_path_array(bld, array):
	return [make_project_path(bld, x) for x in array]

def hash_identifier(flags):
	m = md5.new()
	m.update(''.join(flags))
	return m.hexdigest()[:8]

def list_include(bld, includes):
	return [bld.root.find_dir(x) if os.path.isabs(x) else bld.srcnode.find_dir(x) for x in includes]

def list_source(bld, source):
	return [item for sublist in [bld.root.find_dir(x).ant_glob('*.cpp') if os.path.isabs(x) else bld.srcnode.find_dir(x).ant_glob('*.cpp') for x in source] for item in sublist]

def link_static():
	return 'static'
	
def link_shared():
	return 'shared'
	
def link(bld):
	return bld.options.link

def link_min(bld):
	return link(bld)[:2]

def is_static(bld):
	return bld.options.link == link_static()

def is_shared(bld):
	return bld.options.link == link_shared()

def runtime(bld):
	return bld.options.runtime

def runtime_min(bld):
	return runtime(bld)[:2]

def arch(bld):
	return bld.options.arch

def arch_min(bld):
	return arch(bld)

def variant_debug():
	return 'debug'

def variant_release():
	return 'release'

def variant(bld):
	variant = ''
	if bld.options.variant == variant_debug():
		variant = '-' + variant_debug()
	return variant

def is_debug(bld):
	return bld.options.variant == variant_debug()
		
def is_release(bld):
	return bld.options.variant == variant_release()

def variant_min(bld):
	return bld.options.variant[:1]

def os_windows():
	return 'windows'

def os_linux():
	return 'linux'

def os_osx():
	return 'osx'

def is_windows():
	return sys.platform.startswith('win32')

def is_linux():
	return sys.platform.startswith('linux')

def is_darwin():
	return sys.platform.startswith('darwin')

def osname():
	osname = ''
	if is_windows():
		osname = os_windows()
	elif is_linux():
		osname = os_linux()
	elif is_darwin():
		osname = os_osx()
	return osname

def osname_min():
	return osname()[:3]

def compiler(bld):
	return bld.env.CXX_NAME + '-' + '.'.join(bld.env.CC_VERSION)

def compiler_min(bld):
	return compiler(bld)

def machine():
    if os.name == 'nt' and sys.version_info[:2] < (2,7):
        return os.environ.get("PROCESSOR_ARCHITEW6432", 
               os.environ.get('PROCESSOR_ARCHITECTURE', ''))
    else:
        return platform.machine()

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

def osarch():
    return osarch_parser(machine())

def is_x86(conf):
	return osarch_parser(conf.options.arch) == 'x86'

def is_x64(conf):
	return osarch_parser(conf.options.arch) == 'x64'

def options(opt):
	opt.load('compiler_cxx')
	opt.add_option("--dir", action="store", default='.', help="Project location")
	opt.add_option("--variant", action="store", default='debug', help="Runtime Linking")
	opt.add_option("--runtime", action="store", default='shared', help="Runtime Linking")
	opt.add_option("--link", action="store", default='shared', help="Library Linking")
	opt.add_option("--arch", action="store", default='x86', help="Target Architecture")
	opt.add_option("--test", action="store_true", default=False, help="Test build")
	opt.add_option("--major", action="store_true", default=False, help="Release major version")
	opt.add_option("--minor", action="store_true", default=False, help="Release minor version")
	opt.add_option("--patch", action="store_true", default=False, help="Release patch version")
	
	if is_windows(): 
		opt.add_option("--nounicode", action="store_true", default=False, help="Unicode Support")
	else: 
		opt.add_option("--nounicode", action="store_true", default=True, help="Unicode Support")

def configure_init(conf):
	conf.env.DEFINES=[]
	conf.env.CXXFLAGS=[]
	conf.env.CFLAGS=[]
	conf.env.LINKFLAGS=[]
	conf.env.ARFLAGS=[]

def configure_default(conf):
	if not conf.options.nounicode:
		conf.env.DEFINES.append('UNICODE')

	if is_windows():
		# Compiler Options https://msdn.microsoft.com/en-us/library/fwkeyyhe.aspx
		# Linker Options https://msdn.microsoft.com/en-us/library/y0zzbyt4.aspx

		conf.env.MSVC_VERSIONS = ['msvc 14.0']
		# conf.env.CXXFLAGS.append('/MP') # compiles multiple source files by using multiple processes
		conf.env.CXXFLAGS.append('/Gm-') # disable minimal rebuild
		conf.env.CXXFLAGS.append('/Zc:inline') # compiler does not emit symbol information for unreferenced COMDAT functions or data
		conf.env.CXXFLAGS.append('/Zc:forScope') # implement standard C++ behavior for for loops 
		conf.env.CXXFLAGS.append('/Zc:wchar_t') # wchar_t as a built-in type 
		conf.env.CXXFLAGS.append('/fp:precise') # improves the consistency of floating-point tests for equality and inequality 
		conf.env.CXXFLAGS.append('/W4') # warning level 4
		conf.env.CXXFLAGS.append('/sdl') # enables a superset of the baseline security checks provided by /GS
		conf.env.CXXFLAGS.append('/GS') # detects some buffer overruns that overwrite things
		conf.env.CXXFLAGS.append('/EHsc') # enable exception
		conf.env.CXXFLAGS.append('/nologo') # suppress startup banner
		conf.env.CXXFLAGS.append('/Gd') # specifies default calling convention
		conf.env.CXXFLAGS.append('/analyze-') # disable code analysis
		conf.env.CXXFLAGS.append('/WX-') # warnings are not treated as errors 
		conf.env.CXXFLAGS.append('/FS') # serialized writes to the program database (PDB)
		# conf.env.CXXFLAGS.append('/Fd:testing.pdb') # file name for the program database (PDB) defaults to VCx0.pdb
		
		conf.env.CXXFLAGS.append('/std:c++latest') # enable all features as they become available, including feature removals
		
		conf.env.LINKFLAGS.append('/errorReport:none') # do not send CL crash reports
		# conf.env.LINKFLAGS.append('/OUT:"D:.dll"') # specifies the output file name
		# conf.env.LINKFLAGS.append('/PDB:"D:.pdb"') # creates a program database (PDB) file
		# conf.env.LINKFLAGS.append('/IMPLIB:"D:.lib"')
		# conf.env.LINKFLAGS.append('/PGD:"D:.pgd"') # specifies a .pgd file for profile-guided optimizations
		conf.env.LINKFLAGS.append('/NXCOMPAT') # tested to be compatible with the Windows Data Execution Prevention feature
		conf.env.LINKFLAGS.append('/DYNAMICBASE') # generate an executable image that can be randomly rebased at load time 
		conf.env.LINKFLAGS.append('/NOLOGO') # suppress startup banner
		conf.env.MSVC_MANIFEST = False # disable waf manifest behavior
		# conf.env.LINKFLAGS.append('/MANIFEST') # creates a side-by-side manifest file and optionally embeds it in the binary
		# conf.env.LINKFLAGS.append('/MANIFESTUAC:"level=\'asInvoker\' uiAccess=\'false\'"')
		# conf.env.LINKFLAGS.append('/ManifestFile:".dll.intermediate.manifest"')
		# conf.env.LINKFLAGS.append('/SUBSYSTEM') # how to run the .exe file
		# conf.env.LINKFLAGS.append('/DLL') # builds a DLL
		# conf.env.LINKFLAGS.append('/TLBID:1') # resource ID of the linker-generated type library
		
		conf.env.ARFLAGS.append('/NOLOGO')

		if is_x86(conf):
			conf.env.LINKFLAGS.append('/MACHINE:X86')
			conf.env.ARFLAGS.append('/MACHINE:X86')
		else:
			conf.env.LINKFLAGS.append('/MACHINE:X64')
			conf.env.ARFLAGS.append('/MACHINE:X64')
			
		if is_x86(conf):
			conf.env.MSVC_TARGETS = ['x86']
		else:
			conf.env.MSVC_TARGETS = ['x86_amd64'] # means x64 when using visual studio express for desktop
		
	else:
		if is_x86(conf) == 'x86':
			conf.env.CXXFLAGS.append('-m32')
		else:
			conf.env.CXXFLAGS.append('-m64')

		conf.env.CXXFLAGS.append('-std=c++14')
	
	if is_darwin():
		conf.env.env.CXX	= ['clang++']
		conf.env.CXXFLAGS.append('-stdlib=libc++')
		conf.env.LINKFLAGS.append('-stdlib=libc++')

def configure_debug(conf):
	if is_windows():

		conf.env.CXXFLAGS.append('/RTC1') # run-time error checks (stack frame & uninitialized used variables)
		# conf.env.CXXFLAGS.append('/ZI') # produces a program database in a format that supports the Edit and Continue feature.
		conf.env.CXXFLAGS.append('/Z7') # embeds the program database
		conf.env.CXXFLAGS.append('/Od') # disable optimizations
		conf.env.CXXFLAGS.append('/Oy-') # speeds function calls (should be specified after others /O args)

		if is_static(conf):
			conf.env.CXXFLAGS.append('/MTd')
		elif is_shared(conf):
			conf.env.CXXFLAGS.append('/MDd')

		conf.env.LINKFLAGS.append('/MAP') # creates a mapfile
		conf.env.LINKFLAGS.append('/MAPINFO:EXPORTS') # includes exports information in the mapfile
		conf.env.LINKFLAGS.append('/DEBUG') # creates debugging information
		conf.env.LINKFLAGS.append('/INCREMENTAL') # incremental linking

	else:
		conf.env.CXXFLAGS.append('-g')

	conf.env.DEFINES.append('DEBUG')

def configure_release(conf):
	if is_windows():
	
		# conf.env.CXXFLAGS.append('/Zi') # produces a program database (PDB) does not affect optimizations

		# About COMDATs, linker requires that functions be packaged separately as COMDATs to EXCLUTE or ORDER individual functions in a DLL or .exe file.
		conf.env.CXXFLAGS.append('/Gy') # allows the compiler to package individual functions in the form of packaged functions (COMDATs)
										
		conf.env.CXXFLAGS.append('/GL') # enables whole program optimization
		conf.env.CXXFLAGS.append('/O2') # generate fast code
		conf.env.CXXFLAGS.append('/Oi') # request to the compiler to replace some function calls with intrinsics
		conf.env.CXXFLAGS.append('/Oy-') # speeds function calls (should be specified after others /O args)

		if is_static(conf):
			conf.env.CXXFLAGS.append('/MT')
		elif is_shared(conf):
			conf.env.CXXFLAGS.append('/MD')

		# conf.env.LINKFLAGS.append('/DEF:"D:.def"')
		conf.env.LINKFLAGS.append('/LTCG') # perform whole-program optimization
		# conf.env.LINKFLAGS.append('/LTCG:incremental') # perform incremental whole-program optimization
		conf.env.ARFLAGS.append('/LTCG')
		conf.env.LINKFLAGS.append('/OPT:REF') # eliminates functions and data that are never referenced
		conf.env.LINKFLAGS.append('/OPT:ICF') # to perform identical COMDAT folding
		if is_x86(conf):
			conf.env.LINKFLAGS.append('/SAFESEH') # image will contain a table of safe exception handlers

	else:
		conf.env.CXXFLAGS.append('-O3')

def configure(conf):

	conf.setenv('x86')
	if is_windows():
		conf.env.MSVC_VERSIONS = ['msvc 14.0']
		conf.env.MSVC_TARGETS = ['x86']
	conf.load('compiler_cxx')

	conf.setenv('x64')
	if is_windows():
		conf.env.MSVC_VERSIONS = ['msvc 14.0']
		conf.env.MSVC_TARGETS = ['x86_amd64'] # means x64 when using visual studio express for desktop
	conf.load('compiler_cxx')


def dep_system(bld, libs):
	bld.env['LIB'] += libs
	
def dep_static_release(name, fullname, lib):
	
	global bldcontext
	bld = bldcontext

	deppath = 'dep/' + osname() + '/' + arch(bld) + '/' + fullname + '/' + link_static()
	includes = deppath + '/include'
	libpath = deppath + '/lib'
	
	bld.env['INCLUDES_' + name]		= list_include(bld, [includes])
	bld.env['STLIBPATH_' + name]	= list_include(bld, [libpath])
	bld.env['STLIB_' + name]		= lib
	
def dep_static(name, fullname, lib, libdebug):

	global bldcontext
	bld = bldcontext

	deppath = 'dep/' + osname() + '/' + arch(bld) + '/' + fullname + '/' + link_static() + variant(bld)
	includes = deppath + '/include'
	libpath = deppath + '/lib'
	
	bld.env['INCLUDES_' + name]		= list_include(bld, [includes])
	bld.env['STLIBPATH_' + name]	= list_include(bld, [libpath])
	
	if is_debug():
		bld.env['STLIB_' + name]	= libdebug
	else:
		bld.env['STLIB_' + name]	= lib
		
	
def dep_shared_release(name, fullname, lib):
	
	global bldcontext
	bld = bldcontext

	deppath = 'dep/' + osname() + '/' + arch(bld) + '/' + fullname + '/' + link_shared()
	includes = deppath + '/include'
	libpath = deppath + '/lib'
	
	bld.env['INCLUDES_' + name]		= list_include(bld, [includes])
	bld.env['LIBPATH_' + name]		= list_include(bld, [libpath])
	bld.env['LIB_' + name]			= lib
	
def dep_shared(name, fullname, lib, libdebug):

	global bldcontext
	bld = bldcontext

	deppath = 'dep/' + osname() + '/' + arch(bld) + '/' + fullname + '/' + link_shared() + variant(bld)
	includes = deppath + '/include'
	libpath = deppath + '/lib'
	
	bld.env['INCLUDES_' + name]		= list_include(bld, [includes])
	bld.env['LIBPATH_' + name]		= list_include(bld, [libpath])
	
	if is_debug():
		bld.env['LIB_' + name]		= libdebug
	else:
		bld.env['LIB_' + name]		= lib
	
class CacheConf:
	def __init__(self):
		self.remote = ''
		self.location = ''

def find_cache_conf():
	if not os.path.exists('../settings.glm'):
		return None

	config = ConfigParser.RawConfigParser()
	config.read('../settings.glm')

	if not config.has_section('GOLEM'):
		return None

	conf = CacheConf()

	# cache remote
	if not config.has_option('GOLEM', 'cache.remote'):
		return None
	
	remote = config.get('GOLEM', 'cache.remote')

	if not remote:
		return None

	conf.remote = remote.strip('\'"')

	# cache location
	if not config.has_option('GOLEM', 'cache.location'):
		location = os.path.join(os.path.expanduser("~"), '.cache', 'golem', 'builds')
	else:
		location = config.get('GOLEM', 'cache.location')

	if not location:
		return None

	conf.location = location.strip('\'"')

	# return cache configuration
	return conf

class Dependency:
	def __init__(self):
		self.name = ''
		self.repo = ''
		self.version = 'latest'
		self.system = sys.platform
		self.compiler = ''
		self.arch = platform.machine().lower()
		self.runtime = 'shared'
		self.target = 'shared'
		self.variant = 'release'
		self.hash = 'DEFAULT'
	def __str__(self):
		ret = ''
		ret += 'Name' 	+ '\t\t' + self.name + '\n'
		ret += 'Repo' 	+ '\t\t' + self.repo + '\n'
		ret += 'Version' + '\t\t' + self.version + '\n'
		ret += 'System' 	+ '\t\t' + self.system + '\n'
		ret += 'Compiler' + '\t' + self.compiler + '\n'
		ret += 'Arch' 	+ '\t\t' + self.arch + '\n'
		ret += 'Runtime' + '\t\t' + self.runtime + '\n'
		ret += 'Target' 	+ '\t\t' + self.target + '\n'
		ret += 'Variant' + '\t\t' + self.variant + '\n'
		ret += 'Hash' 	+ '\t\t' + self.hash
		# ret += str(self.__dict__)
		return ret

class Project:
	def __init__(self):
		self.cache = []
		self.deps = []

	def __str__(self):
		ret = ''
		ret += 'Cache' + '\t' + str(self.cache) + '\n'
		ret += 'Deps' + '\t' + str(self.deps)
		return ret
	
	def get_deps(self):
		ret = []
		for fields in self.deps:
			dep = Dependency()
			for index, field in enumerate(fields):
				if not field:
					continue
				if index == 0:
					dep.name = field
				if index == 1:
					dep.repo = field
				if index == 2:
					dep.version = field
			if dep.name:
				ret.append(dep)
		return ret

def target(ttype = '', name = '', defines = [], defines_shared = [], defines_static = [], includes = [], source = [], cxxflags = [], linkflags = [], use = [], windeps = [], unideps = [], deps = [], install = ''):

	if not ttype in 'program library':
		return

	global bldcontext
	bld = bldcontext

	install_path=''
	if install != '':
		install_path = install

	if is_shared(bld):
		defines += defines_shared
	else:
		defines += defines_static
	
	if not is_windows():
		cxxflags.append('-pthread')
		linkflags.append('-pthread')
	
	if ttype == 'library':
		ttypestr = 'lib'
	elif ttype == 'program':
		ttypestr = 'app'

	identifier = hash_identifier(bld.env.CXXFLAGS + bld.env.CFLAGS + bld.env.LINKFLAGS + bld.env.ARFLAGS + bld.env.DEFINES)
	global buildpath
	cachepath = name + '-' + ttypestr + '-' + 'master' + '-' + buildpath + '-' + identifier

	if bld.options.test:
		# targetpath = os.path.join(bld.options.dir, 'bin', bld.options.variant)
		targetpath = bld.options.variant
	else:
		targetpath = cachepath

	pro = Project()
	if hasattr(project, 'prepare'):
		project.prepare(pro)
	pro_deps = pro.get_deps()

	for _dep in deps:
		for dep in pro_deps:
			if _dep == dep.name:

				cache_conf = find_cache_conf()
				if not cache_conf:
					print("ERROR: no valid cache configuration found")
					return
				
				cache_location = cache_conf.location
				cache_repo = cache_conf.remote
				
				cache_dir = cache_location
				if not os.path.exists(cache_dir):
					os.makedirs(cache_dir)

				dep_path_base = dep.name + '-' + 'lib' + '-' + 'master' + '-' + str(dep.version)
				dep_path_build = dep_path_base + '-' + buildpath

				# dep cache path with the current combination of flags (identifier)
				dep_path_name = dep_path_build + '-' + identifier
				dep_path_include = os.path.join(cache_dir, dep_path_base)
				dep_path = os.path.join(cache_dir, dep_path_name)

				if not os.path.exists(dep_path):
					# dep cache path with an independant combination of flags (default)
					dep_path_name = dep_path_build + '-' + 'default' 
					dep_path = os.path.join(cache_dir, dep_path_name)

				if not os.path.exists(dep_path):
					print "INFO: can't find the dependency " + dep.name
					print "Search in the cache repository..."

					os.makedirs(dep_path)

					# search the corresponding branch in the cache repo (with the right version)
					ret = subprocess.call(['git', 'ls-remote', '--heads', '--exit-code', cache_repo, dep_path_name])
					if ret:
						# no such a branch, have to build and cache

						# building
						build_dir = os.path.join(cache_dir, 'build')
						if os.path.exists(build_dir):
							shutil.rmtree(build_dir)
						os.makedirs(build_dir)
						
						ret = subprocess.call(['git', 'clone', '--recursive', '--depth', '1', '--branch', dep.version, '--', dep.repo, '.'], cwd=build_dir)
						if ret:
							print "ERROR: cloning " + dep.repo + ' ' + dep.version
							return

						golem_dir = os.path.join(build_dir, 'golem')
						if not os.path.exists(golem_dir):
							print "ERROR: can't find golem to build the dependency"
							return
						
						ret = subprocess.call(['make', 'build', 'runtime=' + bld.options.runtime, 'link=' + bld.options.link, 'arch=' + bld.options.arch, 'variant=' + bld.options.variant], cwd=build_dir)
						if ret:
							print "ERROR: dependency build failed"
							return

						# caching
						ret = subprocess.call(['git', 'clone', '--depth', '1', '--', cache_repo, '.'], cwd=dep_path)
						if ret:
							print "ERROR: git clone --depth 1 -- " + cache_repo + ' .'
							return
						ret = subprocess.call(['git', 'checkout', '-b', name], cwd=dep_path)
						if ret:
							print "ERROR: git checkout -b " + name
						
						bin_dir = os.path.join(golem_dir, 'out')
						bin_dir = os.path.join(bin_dir, bld.options.variant)

						if not os.path.exists(bin_dir):
							print "ERROR: no binaries found in the dependency build"
							return

						distutils.dir_util.copy_tree(bin_dir, dep_path)

						include_dir = os.path.join(build_dir, 'include')

						if not os.path.exists(include_dir):
							print "ERROR: no include found in the dependency build"
							return
						
						distutils.dir_util.copy_tree(include_dir, dep_path_include)

					else:
						# branch found, have to clone it
						ret = subprocess.call(['git', 'clone', '--depth', '1', '--branch', name, '--', cache_repo, '.'], cwd=dep_path)
						if ret:
							print "ERROR: git clone --depth 1 --branch " + name + ' -- ' + cache_repo + ' .'
							return
					
				# use cache :)
				print list_include(bld, [dep_path])
				bld.env['INCLUDES_' + dep.name]		= list_include(bld, [dep_path_include])
				bld.env['LIBPATH_' + dep.name]		= list_include(bld, [dep_path])
				bld.env['LIB_' + dep.name]			= dep.name + variant(bld)
				use.append(dep.name)

				distutils.dir_util.copy_tree(dep_path, os.path.join(bld.out_dir, targetpath))


	if ttype == 'library':
		prefix = ''
		if is_windows():
			prefix = 'lib'
		target = targetpath + '/' + prefix + name + variant(bld)
	elif ttype == 'program':
		target = targetpath + '/' + name + variant(bld)

	if ttype == 'library':
		if is_shared(bld):
			ttarget = bld.shlib(
				defines			= defines,
				includes		= list_include(bld, make_project_path_array(bld, includes)),
				source			= list_source(bld, make_project_path_array(bld, source)),
				target			= target,
				cxxflags		= cxxflags,
				cflags			= cxxflags,
				linkflags		= linkflags,
				name			= name,
				use				= use,
				install_path	= make_project_path(bld, install_path)
			)
		elif is_static(bld):
			ttarget = bld.stlib(
				defines			= defines,
				includes		= list_include(bld, make_project_path_array(bld, includes)),
				source			= list_source(bld, make_project_path_array(bld, source)),
				target			= target,
				cxxflags		= cxxflags,
				cflags			= cxxflags,
				linkflags		= linkflags,
				name			= name,
				use				= use,
				install_path	= make_project_path(bld, install_path)
			)
		else:
			print "ERROR: no options found"
			return

	elif ttype == 'program':
		ttarget = bld.program(
			defines			= defines,
			includes		= list_include(bld, make_project_path_array(bld, includes)),
			source			= list_source(bld, make_project_path_array(bld, source)),
			target			= target,
			name			= name,
			cxxflags		= cxxflags,
			cflags			= cxxflags,
			linkflags		= linkflags,
			use				= use,
			install_path	= make_project_path(bld, install_path)
		)
	
	if is_windows():
		dep_system(
			bld		= ttarget,
			libs	= windeps
		)
	else:
		dep_system(
			bld		= ttarget,
			libs	= unideps
		)

def library(name = '', defines = [], defines_shared = [], defines_static = [], includes = [], source = [], cxxflags = [], linkflags = [], use = [], windeps = [], unideps = [], deps = [], install = ''):
	target('library', name, defines, defines_shared, defines_static, includes, source, cxxflags, linkflags, use, windeps, unideps, deps, install)

def program(name = '', defines = [], defines_shared = [], defines_static = [], includes = [], source = [], cxxflags = [], linkflags = [], use = [], windeps = [], unideps = [], deps = [], install = ''):
	target('program', name, defines, defines_shared, defines_static, includes, source, cxxflags, linkflags, use, windeps, unideps, deps, install)

def branch_name(name, system, compiler, arch, runtime, target, variant, flags):
	return name + '-' + system + '-' + compiler + '-' + arch + '-' + runtime + '-' + target + '-' + variant + '-' + identifier(flags)

def build(bld):

	global bldcontext
	bldcontext = bld

	project_path = os.path.join(bld.options.dir, 'project.glm')
	if not os.path.exists(project_path):
		print "ERROR: can't find " + project_path
		return
	
	global project
	project = imp.load_source('project', project_path)

	bld.load_envs()
	if is_x86(bld):
		bld.env = bld.all_envs['x86'].derive()
	else:
		bld.env = bld.all_envs['x64'].derive()

	configure_init(bld)
	configure_default(bld)

	if is_debug(bld):
		configure_debug(bld)
	else:
		configure_release(bld)

	bld.env.CFLAGS = bld.env.CXXFLAGS
	
	global buildpath
	buildpath = osname_min() + '-' + compiler_min(bld) + '-' + arch_min(bld) + '-' + runtime_min(bld) + '-' + link_min(bld) + '-' + variant_min(bld)

	myself = sys.modules[__name__]
	project.build(myself)

	if bld.options.test and hasattr(project, 'test'):
		project.test(myself)

def repo_clear(path):
	output = subprocess.check_output(['git', 'status', '-s'], cwd=path)
	if output:
		print(output)
		return False
	return True

def repo_dirty(path):
	return not repo_clear(path)

# commit build (all) to specific repository (according project file)
def release(bld):
	project_path = os.path.join(bld.options.dir, 'project.glm')
	if not os.path.exists(project_path):
		print "ERROR: no project file found " + project_path
		return

	if bld.options.major:
		bumping = 'major'
	elif bld.options.minor:
		bumping = 'minor'
	elif bld.options.patch:
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

	if repo_dirty(bld.options.dir):
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
	
	output = subprocess.check_output(['git', 'add', 'project.glm'], cwd=bld.options.dir)
	if output:
		print output

	output = subprocess.check_output(['git', 'commit', '-m', message], cwd=bld.options.dir)
	if output:
		print output
	
	output = subprocess.check_output(['git', 'tag', '-a', newversion, '-m', message], cwd=bld.options.dir)
	if output:
		print output
		
	print "Released " + newversion