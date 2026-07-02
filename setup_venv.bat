@echo off

cd /d %~dp0

python -m venv C:\python_env\venv

call C:\python_env\venv\Scripts\activate

python -m pip install --upgrade pip

python -m pip install -r requirements.txt

echo.
echo =====================================
echo Setup Complete!
echo =====================================
pause