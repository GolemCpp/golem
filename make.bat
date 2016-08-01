@echo off

@setlocal
set DIR=%~dp0

python -B %DIR%golem %*
@endlocal