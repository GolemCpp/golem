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
	if not bld.variant and bld.cmd == 'build':
		print("BUILD")
		import waflib.Options
		for x in ['debug', 'release']:
			waflib.Options.commands.append(x)
	else:
		builder.build(bld)
		project.build(builder)

from waflib.Build import BuildContext, CleanContext, \
        InstallContext, UninstallContext

for x in 'debug release'.split():
	class tmp(BuildContext):
		cmd = x
		variant = x