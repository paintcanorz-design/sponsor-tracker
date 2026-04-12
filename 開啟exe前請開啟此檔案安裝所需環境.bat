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

echo [提示] 即將下載 Playwright 用 Chromium（設定內瀏覽器登入需要），約數百 MB，需網路。

echo [提示] 若不需要可略過本步驟，改用手動貼 Cookie。

echo.

"%EXE%" --install-playwright-browsers

set "RC=%ERRORLEVEL%"

echo.

if not "%RC%"=="0" goto INSTALL_FAIL

echo ----------------------------

echo [成功] 瀏覽器環境已就緒。

echo        即將開啟「贊助額追蹤」主程式…

echo ----------------------------

timeout /t 2 /nobreak >nul

start "" "%EXE%"

exit /b 0



:INSTALL_FAIL

echo ----------------------------

echo [失敗] 瀏覽器環境安裝未完成。

echo        結束碼: %RC%

echo        可改用手動貼 Cookie，或檢查網路／防火牆後再執行本腳本。

echo ----------------------------

timeout /t 8 /nobreak

exit /b %RC%

