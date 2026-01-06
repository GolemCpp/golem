<a href="https://github.com/GolemCpp/golem/releases">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/banner-dark.png">
    <source media="(prefers-color-scheme: light)" srcset="docs/banner-light.png">
    <img alt="Golem - Build System for Modern C++" src="docs/banner-light.png">
  </picture>
</a>

## Golem

- [Golem](#golem)
  - [What is it?](#what-is-it)
- [🌱 Getting started](#🌱-getting-started)
  - [How to install?](#how-to-install)
  - [First project](#first-project)
- [💻 Commands](#💻-commands)
  - [golem configure](#golem-configure)
  - [golem resolve (if using dependencies)](#golem-resolve-if-using-dependencies)
  - [golem dependencies (if using dependencies)](#golem-dependencies-if-using-dependencies)
  - [golem build](#golem-build)
  - [golem package](#golem-package)
  - [golem clean](#golem-clean)
  - [golem distclean](#golem-distclean)
- [🚀 Roadmap](#🚀-roadmap)
- [💖 Thanks](#💖-thanks)
- [❓ FAQ](#❓-faq)
  - [Why another build system?](#why-another-build-system)
  - [Known issues](#known-issues)
  - [How is it designed?](#how-is-it-designed)

### What is it?

Golem is a cross-platform build system for C/C++ projects. It can build projects like CMake does, or manage dependencies like Conan does. It only requires Python and Git to work.

Golem's main goal is to remove the noise in the project file, and favor the developers intents rather than the technical details when unneeded.

``` python
def configure(project):
    
    project.dependency(name='json',
                       repository='https://github.com/nlohmann/json.git',
                       version='^3.0.0',
                       shallow=True)

    project.library(name='mylib',
                    includes=['mylib/include'],
                    source=['mylib/src'],
                    defines=['FOO_API_EXPORT'])

    project.export(name='mylib',
                   includes=['mylib/include'],
                   defines=['FOO_API_IMPORT'])

    project.program(name='hello',
                    source=['src'],
                    use=['mylib'],
                    deps=['json'])
```

TODO: mention where to find the sample project showing this file (indicating one for windows too)
TODO: always mention golemfile.py and an equivalent golemfile.json
TODO: mention where to find a more elaborate sample project

## 🌱 Getting started

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

Golem's repository needs to be added to your **PATH** environment variable. And in a Python environment, install the only needed dependency:

``` bash
pip install node-semver==0.8.0
```

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

## 💻 Commands

All the commands are meant to be called at the root of your project, where the project file (e.g. `golemfile.py` or `golem.json`) seats.

The commands are presented in the order they are expected to be called, when needed to be called.

#### golem configure

``` bash
golem configure --variant=debug
```

TODO: About Qt5/6
TODO: Editor arguments (--vscode --clangd)

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

## 🚀 Roadmap

Here is a list of important features to add as a priority:

- Add command to initialize a project
- Add the ability for a project file to include another one
- Set default value for shallow on dependencies to True, or 'auto' (when version is a tag then shallow=True, otherwise for branches and commit hashes shallow=false) (this new behavior requires to check how version_template will behave, and it requires to fix how golem projects generate artifacts with the asked version to no break dependencies)
- Generate an implicit export on a library when a program tries to use it
- Support downloadable archives instead of git repositories
- Add commands to manage the dependencies in the cache system
- Allow the recipes to be a local folder instead of a repository
- Supporting libraries mixing compiled targets and header only targets (e.g. boost)
- Add a Visual Studio solution generator (investigate waf capabilities and in slnx too)
- Add an option to choose the runtime variant (debug or release, important on Windows)
- Add the ability to remove the default flags of a variant
- Add the ability to have different recipes for different versions of the dependency
- Make an empty version on a dependency default to the latest available version
- Create a pip package
- Consider packaging Golem for Windows, Linux, MacOS (see https://pyinstaller.org/en/stable/)
- Add `c_standard`/`cxx_standard` on the Configuration (library, program, dependency)
- Rename `golem.json` to `golemfile.json` for symmetry with `golemfile.py`
- Remove v prefix from versions (see `Version.py`)
- Detect automatically Qt if in `C:\Qt` or other obvious paths on other platforms
- Return a sensible error message to the user when running golem commands in the wrong order
- Generate API header and associated defines for libraries when `auto_api_name='MYLIB_API'` is defined (can possibly switch later to a systematic generation with a switch to disable the generation)
- Add or improve recipes for the most popular dependencies (increase support for configuration options)
- Add support for cppfront
- Add support for C++ modules

Here is a list of important improvements to work on the long term:

- Add more documentation
- Add integration tests
- Add unit tests
- Add the ability to create user-defined variants
- Use the task mechanism of Waf for everything (e.g. resolving, building dependencies)
- Improve available helper functions to build dependencies using other build systems (recipes)
- Define default security profiles (allow creation and customization, `security_profile='all'`)

Here is a list of other nice improvements to work on:

- Properly log messages instead of using print() (needs anlaysis, consider using waflibs.Logs)
- Properly abort execution when encoutering an error instead of raising an exception (needs anlaysis, consider using config.fatal(''), raise Waf.Error(), etc.)
- Show the full path of the compiler when in a NixOS shell (issue on Waf's side)
- Detect when `/external:I` or `-isystem` are available before using them
- Merge `use` and `deps` with a properly defined convention to differentiate the dependencies (e.g. @json, needs analysis)
- Generate by default `qmldir` and a `qrc` file for all the found QML files (allow to customize the namespace, or to disable generation)

Contributions are very welcome!

Do not hesitate to create a PR with no change to start the conversation about something you'd be interested in developing. Do not hesitate to create issues to open the conversation about a problem or a need.

Of course, much remains to be done to make Golem the best build system!

## 💖 Thanks

A big thank you to:

- **mythicsoul** & **wtfblub** for their early testing, feedback, ideas, and support!

## ❓ FAQ

### Why another build system?

It all started back in 2016, with accumulated frustrations about the absence of proper dependency management in the tools of that time. In July 2016, Conan was not even a thing. CMake wasn't as widely adopted, but was definitely ramping up to become the success it is. At the time, I already went through a lot of thinking about how to solve the needs I had with previous scripting attempts, and being tired of it; I decided to start a proper tool on top of Waf to do it. Golem was born.

Years have passed, Golem ended up serving me better than I anticipated in the first place. I witnessed the rise of Conan and CMake, and I thought that Golem had something they didn't have. Time passed again, and I finally found the time to focus on sharing it properly, publishing it (Dec 27, 2025), documenting it and work on what's missing for it to not just be my tool, but a tool for everyone.

C++ has progressed a lot in the meantime; safety concerns, C++ modules, etc. Since the beginning, Golem's spirit is to be helpful and aware of how C++ projects are made today. It is made to be simple to use. Golem's goals are to provide premium support for both the bleeding edge features C++ can offer and the best safety and programming practices. This is how Golem's development will continue.

After the neccessary improvements, I'll advertise Golem to a broader audience.

### Known issues

- `golem` alone should welcome the user with a basic recap of the useful commands
- The cache system accumulates the dependencies and there are no commands yet to clean it up (requires manual deletion)
- Failure on a dependency processed by `golem resolve` may put this dependency in an unrecoverable state, requiring to delete it manually from the cache
- Errors of often not user friendly (raised exceptions)
- In some specific environments, such as NixOS, the path to the compiler is not a full path (not a blocking issue, need to fixed on Waf's side)
- When dealing with conflicting variants of a same dependency, there is no message to warn the user, and Golem attemps to link both anyway (master_dependencies.json is a good workaround for most cases)
- Only 1 template among those having the same source will get processed (bug caused by `if str(version_template_src) in self.context_tasks: continue`)
- No support for specifying header files in include parameter to export a library (needs to be a directory for now)

Additionnally to this non-exhaustive list, there are edge cases where the behavior isn't properly defined yet.

### How is it designed?

Golem is powered by [Waf](https://waf.io/), but provides a completely different API. It's a sophisticated frontend to Waf that adds many features and simplifies for the users how to define their project.

Among the added features, Golem provides dependency management with a cache system and [recipes](https://github.com/GolemCpp/recipes).