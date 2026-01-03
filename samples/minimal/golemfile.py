
def configure(project):
    
    project.dependency(name='json',
                       repository='https://github.com/nlohmann/json.git',
                       version='^3.0.0',
                       shallow=True)

    project.library(name='mylib',
                    includes=['mylib/include'],
                    source=['mylib/src'],
                    defines=['FOO_API_EXPORT'])

    project.export(name='mylib',
                   includes=['mylib/include'],
                   defines=['FOO_API_IMPORT'])

    project.program(name='hello',
                    source=['src'],
                    use=['mylib'],
                    deps=['json'])