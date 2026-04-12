@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>&1
if errorlevel 1 (
    echo [錯誤] 找不到 Python。請安裝 Python 3.11+ 並勾選「Add python.exe to PATH」。
    echo 下載：https://www.python.org/downloads/
    pause
    exit /b 1
)
echo [1/5] 更新 pip 並安裝依賴（缺少時會自動下載）...
python -m pip install -q --upgrade pip
python -m pip install -q -r requirements.txt -r requirements-build.txt
if errorlevel 1 (
    echo [錯誤] pip 安裝失敗。
    pause
    exit /b 1
)
echo [2/5] Playwright Chromium（本機快取，供開發測試；不打包進發行檔以縮小體積）...
python -m playwright install chromium
if errorlevel 1 (
    echo [警告] Playwright 瀏覽器下載失敗，打包仍繼續；瀏覽器登入可能需已安裝 Chromium 的環境。
)
echo [3/5] PyInstaller 建置免安裝資料夾（dist\贊助額追蹤\）...
python -m PyInstaller --clean --noconfirm sponsor_tracker.spec
if errorlevel 1 (
    echo [錯誤] 建置失敗。
    pause
    exit /b 1
)
echo [4/5] 同步到專案根目錄的醒目資料夾（不必再進 dist 找路徑）...
set "REL_OUT=【請由此執行】贊助額追蹤"
set "ABS_OUT=%~dp0%REL_OUT%"
set "ABS_SRC=%~dp0dist\贊助額追蹤"
if not exist "%ABS_SRC%\贊助額追蹤.exe" (
    echo [錯誤] 找不到建置輸出：%ABS_SRC%\贊助額追蹤.exe
    pause
    exit /b 1
)
robocopy "%ABS_SRC%" "%ABS_OUT%" /MIR /NFL /NDL /NJH /NJS /NP >nul
set "RC=%ERRORLEVEL%"
if %RC% GEQ 8 (
    echo [錯誤] 複製到「%REL_OUT%」失敗（robocopy 代碼 %RC%）。
    pause
    exit /b 1
)
copy /Y "%~dp0使用說明.txt" "%ABS_OUT%\使用說明.txt" >nul 2>&1
echo [5/5] 產生 GitHub 發佈用 zip（release 資料夾，供上傳 Release 附件）...
python "%~dp0pack_release_zip.py"
if errorlevel 1 (
    echo [警告] 壓縮失敗，請手動將「%REL_OUT%」資料夾壓成 zip 再上傳。
) else (
    echo        檔案位於：release\  （檔名含版本號）
)
echo.
echo [完成] 主程式位置（最顯眼）：
echo        %REL_OUT%\贊助額追蹤.exe
echo.
echo 之後使用可雙擊：【一鍵啟動】贊助額追蹤.bat
echo 詳細說明請開：使用說明.txt
echo 發給別人時請整包複製「%REL_OUT%」資料夾（含 _internal），勿只複製 exe。
echo GitHub Release 請上傳 release 內的 zip（程式「一鍵更新」會下載此檔）。
echo.
start "" explorer "%ABS_OUT%"
pause
