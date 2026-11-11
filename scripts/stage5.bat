@echo off
chcp 65001 > nul
set PYTHONUTF8=1
cd /d %~dp0..
echo ===== Stage 5 demo =====
call :run --package A --repo tests\repos\simple.txt --test
call :run --package A --repo tests\repos\big.txt --test --ascii --depth 3
call :run --package A --repo tests\repos\cycle.txt --test --ascii
call :run --package A --repo tests\repos\self_cycle.txt --test --ascii
call :run --package A --repo tests\repos\big.txt --test --ascii --filter G --depth 4
call :run --package D --repo tests\repos\simple.txt --test --reverse
call :run --package requests --ascii --depth 2
call :run --package flask --ascii --depth 2
call :run --package pytest --ascii --depth 2
goto :eof

:run
echo.
echo ^>^>^> depgraph %*
py src\depgraph.py %*
echo --- exit code: %ERRORLEVEL%
goto :eof
