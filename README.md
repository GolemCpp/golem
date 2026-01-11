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

Here is how a **golemfile.py** looks like: 
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

But alternatively, you can also define an equivalent [golemfile.json](/examples/minimal/golemfile.json).

Have a look at the full example in [examples/minimal](/examples/minimal).

#### Other examples

TODO: List more elaborate projects here.

## 🌱 Getting started

### How to install?

**Requirements:** Python 3.10 or later, Git

Using **pipx** (recommended, creates a virtual environment):

``` bash
pipx install golemcpp

# Or install it for all users
pipx install --global golemcpp
```

Alternatively, using **pip**:

``` bash
pip install golemcpp
```

Since Golem is evolving fast, to upgrade it run:

``` bash
# When using pipx
pipx upgrade golemcpp

# When using pipx for all users
pipx upgrade --global golemcpp

# When using pip
pip install --upgrade golemcpp
```

### First project

Everything starts with `golemfile.py`. Create it at the root of your project directory.

Here is an example of `golemfile.py` to compile a **Hello World** program:

``` python
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

Have a look at the full example in [examples/hello](/examples/hello).

#### Building the project

To build the program, run:

``` bash
# For a debug build
golem configure --variant=debug

# Or, for a release build
golem configure --variant=release

# In both cases, continue with
golem build
```

The built artifacts are located in `build/bin`.

Debug artifacts are suffixed with **"-debug"** by default.

## 💻 Commands

All the commands are meant to be called at the root of your project, where the project file (e.g. `golemfile.py` or `golemfile.json`) seats.

The commands are presented in the order they are expected to be called, when needed to be called.

#### golem configure

This command allows you to configure how to build your project. The choices are saved, therefore it needs to be run only once. Modifying the project file will not require re-executing this command.

``` bash
golem configure [options]
```

<ins>Build options:</ins>

``` text
# Directory where to build the project (default: ./build)
--dir=<build_dir>

# Variants define a set of default flags/options for your build (default: debug)
--variant=(debug|release)

# Links the runtime dynamically (shared) or statically (static) (default: shared)
--runtime=(shared|static)

# Builds and links libraries dynamically (shared) or staticaly (static) (default: shared)
--link=(shared|static)

# Builds using the specfied architecture (default: <your_os_arch>)
--arch=(x64|x86)
```

<ins>IDE/support options:</ins>

``` text
# Generates files to enable Microsoft C/C++ Extension's IntelliSense in VSCode (default: False)
--vscode

# Generates files to support clangd (default: False)
--clangd

# Generates compile_commands.json files in ./build/golem/compile_commands/ (default: False)
--compile-commands
```

<ins>Qt options:</ins>

``` text
# Directory to Qt, for example C:\Qt\6.10.0\msvc2022_64 (default: None)
--qtdir=<qt_dir>
```

#### golem resolve (if using dependencies)

When defining **dependencies** in the project file, this command becomes **mandatory** after `golem configure`.

This command resolves the version of each dependency, clones them in the cache system, and configures them.

This is the only command requiring a network access, although Golem can be setup to not require any network access.

``` bash
golem resolve
```

##### About the cache system

By default, Golem stores dependencies in `~/.cache/golem`.

To control where the dependencies are being cached, define the following environment variable:

``` text
GOLEM_DEFINE_CACHE_DIRECTORIES=<path1>=<regex1>|<path2>=<regex2>|...

# <path> is a directory where the matched depencencies are stored
# <regex> is defining which dependency needs to be stored in <path> based on the repository URL
```

For example, this will store all dependencies in `F:\CACHE`:

``` text
GOLEM_DEFINE_CACHE_DIRECTORIES=F:\CACHE=^.*$
```

> One interesting use case for this feature is to be able to split the cache in different directories to separate your own dependencies from others. By separating the cache, in a CI environment it allows you to only trigger rebuilds on a specified set of dependencies.

To define a cache directory in read-only mode:

``` test
GOLEM_STATIC_CACHE_DIRECTORY=<path>
GOLEM_STATIC_CACHE_DEPENDENCIES_REGEX=<regex>

