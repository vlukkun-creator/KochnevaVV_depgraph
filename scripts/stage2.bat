@echo off
chcp 65001 > nul
set PYTHONUTF8=1
cd /d %~dp0..
echo ===== Stage 2 demo =====
call :run --package requests --debug
call :run --package flask
call :run --package pytest
call :run --package no-such-package-zzz-123
call :run --package requests --repo http://localhost:1
call :run --package A --repo tests\repos\simple.txt --test
call :run --package a --depth x
goto :eof

:run
echo.
echo ^>^>^> depgraph %*
py src\depgraph.py %*
echo --- exit code: %ERRORLEVEL%
goto :eof
