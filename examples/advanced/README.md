# advanced

Start a [clean session](#start-a-clean-session) to run commands, if needed.

## Customize and force options on dependencies

To showcase how to customize or force options on dependencies, we suggest to run the following:

``` bash
golem configure --variant=release
golem resolve
golem dependencies
golem build
```

The project file defines a dependency, forces it to the `release` variant, and sets a message `'Hello'` through a macro on it. The program linked to this dependency calls the dependency to print the options it was built with.

``` bash
.\build\bin\hello-advanced.exe

# On UNIX/Linux
./build/bin/hello-advanced
```

The expected output is:

``` text
Variant is: Release
Message is: Hello
```

## Start a clean session

To run the commands without the Golem environment variables that you may have set on your system:

``` bash
# On Windows
clean-session

# On UNIX/Linux
./clean-session
```