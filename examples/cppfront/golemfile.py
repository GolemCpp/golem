
def configure(project):
    project.program(name='hello-cppfront',
                    source=['src'],
                    cpp2flags=['-p']) # -p is default, no need to specify it, but just to show how to pass cpp2flags