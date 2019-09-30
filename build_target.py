class BuildTarget:
    def __init__(self,
                 config,

                 defines,
                 includes,
                 source,
                 target,
                 name,
                 cxxflags,
                 cflags,
                 linkflags,
                 ldflags,
                 use,
                 uselib,
                 moc,
                 features,
                 install_path,
                 vnum,
                 depends_on,
                 lib,
                 libpath,
                 stlibpath,
                 cppflags,
                 framework,
                 frameworkpath,
                 rpath,
                 cxxdeps,
                 ccdeps,
                 linkdeps,

                 env_defines,
                 env_cxxflags,
                 env_includes,
                 env_isystem):

        self.config = config

        self.defines = defines
        self.includes = includes
        self.source = source
        self.target = target
        self.name = name
        self.cxxflags = cxxflags
        self.cflags = cflags
        self.linkflags = linkflags
        self.ldflags = ldflags
        self.use = use
        self.uselib = uselib
        self.moc = moc
        self.features = features
        self.install_path = install_path
        self.vnum = vnum
        self.depends_on = depends_on
        self.lib = lib
        self.libpath = libpath
        self.stlibpath = stlibpath
        self.cppflags = cppflags
        self.framework = framework
        self.frameworkpath = frameworkpath
        self.rpath = rpath
        self.cxxdeps = cxxdeps
        self.ccdeps = ccdeps
        self.linkdeps = linkdeps

        self.env_defines = env_defines
        self.env_cxxflags = env_cxxflags
        self.env_includes = env_includes
        self.env_isystem = env_isystem
