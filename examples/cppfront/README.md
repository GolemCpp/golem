# cppfront

Start a [clean session](#start-a-clean-session) to run commands, if needed.

## Build instructions

Build the program:

``` bash
golem configure --variant=debug --cppfront-path=/path/to/cppfront --cppfront-include=/path/to/cppfront/source
golem build
```

Run the program:

``` bash
# On Windows
.\build\bin\hello-cppfront.exe

# On UNIX/Linux
./build/bin/hello-cppfront
```

## Start a clean session

To run the commands without the Golem environment variables that you may have set on your system:

``` bash
# On Windows
clean-session

# On UNIX/Linux
./clean-session
```