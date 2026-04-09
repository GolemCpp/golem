def configure(project):

    task = project.program(name='hello-package',
                    source=['src', 'qml'],
                    moc=['src'],
                    features=['QT6CORE', 'QT6QML', 'QT6QUICK'],
                    qmldirs=['qml'])

    task.when(compiler='msvc', cxxflags='/std:c++17')
    task.when(compiler='!msvc', cxxflags='-std=c++17')

    package = project.package(name='hello-package',
                            targets=[
                                'hello-package'
                            ],
                            stripping=True)

    package.deb(prefix='/usr/local',
                subdirectory='share/example/hello-package',
                skeleton='dist/deb/skeleton',
                control='dist/deb/DEBIAN',
                section='misc',
                priority='optional',
                maintainer='John Doe',
                description='Example program to illustrate how to package applications with Golem',
                homepage='https://www.example.com/',
                templates=['share/applications/hello-package.desktop'])

    package.msi(project="dist/msi/wix",
                extensions=['WixUIExtension'],
                cultures=['en-us'],
                installdir_id='INSTALLDIR',
                installdir_files_id='INSTALLDIR_files')

    package.dmg(name='hello-package',
                skeleton='dist/dmg/skeleton',
                background='dist/dmg/background.png')

    package.hook(log_files)


def log_files(context):
    for f in context.files:
        print("{}".format(f.path))