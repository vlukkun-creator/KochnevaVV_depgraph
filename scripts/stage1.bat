@echo off
chcp 65001 > nul
set PYTHONUTF8=1
cd /d %~dp0..
echo ===== Stage 1 demo =====
call :run --package requests
call :run --package requests --repo tests\repos\simple.txt --test --ascii --depth 5 --filter X
call :run 
call :run --package bad!name
call :run --package A --repo ftp://x
call :run --package A --repo nofile.txt --test
call :run --package A --repo src --test
call :run --package A --depth abc
call :run --package A --depth 0
call :run --package A --depth 100
call :run --package abc --filter b
call :run --package abc --filter ""
call :run --bad
goto :eof

:run
echo.
echo ^>^>^> depgraph %*
py src\depgraph.py %*
echo --- exit code: %ERRORLEVEL%
goto :eof
