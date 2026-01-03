from golemcpp.golem import helpers


class BuildTarget:
    def __init__(self, config, defines, includes, source, target, name,
                 cxxflags, cflags, linkflags, ldflags, use, uselib, moc,
                 features, install_path, vnum, depends_on, lib, libpath, stlib,
                 stlibpath, cppflags, framework, frameworkpath, rpath, cxxdeps,
                 ccdeps, linkdeps, env_defines, env_cxxflags, env_includes,
                 env_isystem):

        self.config = config

        self.target = target
        self.name = name
        self.vnum = vnum
        self.install_path = install_path

        self.defines = defines
        self.defines = helpers.filter_unique(self.defines)
        self.includes = includes
        self.includes = helpers.filter_unique(self.includes)
        self.source = source
        # self.source = helpers.filter_unique(self.source)
        self.cxxflags = cxxflags
        self.cxxflags = helpers.filter_unique(self.cxxflags)
        self.cflags = cflags
        self.cflags = helpers.filter_unique(self.cflags)
        self.linkflags = linkflags
        self.linkflags = helpers.filter_unique(self.linkflags)
        self.ldflags = ldflags
        self.ldflags = helpers.filter_unique(self.ldflags)
        self.use = use
        self.use = helpers.filter_unique(self.use)
        self.uselib = uselib
        self.uselib = helpers.filter_unique(self.uselib)
        self.moc = moc
        self.moc = helpers.filter_unique(self.moc)
        self.features = features
        self.features = helpers.filter_unique(self.features)
        self.depends_on = depends_on
        self.depends_on = helpers.filter_unique(self.depends_on)
        self.lib = lib
        self.lib = helpers.filter_unique(self.lib)
        self.libpath = libpath
        self.libpath = helpers.filter_unique(self.libpath)
        self.stlib = stlib
        self.stlib = helpers.filter_unique(self.stlib)
        self.stlibpath = stlibpath
        self.stlibpath = helpers.filter_unique(self.stlibpath)
        self.cppflags = cppflags
        self.cppflags = helpers.filter_unique(self.cppflags)
        self.framework = framework
        self.framework = helpers.filter_unique(self.framework)
        self.frameworkpath = frameworkpath
        self.frameworkpath = helpers.filter_unique(self.frameworkpath)
        self.rpath = rpath
        self.rpath = helpers.filter_unique(self.rpath)
        self.cxxdeps = cxxdeps
        self.cxxdeps = helpers.filter_unique(self.cxxdeps)
        self.ccdeps = ccdeps
        self.ccdeps = helpers.filter_unique(self.ccdeps)
        self.linkdeps = linkdeps
        self.linkdeps = helpers.filter_unique(self.linkdeps)

        self.env_defines = env_defines
        self.env_defines = helpers.filter_unique(self.env_defines)
        self.env_cxxflags = env_cxxflags
        self.env_cxxflags = helpers.filter_unique(self.env_cxxflags)
        self.env_includes = env_includes
        self.env_includes = helpers.filter_unique(self.env_includes)
        self.env_isystem = env_isystem
        self.env_isystem = helpers.filter_unique(self.env_isystem)
