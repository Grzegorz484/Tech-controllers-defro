@echo off
chcp 65001 >nul
cd /d "%~dp0"
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,8) else 1)" >nul 2>nul
if not errorlevel 1 goto python_launcher
python -c "import sys; sys.exit(0 if sys.version_info >= (3,8) else 1)" >nul 2>nul
if not errorlevel 1 goto python_direct
echo Nie znaleziono Pythona. Mozesz wgrac folder custom_components recznie wedlug INSTALACJA.txt.
goto koniec
:python_launcher
py -3 "%~dp0install.py"
goto koniec
:python_direct
python "%~dp0install.py"
:koniec
echo.
pause

