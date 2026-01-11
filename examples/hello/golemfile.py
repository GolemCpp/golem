
def configure(project):
    
    # The project variable is the entry point to declare dependencies, libraries and programs that make up the project.

    project.program(name='hello',
                    source=['src'])
    
    # 'hello' is the name of the program being compiled (e.g. hello.exe or hello-debug.exe)
    # 'src' is the directory where all source files are expected to be found (recusrively) for 'hello'