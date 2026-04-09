def configure(project):

    task = project.library(name='hello-advanced-lib',
                    includes=['include'],
                    source=['src'],
                    defines=['FOO_API_EXPORT'])
    
    task.when(variant='debug', defines=['ADVANCED_LIB_VARIANT=Debug'])
    task.when(variant='release', defines=['ADVANCED_LIB_VARIANT=Release'])

    project.export(name='hello-advanced-lib',
                   includes=['include'],
                   defines=['FOO_API_IMPORT'])