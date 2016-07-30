@echo off
setlocal

set first=%1

shift
set rest=%1

:loop
	shift
	if [%1]==[] goto afterloop
	set rest=%rest% %1
	goto loop

:afterloop

if not exist "%first%" echo Script "%first%" not found & exit 2

set _CYGBIN=C:\cygwin\bin
if not exist "%_CYGBIN%" echo Couldn't find Cygwin at "%_CYGBIN%" & exit 3

:: Resolve ___.sh to /cygdrive based *nix path and store in %_CYGSCRIPT%
for /f "delims=" %%A in ('%_CYGBIN%\cygpath.exe "%first%"') do set _CYGSCRIPT=%%A
for /f "delims=" %%A in ('%_CYGBIN%\cygpath.exe "%CD%"') do set _CYGPATH=%%A

:: Throw away temporary env vars and invoke script, passing any args that were passed to us
:: endlocal & %_CYGBIN%\bash --login "%_CYGSCRIPT%" %rest%
endlocal & echo cd %_CYGPATH%; "%_CYGSCRIPT%" %rest% | %_CYGBIN%\bash --login -s