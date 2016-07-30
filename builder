#!/usr/bin/env python

import os
import sys
import platform


def list_include(bld, includes):
	return [bld.srcnode.find_dir(x).abspath() for x in includes]

def list_source(bld, source):
	return [item for sublist in [bld.srcnode.find_dir(x).ant_glob('*.cpp') for x in source] for item in sublist]

def link_static():
	return 'static'
	
def link_shared():
	return 'shared'
	
def link(bld):
	return bld.options.link
	
def is_static(bld):
	return bld.options.link == link_static()

def is_shared(bld):
	return bld.options.link == link_shared()

def arch(bld):
	return bld.options.arch

def variant_debug():
	return 'debug'

def variant_release():
	return 'release'

def variant(bld):
	variant = ''
	if bld.variant == variant_debug():
		variant = '-' + variant_debug()
	return variant
		
def is_debug(bld):
	return bld.variant == variant_debug()
		
def is_release(bld):
	return bld.variant == variant_release()

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

def machine():
    if os.name == 'nt' and sys.version_info[:2] < (2,7):
        return os.environ.get("PROCESSOR_ARCHITEW6432", 
               os.environ.get('PROCESSOR_ARCHITECTURE', ''))
    else:
        return platform.machine()

def osarch():
    machine2bits = {'amd64': 'x64', 'x86_64': 'x64', 'i386': 'x86', 'x86': 'x86'}
    return machine2bits.get(machine().lower(), None)

def is_x86(conf):
	return conf.options.arch == 'x86'

def is_x64(conf):
	return conf.options.arch == 'x64'

def options(opt):
	opt.load('compiler_cxx')
	# opt.add_option("--variant", action="store", default='debug', help="Runtime Linking")
	opt.add_option("--runtime", action="store", default='shared', help="Runtime Linking")
	opt.add_option("--link", action="store", default='shared', help="Library Linking")
	opt.add_option("--arch", action="store", default='x86', help="Target Architecture")
	
	if is_windows(): 
		opt.add_option("--nounicode", action="store_true", default=False, help="Unicode Support")
	else: 
		opt.add_option("--nounicode", action="store_true", default=True, help="Unicode Support")

def configure_default(conf):
	conf.env.DEFINES=[]
	conf.env.CXXFLAGS=[]
	conf.env.CFLAGS=[]
	conf.env.LINKFLAGS=[]

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
		
		conf.env.LINKFLAGS.append('/errorReport:none') # do not send CL crash reports
		# conf.env.LINKFLAGS.append('/OUT:"D:.dll"') # specifies the output file name
		# conf.env.LINKFLAGS.append('/PDB:"D:.pdb"') # creates a program database (PDB) file
		# conf.env.LINKFLAGS.append('/IMPLIB:"D:.lib"')
		# conf.env.LINKFLAGS.append('/PGD:"D:.pgd"') # specifies a .pgd file for profile-guided optimizations
		conf.env.LINKFLAGS.append('/NXCOMPAT') # tested to be compatible with the Windows Data Execution Prevention feature
		conf.env.LINKFLAGS.append('/DYNAMICBASE') # generate an executable image that can be randomly rebased at load time 
		conf.env.LINKFLAGS.append('/NOLOGO') # suppress startup banner
		# conf.env.LINKFLAGS.append('/MANIFEST') # creates a side-by-side manifest file and optionally embeds it in the binary
		# conf.env.LINKFLAGS.append('/MANIFESTUAC:"level=\'asInvoker\' uiAccess=\'false\'"')
		# conf.env.LINKFLAGS.append('/ManifestFile:".dll.intermediate.manifest"')
		# conf.env.LINKFLAGS.append('/SUBSYSTEM') # how to run the .exe file
		# conf.env.LINKFLAGS.append('/DLL') # builds a DLL
		# conf.env.LINKFLAGS.append('/TLBID:1') # resource ID of the linker-generated type library

		if is_x86(conf):
			conf.env.LINKFLAGS.append('/MACHINE:X86')
		else:
			conf.env.LINKFLAGS.append('/MACHINE:X64')
			
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
		conf.env.linkflags.append('-stdlib=libc++')

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
		conf.env.LINKFLAGS.append('/LTCG:incremental') # perform whole-program optimization
		conf.env.LINKFLAGS.append('/OPT:REF') # eliminates functions and data that are never referenced
		conf.env.LINKFLAGS.append('/OPT:ICF') # to perform identical COMDAT folding
		if is_x86(conf):
			conf.env.LINKFLAGS.append('/SAFESEH') # image will contain a table of safe exception handlers

	else:
		conf.env.CXXFLAGS.append('-O3')

