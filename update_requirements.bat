@echo off

cd /d %~dp0

call "%~dp0..\python_env\venv\Scripts\activate"

python -m pip freeze > requirements.txt

echo.
echo =====================================
echo requirements.txt updated.
echo =====================================
pause