def configure(project):
    task = project.program(name='hello-conditions',
                    source=['src'])
    task.when(osystem="windows", includes=['src/windows'])
    task.when(osystem="linux", includes=['src/linux'])
    task.when(osystem="osx", includes=['src/macos'])