@echo off
chcp 65001 >nul
cd /d "%~dp0"
node dist\demo.mjs
echo.
echo Open report.md in the newly created moontxnwitness-demo directory.
pause
