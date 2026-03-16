def configure(project):
    

    project.dependency(name='gsl',
                       repository='https://github.com/microsoft/GSL.git',
                       version='^4.2.0',
                       shallow=True)
    
    project.dependency(name='json',
                       repository='https://github.com/nlohmann/json.git',
                       version='^3.0.0',
                       shallow=True)

    project.program(name='hello-cache',
                    source=['src'],
                    deps=['json', 'gsl'])