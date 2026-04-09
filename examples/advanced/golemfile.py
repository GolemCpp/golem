def configure(project):
    
    task = project.dependency(name='hello-advanced-lib',
                              repository='./lib',
                              variant='release',
                              defines=['ADVANCED_LIB_MESSAGE=Hello'])
    
    task.when(variant='debug', defines=['ADVANCED_LIB_MESSAGE=World'])

    project.program(name='hello-advanced',
                    source=['src'],
                    deps=['hello-advanced-lib'])