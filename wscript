#!/usr/bin/env python

import sys
sys.dont_write_bytecode = True

import imp
builder = imp.load_source('builder', '$builder_path')

import os
top = ''
out = '.'

import waflib

from waflib import Configure
Configure.autoconfig = True 

def options(opt):
	builder.options(opt)

def configure(conf):
	builder.configure(conf)

def build(bld):
	waflib.Tools.c_preproc.go_absolute=True
	waflib.Tools.c_preproc.standard_includes=[]

	if hasattr(bld, 'opt_arch'):
		bld.options.arch = bld.opt_arch
	
	if hasattr(bld, 'opt_link'):
		bld.options.link = bld.opt_link

	if hasattr(bld, 'opt_variant'):
		bld.options.variant = bld.opt_variant
	
	bld.options.arch = bld.options.arch.lower()
	bld.options.link = bld.options.link.lower()
	bld.options.variant = bld.options.variant.lower()

	if bld.options.export:
		if os.path.exists(bld.options.export):
			bld.add_post_fun(builder.export)
		else:
			print "ERROR: export path doesn't exist"
			return

	builder.build(bld)

from waflib.Build import BuildContext, CleanContext, \
        InstallContext, UninstallContext

# All build combinations

all_build = []

for arch in 'x86 x64'.split():
	for link in 'shared static'.split():
		for variant in 'debug release'.split():
			class tmp(BuildContext):
				cmd = arch + '_' + link + '_' + variant
				opt_arch = arch
				opt_link = link
				opt_variant = variant
				all_build.append(cmd)

# Everything

def everything(bld):
	import waflib.Options
	waflib.Options.commands = ['configure'] + all_build + waflib.Options.commands

from waflib.Context import Context
class tmp(Context):
	cmd = 'everything'
	fun = 'everything'

# Rebuild

def rebuild(bld):
	import waflib.Options
	waflib.Options.commands = ['distclean', 'configure', 'build'] + waflib.Options.commands

from waflib.Context import Context
class tmp(Context):
	cmd = 'rebuild'
	fun = 'rebuild'

# Qt stuff

from waflib.TaskGen import feature, before_method, after_method
@feature('cxx')
@after_method('process_source')
@before_method('apply_incpaths')
def add_includes_paths(self):
	incs = set(self.to_list(getattr(self, 'includes', '')))
	for x in self.compiled_tasks:
		incs.add(x.inputs[0].parent.path_from(self.path))
	self.includes = sorted(incs)