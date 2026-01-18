def configure(project):
    task = project.program(name='hello-qt-qml',
                    source=['src', 'qml'],
                    moc=['src'],
                    features=['QT6CORE', 'QT6QML', 'QT6QUICK'],
                    qmldirs=['qml'])
    
    task.when(compiler='msvc', cxxflags='/std:c++17')
    task.when(compiler='!msvc', cxxflags='-std=c++17')