@echo off
chcp 65001 >nul
REM 與「安裝瀏覽器登入環境.bat」相同：下載 Playwright 用 Chromium（瀏覽器登入／相關功能需要）
call "%~dp0安裝瀏覽器登入環境.bat"
exit /b %ERRORLEVEL%
