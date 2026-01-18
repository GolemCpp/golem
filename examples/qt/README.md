# qt

## Build instructions

``` batch
golem configure --variant=debug --qtdir="C:\Qt\6.8.1\msvc2022_64"
golem build
```

On Windows:

``` batch
& { $env:PATH = "C:\Qt\6.8.1\msvc2022_64\bin;$env:PATH"; & .\build\bin\hello-qt-debug.exe }
```