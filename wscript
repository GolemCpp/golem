#!/usr/bin/env python3

from waflib.TaskGen import feature, before_method, after_method, extension
from waflib.Build import BuildContext, CleanContext, \
    InstallContext, UninstallContext
from waflib.Configure import conf, ConfigurationContext
from waflib.Context import Context
from waflib import Configure
from waflib import Task, TaskGen
import waflib
import os
import importlib
import importlib.util
import sys
sys.dont_write_bytecode = True

def import_from_file(name, file_path):
    loader = importlib.machinery.SourceFileLoader(name, file_path)

    spec = importlib.util.spec_from_loader(loader.name, loader)

    module = importlib.util.module_from_spec(spec)

    sys.modules[name] = module

    spec.loader.exec_module(module)

    return module

builder = import_from_file('builder', '$builder_path')

top = ''
out = 'obj'

Configure.autoconfig = False


def options(opt):
    builder.options(opt)


def configure(conf):
    builder.configure(conf)


def build(bld):
    waflib.Tools.c_preproc.go_absolute = True
    waflib.Tools.c_preproc.standard_includes = []

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
            print("ERROR: export path doesn't exist")
            return

    builder.build(bld)


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
    waflib.Options.commands = ['configure'] + \
        all_build + waflib.Options.commands


class tmp(Context):
    cmd = 'everything'
    fun = 'everything'


# Rebuild


def rebuild(bld):
    import waflib.Options
    waflib.Options.commands = ['distclean', 'configure', 'build'
                               ] + waflib.Options.commands


class tmp(Context):
    cmd = 'rebuild'
    fun = 'rebuild'


# Package


def package(bld):
    builder.package(bld)


class tmp(BuildContext):
    cmd = 'package'
    fun = 'package'


# Requirements


def requirements(bld):
    builder.requirements(bld)


class tmp(BuildContext):
    cmd = 'requirements'
    fun = 'requirements'


# Export


def export(bld):
    builder.export(bld)


class tmp(BuildContext):
    cmd = 'export'
    fun = 'export'


# Resolve


def resolve(bld):
    builder.resolve(bld)


class tmp(BuildContext):
    cmd = 'resolve'
    fun = 'resolve'


# Dependencies


def dependencies(bld):
    builder.dependencies(bld)


class tmp(BuildContext):
    cmd = 'dependencies'
    fun = 'dependencies'


# CppCheck


def cppcheck(bld):
    builder.cppcheck(bld)


class tmp(BuildContext):
    cmd = 'cppcheck'
    fun = 'cppcheck'


# clang-tidy


def clang_tidy(bld):
    builder.clang_tidy(bld)


class tmp(BuildContext):
    cmd = 'clang-tidy'
    fun = 'clang_tidy'


# Qt stuff


@feature('cxx')
@after_method('process_source')
@before_method('apply_incpaths')
def add_includes_paths(self):
    incs = set(self.to_list(getattr(self, 'includes', '')))
    incs = [str(inc) for inc in incs]
    self.includes = sorted(incs)


@TaskGen.extension('.mm')
def create_objc_task(self, node):
    return self.create_compiled_task('cxx', node)