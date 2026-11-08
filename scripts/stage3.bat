@echo off
chcp 65001 > nul
set PYTHONUTF8=1
cd /d %~dp0..
echo ===== Stage 3 demo =====
call :run --package A --repo tests\repos\simple.txt --test
call :run --package A --repo tests\repos\chain.txt --test
call :run --package A --repo tests\repos\cycle.txt --test
call :run --package A --repo tests\repos\self_cycle.txt --test
call :run --package A --repo tests\repos\no_deps.txt --test
call :run --package A --repo tests\repos\chain.txt --test --depth 2
call :run --package A --repo tests\repos\big.txt --test --depth 1
call :run --package A --repo tests\repos\big.txt --test --filter G
call :run --package A --repo tests\repos\big.txt --test --filter H --depth 5
call :run --package A --repo tests\repos\big.txt --test --depth 10
call :run --package Z --repo tests\repos\simple.txt --test
call :run --package A --repo tests\repos\bad_no_colon.txt --test
call :run --package A --repo tests\repos\bad_name.txt --test
call :run --package A --repo tests\repos\bad_duplicate.txt --test
call :run --package requests --depth 2
goto :eof

:run
echo.
echo ^>^>^> depgraph %*
py src\depgraph.py %*
echo --- exit code: %ERRORLEVEL%
goto :eof