def configure(conf):
	conf.setenv('debug')
	configure_default(conf)
	configure_debug(conf)
	conf.env.CFLAGS = conf.env.CXXFLAGS
	conf.load('compiler_cxx')

	conf.setenv('release')
	configure_default(conf)
	configure_release(conf)
	conf.env.CFLAGS = conf.env.CXXFLAGS
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
	
	if bld.variant == 'debug':
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
	
	if bld.variant == 'debug':
		bld.env['LIB_' + name]		= libdebug
	else:
		bld.env['LIB_' + name]		= lib
	
def library(name = '', defines = [], includes = [], source = [], cxxflags = [], linkflags = [], deps = [], windeps = [], unideps = [], install = ''):

	global bldcontext
	bld = bldcontext

	prefix = ''
	if is_windows():
		prefix = 'lib'
	
	buildpath = '/' + osname() + '/' + arch(bld) + '/' + link(bld) + variant(bld)
	
	target = prefix + name + variant(bld)

	install_path=''
	if install != '':
		install_path = install

	if not is_windows():
		cxxflags.append('-pthread')
		linkflags.append('-pthread')

	if is_shared(bld):
		lib = bld.shlib(
			defines			= defines,
			includes		= list_include(bld, includes),
			source			= list_source(bld, source),
			target			= target,
			cxxflags		= cxxflags,
			cflags			= cxxflags,
			linkflags		= linkflags,
			name			= name,
			use				= deps,
			install_path	= install_path
		)
	elif is_static(bld):
		lib = bld.stlib(
			defines			= defines,
			includes		= list_include(bld, includes),
			source			= list_source(bld, source),
			target			= target,
			cxxflags		= cxxflags,
			cflags			= cxxflags,
			linkflags		= linkflags,
			name			= name,
			use				= deps,
			install_path	= install_path
		)
	
	if is_windows():
		dep_system(
			bld		= lib,
			libs	= windeps
		)
	else:
		dep_system(
			bld		= lib,
			libs	= unideps
		)
	
def program(name = '', defines = [], includes = [], source = [], cxxflags = [], linkflags = [], deps = [], windeps = [], unideps = [], install = ''):
	global bldcontext
	bld = bldcontext

	buildpath = '/' + osname() + '/' + arch(bld) + '/' + bld.variant

	install_path=''
	if install != '':
		install_path = install

	program = bld.program(
		defines			= defines,
		includes		= list_include(bld, includes),
		source			= list_source(bld, source),
		target			= name + variant(bld),
		name			= name,
		cxxflags		= cxxflags,
		cflags			= cxxflags,
		linkflags		= linkflags,
		use				= deps,
		install_path	= install_path
	)
	
	if is_windows():
		dep_system(
			bld		= program,
			libs	= windeps
		)
	else:
		dep_system(
			bld		= program,
			libs	= unideps
		)

def build_checks():
	global bldcontext
	bld = bldcontext
	# verify options
	if not bld.options.arch in ['x86', 'x64']:
		bld.fatal("'" + bld.options.arch + "' is not a valid target architecture, instead use: ['x86', 'x64']")
	if not bld.options.link in ['static', 'shared']:
		bld.fatal("'" + bld.options.link + "' is not a valid linking option, instead use: ['static', 'shared']")
	if not bld.options.runtime in ['static', 'shared']:
		bld.fatal("'" + bld.options.runtime + "' is not a valid runtime-linking option, instead use: ['static', 'shared']")

def build(bld):
	global bldcontext
	bldcontext = bld
	build_checks()