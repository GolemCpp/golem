[![Golem - Build System for Modern C++](docs/banner.png)](https://github.com/GolemCpp/golem/releases)

# Golem

- [What is it?](#what-is-it)
- [Getting started](#getting-started)
  - [How to install?](#how-to-install)

TODO

### What is it?

Golem is a cross-platform build system for C/C++ projects. It can build projects like CMake does, or manage dependencies like Conan does. It only requires Python and Git to work.

Golem's main goal is to remove the noise in the project file, and favor the developers intents rather than the technical details when unneeded.

``` python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

def configure(project):
    
    project.dependency(name='json',
                       repository='https://github.com/nlohmann/json.git',
                       version='^3.0.0',
                       shallow=True)

    project.library(name='mylib',
                    includes=['mylib/include'],
                    source=['mylib/src'])

    project.export(name='mylib',
                   includes=['mylib/include'])

    project.program(name='hello',
                    source=['src'],
                    use=['mylib'],
                    deps=['json'])
```

TODO: mention where to find the sample project showing this file (indicating one for windows too)

TODO: mention where to find a more elaborate sample project

## Getting started

### How to install?

**Requirements:** Python 3.10 or later, Git

Golem doesn't have a **pip** package, yet. Therefore, it needs to be cloned in your environment:

``` bash
git clone --recursive -b main https://github.com/GolemCpp/golem.git
```

To later update your cloned version of Golem:

``` bash
git pull origin/main
git submodule update --init
```

Golem's repository needs to be added to your **PATH** environment variable.

### First project

Everything starts with `golemfile.py`. Create it at the root of your project directory.

Here is an example of `golemfile.py` to compile a **Hello World** program:

``` python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

def configure(project):

    # The project variable is the entry point to declare dependencies, libraries and programs that make up the project.

    project.program(name='hello',
                    source=['src'])
    
    # 'hello' is the name of the program being compiled (e.g. hello.exe or hello-debug.exe)
    # 'src' is the directory where all source files are expected to be found (recusrively) for 'hello'
    
```

Here is `src/main.cpp`:

``` cpp
#include <iostream>
int main()
{
    std::cout << "Hello World!\n";
    return EXIT_SUCCESS;
}
```

### Commands

All the commands are meant to be called at the root of your project, where the project file (e.g. `golemfile.py` or `golem.json`) seats.

The commands are presented in the order they are expected to be called, when needed to be called.

#### golem configure

``` bash
golem configure --variant=debug
```

TODO: About Qt5/6

#### golem resolve (if using dependencies)

``` bash
golem resolve
```

TODO: About the cache system, all the environment variables, master_dependencies.json

#### golem dependencies (if using dependencies)

``` bash
golem dependencies
```

TODO

#### golem build

``` bash
golem build
```

TODO: About the -v

#### golem package

``` bash
golem package
```

TODO

#### golem clean

``` bash
golem clean
```

TODO

#### golem distclean

``` bash
golem distclean
```

TODO

## Roadmap

Here is a list of important features to add as a priority:

- Add command to initialize a project
- Add the ability for a project file to include another one
- Reverse default value for shallow on dependencies
- Generate an implicit export on a library when a program tries to use it
- Support downloadable archives instead of git repositories
- Add commands to manage the dependencies in the cache system
- Allow the recipes to be a local folder instead of a repository
- Supporting libraries mixing compiled targets and header only targets (e.g. boost)
- Add a Visual Studio solution generator (investigate waf capabilities and in slnx too)
- Add an option to choose the runtime variant (debug or release, important on Windows)
- Add the ability to remove the default flags of a variant
- Add support for cppfront
- Add support for C++ modules

Here is a list of important improvements to work on the long term:

- Add more documentation
- Add integration tests
- Add unit tests
- Add the ability to create user-defined variants
- Use the task mechanism of Waf for everything (e.g. resolving, building dependencies)

Contributions are very welcome!

Do not hesitate to create a PR with no change to start the conversation about something you'd be interested in developing. Do not hesitate to create issues to open the conversation about a problem or a need.

Of course, much remains to be done to make Golem the best build system!

## Thanks

A big thank you to:

- **mythicsoul** & **wtfblub** for their early testing, feedback, ideas, and support!

## FAQ

### Why another build system?

TODO: Explain the history behind the project

### Known issues

- `golem` alone should welcome the user with a basic recap of the useful commands
- Changing a header included by a Qt aware header (e.g. Q_OBJECT) doesn't trigger the recompilation of the associated cpp file
- The cache system accumulates the dependencies and there are no commands yet to clean it up (requires manual deletion)
- Failure on a dependency processed by `golem resolve` may put this dependency in an unrecoverable state, requiring to delete it manually from the cache
- Errors of often not user friendly (raised exceptions)
- In some specific environments, such as NixOS, the path to the compiler is not a full path (not a blocking issue, need to fixed on Waf's side)

### How is it designed?

Golem is powered by [Waf](https://waf.io/), but provides a completely different API. It's a sophisticated frontend to Waf that adds many features and simplifies for the users how to define their project.

Among the added features, Golem provides dependency management with a cache system and [recipes](https://github.com/GolemCpp/recipes).