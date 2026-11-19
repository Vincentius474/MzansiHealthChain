@echo off
REM Lets you type "run test" instead of ".\run.ps1 test" and skips the PowerShell script-policy prompt.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1" %*
