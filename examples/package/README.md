# hello-package

Start a [clean session](#start-a-clean-session) to run commands, if needed.

## Build instructions

Build the program:

``` bash
golem configure --variant=release --qtdir="C:\Qt\6.8.1\msvc2022_64"
golem build
```

Run the program:

``` bash
# On Windows
& { $env:PATH = "C:\Qt\6.8.1\msvc2022_64\bin;$env:PATH"; & .\build\bin\hello-package.exe }

# On UNIX/Linux
./build/bin/hello-package
```

Package the program:

``` bash
golem package
```

## Start a clean session

To run the commands without the Golem environment variables that you may have set on your system:

``` bash
# On Windows
clean-session

# On UNIX/Linux
./clean-session
```