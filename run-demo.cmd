@echo off
chcp 65001 >nul
cd /d "%~dp0"
node dist\moontxnwitness.mjs check examples\write-skew.json
echo.
echo This synthetic example is expected to report a violation (exit code 1).
pause
