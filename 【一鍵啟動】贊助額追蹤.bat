@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "EXE1=%~dp0【請由此執行】贊助額追蹤\贊助額追蹤.exe"
set "EXE2=%~dp0dist\贊助額追蹤\贊助額追蹤.exe"
if exist "%EXE1%" (
    start "" "%EXE1%"
    exit /b 0
)
if exist "%EXE2%" (
    start "" "%EXE2%"
    exit /b 0
)
echo.
echo [找不到程式] 尚未打包，或資料夾被移動過。
echo 請在這個專案資料夾裡，先雙擊執行「打包EXE.bat」，完成後再開「【請由此執行】贊助額追蹤」裡的 exe。
echo 詳見「使用說明.txt」。
echo.
pause
exit /b 1
