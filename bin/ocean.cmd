@echo off
setlocal
set "SCRIPT_DIR=%~dp0.."
set "PYTHON_EXE=python"
where %PYTHON_EXE% >nul 2>nul
if %ERRORLEVEL% neq 0 (
    set "PYTHON_EXE=py -3"
)
%PYTHON_EXE% "%SCRIPT_DIR%\ocean.py" %*
