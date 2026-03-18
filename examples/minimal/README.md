# minimal

Start a [clean session](#start-a-clean-session) to run commands, if needed.

## Build instructions

Build the program:

``` bash
golem configure --variant=debug
golem resolve
golem dependencies
golem build
```

This builds both the library `mylib` and the program using it.

Run the program:

``` bash
# On Windows
.\build\bin\hello-minimal.exe

# On UNIX/Linux
./build/bin/hello-minimal
```

## Start a clean session

To run the commands without the Golem environment variables that you may have set on your system:

``` bash
# On Windows
clean-session

# On UNIX/Linux
./clean-session
```