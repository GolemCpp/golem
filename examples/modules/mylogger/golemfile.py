def configure(project):

    build_task = project.library(
        name="mylogger",
        includes=["include", "include/mylogger"],
        source=["src"],
        cxx_standard=23,
    )

    export_task = project.export(name="mylogger", includes=["include"])

    build_task.when(link="shared", defines=["MYLOGGER_API_EXPORT"])
    export_task.when(link="shared", defines=["MYLOGGER_API_IMPORT"])
    build_task.when(
        osystem="linux", cxxflags=["-fvisibility=hidden", "-fvisibility-inlines-hidden"]
    )
