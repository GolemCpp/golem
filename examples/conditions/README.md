# conditions

Start a [clean session](#start-a-clean-session) to run commands, if needed.

## Build instructions

To showcase conditions in the project file, we suggest to run the following:

``` bash
golem configure --variant=debug
golem build
```

Run the program:

``` bash
# On Windows
.\build\bin\hello-conditions.exe

# On UNIX/Linux
./build/bin/hello-conditions
```

The program displays a message containing the name of your platform, following the conditions defined in the project file to compile the program.

## Start a clean session

To run the commands without the Golem environment variables that you may have set on your system:

``` bash
# On Windows
clean-session

# On UNIX/Linux
./clean-session
```