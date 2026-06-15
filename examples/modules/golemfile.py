
def configure(project):

    project.dependency(name='mylogger',
                       repository='./mylogger')

    project.export(name='config',
                   header_only=True,
                   cxx_standard=26)

    build_task = project.library(name='myfigures',
                                 source=['myfigures/src'],
                                 use=['config'])
    
    export_task = project.export(name='myfigures')
    
    build_task.when(link='shared', defines=['MYFIGURES_API_EXPORT'])
    export_task.when(link='shared', defines=['MYFIGURES_API_IMPORT'])
    build_task.when(osystem='linux', cxxflags=['-fvisibility=hidden', '-fvisibility-inlines-hidden'])
    
    project.program(name='hello-modules',
                    source=['src'],
                    use=['config', 'myfigures'],
                    deps=['mylogger'])