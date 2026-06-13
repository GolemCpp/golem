
def configure(project):

    project.dependency(name='mylogger',
                       repository='./mylogger')

    project.export(name='config',
                   header_only=True,
                   cxx_standard=26)

    project.library(name='myfigures',
                    source=['myfigures/src'],
                    use=['config'])
    
    project.program(name='hello-modules',
                    source=['src'],
                    use=['config', 'myfigures'],
                    deps=['mylogger'])