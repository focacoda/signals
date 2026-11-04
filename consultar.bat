@echo off
chcp 65001 >nul
title DevHub Signals - Consultas
cd /d "%~dp0"
echo.
echo ============ RELATORIO DE ANALISE ============
python -m tools.relatorio
pause
