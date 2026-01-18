def configure(project):
    task = project.program(name='hello-qt',
                    source=['src'],
                    moc=['src'],
                    features=['QT6CORE', 'QT6WIDGETS'])
    
    task.when(compiler='msvc', cxxflags='/std:c++17')
    task.when(compiler='!msvc', cxxflags='-std=c++17')