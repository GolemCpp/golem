
def configure(project):
    project.program(name='hello-modules',
                    source=['src'],
                    cxx_standard='26')