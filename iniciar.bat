@echo off
chcp 65001 >nul
title DevHub Signals
cd /d "%~dp0"
echo ================================================
echo   DevHub Signals
echo   Abra no navegador:  http://127.0.0.1:8000
echo   Documentacao API:   http://127.0.0.1:8000/docs
echo ================================================
echo.
echo Feche esta janela para parar o servidor.
echo.
python run.py
pause
