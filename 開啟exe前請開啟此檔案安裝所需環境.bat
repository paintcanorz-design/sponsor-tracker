@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "EXE=%~dp0贊助額追蹤.exe"
if not exist "%EXE%" (
    echo [錯誤] 找不到贊助額追蹤.exe。請整包解壓，勿只複製此腳本。
    pause
    exit /b 1
)
echo.
echo 即將下載 Playwright 用 Chromium（設定內瀏覽器登入需要），約數百 MB，需網路。
echo 若不需要瀏覽器登入可略過，改用手動貼 Cookie。
echo.
pause
"%EXE%" --install-playwright-browsers
set "RC=%ERRORLEVEL%"
echo.
if %RC% neq 0 (
    echo 安裝未成功。可改用手動貼 Cookie 等方式登入。
) else (
    echo 完成。接下來可雙擊贊助額追蹤.exe；瀏覽器登入請到設定操作。
)
echo.
pause
exit /b %RC%
