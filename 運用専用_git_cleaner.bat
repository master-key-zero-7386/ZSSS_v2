@echo off
title Git Refresh

cd /d %~dp0

echo ===============================
echo   Git Refresh
echo ===============================

git restore --staged .
git restore .
git pull

echo.
echo Complete.
pause
