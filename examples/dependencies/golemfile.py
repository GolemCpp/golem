
def configure(project):
    
    project.dependency(name='json',
                       repository='https://github.com/nlohmann/json.git',
                       version='^3.0.0',
                       shallow=True)

    project.program(name='hello-dependencies',
                    source=['src'],
                    deps=['json'])