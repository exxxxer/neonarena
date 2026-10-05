@echo off
setlocal
cd /d "%~dp0"
py -3 -m venv .venv
if errorlevel 1 goto failed
call .venv\Scripts\activate.bat
python -m pip install -r requirements.txt
if errorlevel 1 goto failed
python -m unittest discover -s tests -v
if errorlevel 1 goto failed
python -m PyInstaller --noconfirm --clean NeonArena.spec
if errorlevel 1 goto failed
echo Ready: dist\NeonArena\NeonArena.exe
echo Keep the entire dist\NeonArena folder, including _internal.
pause
exit /b 0
:failed
echo Build failed. Read the error above.
pause
exit /b 1
