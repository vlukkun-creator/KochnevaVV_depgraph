@echo off
chcp 65001 > nul
set PYTHONUTF8=1
set PYTHONPATH=src
py -m unittest discover -s tests -v
