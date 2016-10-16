#!/usr/bin/env python

import sys
sys.dont_write_bytecode = True

import imp
builder = imp.load_source('builder', 'builder')

import os
top = os.path.dirname(os.path.abspath('__file__'))
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

def everything(bld):
	import waflib.Options
	waflib.Options.commands = ['configure'] + all_build + waflib.Options.commands

from waflib.Context import Context
class tmp(Context):
	cmd = 'everything'
	fun = 'everything'

def test(bld):
	import waflib.Options
	waflib.Options.commands = ['configure', 'build'] + waflib.Options.commands

def release(bld):
	builder.release(bld)

from waflib.Context import Context
class tmp(Context):
	cmd = 'release'
	fun = 'release'
