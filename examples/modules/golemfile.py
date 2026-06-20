
def configure(project):

    project.dependency(name='mylogger',
                       repository='./mylogger')

    build_task = project.library(name='myfigures',
                                 source=['myfigures/src'],
                                 cxx_standard=23)
    
    export_task = project.export(name='myfigures')
    
    build_task.when(link='shared', defines=['MYFIGURES_API_EXPORT'])
    export_task.when(link='shared', defines=['MYFIGURES_API_IMPORT'])
    build_task.when(osystem='linux', cxxflags=['-fvisibility=hidden', '-fvisibility-inlines-hidden'])
    
    project.program(name='hello-modules',
                    source=['src'],
                    use=['myfigures'],
                    deps=['mylogger'],
                    cxx_standard=26)