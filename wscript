#!/usr/bin/env python

import sys

import imp
project = imp.load_source('project', '../project')
builder = imp.load_source('builder', 'builder')

top = '.'
out = 'out'

def options(opt):
	builder.options(opt)

def configure(conf):
	builder.configure(conf)

def build(bld):
	if hasattr(bld, 'opt_arch'):
		bld.options.arch = bld.opt_arch
	
	if hasattr(bld, 'opt_link'):
		bld.options.link = bld.opt_link

	if hasattr(bld, 'opt_variant'):
		bld.options.variant = bld.opt_variant
	
	bld.options.arch = bld.options.arch.lower()
	bld.options.link = bld.options.link.lower()
	bld.options.variant = bld.options.variant.lower()

	builder.build(bld)
	project.build(builder)
	if bld.cmd == 'build':
		project.test(builder)

from waflib.Build import BuildContext, CleanContext, \
        InstallContext, UninstallContext

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

def all(ctx):
	import waflib.Options
	waflib.Options.commands = ['configure'] + all_build + waflib.Options.commands

from waflib.Context import Context
class tmp(Context):
	cmd = 'all'
	fun = 'all'

def debug(ctx):
	import waflib.Options
	waflib.Options.commands = ['configure'] + all_build + waflib.Options.commands

from waflib.Context import Context
class tmp(Context):
	cmd = 'all'
	fun = 'all'