# <path> is a directory where the matched depencencies are stored
# <regex> is defining which dependency is already stored in <path> based on the repository URL
```

> This makes sure that the dependencies stored in it will stay untouched. In a CI environment, it guarantees that Golem won't mess with the static cache if an artifact is found missing, etc.

Note that a static cache doesn't need to be defined with **GOLEM_DEFINE_CACHE_DIRECTORIES** to exist. The static cache definition is defined independantly.

##### Managing dependencies

It is expected in a complex project that dependencies have some dependencies in common, and sometimes they are conflicting with each other.

The `master_dependencies.json` file solves this issue by overriding how dependencies should be resolved. It's a list of dependencies that `golem resolve` checks everytime it is encountering a dependency definition to replace it with the one found (if any) in the `master_dependencies.json`.

> The most common use case is to force a specific version on a dependency accross a whole project.

Here is how a `master_dependencies.json` looks like:

``` json
[
    {
        "repository": "https://github.com/nlohmann/json.git",
        "version": "^3.0.0",
        "variant": "release",
        "shallow": true
    }
]
```

This overrides any reference to this dependency with the version `^3.0.0` and the release variant.

The `master_dependencies.json` can be specified in multiple ways. By order of precedence:

``` text
# Call golem configure with an option pointing to the file 
--master-dependencies-configuration=<path_to_file>

# Define in the project file where to find the file
project.master_dependencies_configuration = '<path_to_file>'

# Define an environment variable pointing to the file
GOLEM_MASTER_DEPENDENCIES_CONFIGURATION=<path_to_file>

# Define in the project file the repository where to find the file
project.master_dependencies_repository = '<repository_url>'

# Define an environment variable pointing to a repository containing: master_dependencies.json
GOLEM_MASTER_DEPENDENCIES_REPOSITORY=<repository_url>
```

> Although useful to quickly try a `master_dependencies.json`, it is not recommended to define it in the project file itself for most projects.

#### Managing recipes

Golem aware dependencies, those having Golem project file defined at their root, can seemlessly refer to each other. But, when refering to a dependency unaware of Golem, Golem provides a recipe mechanism.

By default, Golem provides a [recipe repository](https://github.com/GolemCpp/recipes) to find a corresponding project file for these dependencies unaware of Golem.

Dependencies are uniquely identified by their repository URL. Their ID is constructed such as "https://github.com/nlohmann/json.git" becomes "json@com.github.nlohmann".

A recipe repository contains directories named after these dependency IDs, and each directory contains a project file.

This is how it looks like:

``` text
.
├── boost@com.github.boostorg/
│   └── golemfile.py
├── json@com.github.nlohmann/
│   └── golemfile.py
├── spdlog@com.github.gabime/
│   └── golemfile.py
└── <etc>
    └── golemfile.py
``` 

> For now, there is no project file per version mechanism, but this is in the Roadmap.

A `golemfile.py` can use scripting to handle any build system, any situation.

To override the default Golem recipe repository, and possibly have multiple sources for recipes:

``` text
# Define an environment variable pointing to the repositories
GOLEM_RECIPES_REPOSITORIES=<repository_url_1>|<reposiroty_url_2>|...
```

> For now, there is no possibility to define a directory instead of a repository, but this is in the Roadmap.

> When a dependency is missing, or not building properly, it is recommended to fork the Golem [recipe repository](https://github.com/GolemCpp/recipes), make the needed changes and create a Pull Request. Contributions are very welcome!

#### golem dependencies (if using dependencies)

When defining **dependencies** in the project file, this command becomes **mandatory** after `golem resolve`, and expects it to have run successfully.

This command builds the dependencies needed to build the project.

``` bash
golem dependencies
```

#### golem build

This command builds the libraries and programs defined in the project file (e.g. `golemfile.py` or `golemfile.json`).

If any dependency is needed, the artifacts are expected to be built using `golem resolve` and `golem dependencies` before hand.

``` bash
# Build all the targets
golem build

# Build and show the compile commands
golem build -v

# Build specific targets
golem build --targets=foo,bar
```

#### golem package

This command generates the packages defined in the project file.

``` bash
golem package
```

For now, Golem can generate:
- MSI files for Windows with WiX
- DMG files for MacOS
- DEB files for Debian-based distributions

Golem also provides a hook mechanism for scripting purposes after a package is generated.

#### golem clean

This command cleans up the objects built with `golem build`.

``` bash
golem clean
```

#### golem distclean

This command deletes the build directory.

``` bash
golem distclean
```

## 🚀 Roadmap

Here is a list of important features to add as a priority:

- Add command to initialize a project
- Add command to initialize a recipe (takes a URL and an option for the build system, include comments in project file)
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