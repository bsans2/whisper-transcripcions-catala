@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo  Creant Whisper.exe - pot trigar entre 5 i 15 minuts
echo ============================================================
echo.

if not exist ".venv\Scripts\python.exe" (
  echo No s'ha trobat l'entorn virtual .venv en aquesta carpeta.
  echo Copia aquest fitxer a C:\WhisperClasses i torna-ho a provar.
  goto :error
)
if not exist "whisper_gui.py" (
  echo No s'ha trobat whisper_gui.py en aquesta carpeta.
  goto :error
)
if not exist "icona_whisper.ico" (
  echo No s'ha trobat icona_whisper.ico en aquesta carpeta.
  goto :error
)

echo [1/3] Instal.lant PyInstaller dins de l'entorn virtual...
".venv\Scripts\python.exe" -m pip install --upgrade pyinstaller
if errorlevel 1 goto :error

echo.
echo [2/3] Generant el programa...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onedir --windowed ^
  --name Whisper ^
  --icon icona_whisper.ico ^
  --add-data "icona_whisper.ico;." ^
  --collect-all whisper ^
  --hidden-import tiktoken_ext ^
  --hidden-import tiktoken_ext.openai_public ^
  whisper_gui.py
if errorlevel 1 goto :error

echo.
echo [3/3] Afegint ffmpeg al programa...
set "FFMPEG="
for /f "delims=" %%i in ('where ffmpeg 2^>nul') do if not defined FFMPEG set "FFMPEG=%%i"
if defined FFMPEG (
  copy /y "%FFMPEG%" "dist\Whisper\ffmpeg.exe" >nul
  echo ffmpeg.exe copiat dins de dist\Whisper
) else (
  echo AVIS: no s'ha trobat ffmpeg. Copia ffmpeg.exe manualment dins de dist\Whisper
)

echo.
echo ============================================================
echo  FET. El programa es a la carpeta:  dist\Whisper
echo  Obre dist\Whisper\Whisper.exe per provar-lo.
echo ============================================================
pause
exit /b 0

:error
echo.
echo ERROR: no s'ha pogut crear l'executable.
echo Fes una captura del missatge d'error que hi ha mes amunt.
pause
exit /b 1
