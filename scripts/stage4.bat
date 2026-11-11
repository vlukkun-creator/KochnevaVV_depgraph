@echo off
chcp 65001 > nul
set PYTHONUTF8=1
cd /d %~dp0..
echo ===== Stage 4 demo =====
call :run --package D --repo tests\repos\simple.txt --test --reverse
call :run --package D --repo tests\repos\simple.txt --test --reverse --depth 1
call :run --package A --repo tests\repos\simple.txt --test --reverse
call :run --package A --repo tests\repos\cycle.txt --test --reverse
call :run --package I --repo tests\repos\big.txt --test --reverse --depth 10
call :run --package H --repo tests\repos\big.txt --test --reverse --filter F
call :run --package Z --repo tests\repos\big.txt --test --reverse
call :run --package requests --reverse
call :run --package A --repo tests\repos\big.txt --test --depth 3
goto :eof

:run
echo.
echo ^>^>^> depgraph %*
py src\depgraph.py %*
echo --- exit code: %ERRORLEVEL%
goto :eof
