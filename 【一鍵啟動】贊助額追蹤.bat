@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "EXE1=%~dp0【請由此執行】贊助額追蹤\贊助額追蹤.exe"
set "EXE2=%~dp0dist\贊助額追蹤\贊助額追蹤.exe"
set "PYW=%~dp0贊助額追蹤.pyw"
set "RUNGUI=%~dp0run_gui.py"

if exist "%EXE1%" (
    start "" "%EXE1%"
    exit /b 0
)
if exist "%EXE2%" (
    start "" "%EXE2%"
    exit /b 0
)

REM 尚未打包時：改以原始碼啟動（需已安裝 Python 並安裝依賴，見 requirements.txt）
where pythonw >nul 2>&1
if not errorlevel 1 (
    if exist "%PYW%" (
        start "" pythonw "%PYW%"
        exit /b 0
    )
)
where python >nul 2>&1
if not errorlevel 1 (
    if exist "%RUNGUI%" (
        start "" python "%RUNGUI%"
        exit /b 0
    )
)
where py >nul 2>&1
if not errorlevel 1 (
    if exist "%RUNGUI%" (
        start "" py -3 "%RUNGUI%"
        exit /b 0
    )
)

echo.
echo [找不到可執行檔]
echo   尚未建置 exe，且無法以 Python 啟動原始碼。
echo.
echo 請擇一處理：
echo   1）雙擊「【一鍵打包】EXE.bat」建置後，會出現「【請由此執行】贊助額追蹤」資料夾，再執行本捷徑即可。
echo   2）或安裝 Python 3.11+ 後在此資料夾開啟命令列執行：
echo        pip install -r requirements.txt
echo      再執行本捷徑（會改開 贊助額追蹤.pyw）。
echo.
echo 詳見「使用說明.txt」。
echo.
pause
exit /b 1
