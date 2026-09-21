@echo off
rem Double-click this file to start Teleloadzai.
rem Temporary launcher: at step 6 this becomes a real Teleloadzai.exe.

cd /d "%~dp0"
title Teleloadzai

python -m teleloadzai

if errorlevel 1 (
  echo.
  echo ---------------------------------------------
  echo  Teleloadzai stopped with an error.
  echo  Read the message above, then close this window.
  echo ---------------------------------------------
  pause
)
