@echo off
rem Builds dist\DesktopCat.exe. Needs Python 3.11+ from python.org (tick "Add to PATH").
cd /d "%~dp0"
python -m venv .venv || goto :error
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul
pip install -r requirements.txt || goto :error
rem The sheet link, if there is one (it's kept out of the repo).
set "LINK="
if exist data\link.txt set "LINK=--add-data data\link.txt:."
pyinstaller --noconfirm --clean --onefile --windowed --name DesktopCat ^
  --icon assets\cat.ico ^
  --add-data "assets\Animations:Animations" ^
  --add-data "assets\cat.ico:." ^
  --add-data "data\animations.json:." ^
  --add-data "data\messages.json:." ^
  --add-data "data\reminders.json:." ^
  --add-data "data\config.json:." %LINK% ^
  run.py || goto :error
echo.
echo Built dist\DesktopCat.exe
goto :eof
:error
echo Build failed.
exit /b 1
