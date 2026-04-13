@echo off
cd /d %~dp0
call venv\Scripts\activate.bat
start /min python binah.py
exit