@echo off

cd /d %~dp0

python -m venv "%~dp0..\python_env\venv"

call "%~dp0..\python_env\venv\Scripts\activate"

python -m pip install --upgrade pip

python -m pip install -r requirements.txt

echo.
echo =====================================
echo Setup Complete!
echo =====================================
pause