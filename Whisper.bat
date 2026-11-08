@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo No s'ha trobat l'entorn virtual .venv en aquesta carpeta.
  echo Copia whisper_gui.py i Whisper.bat dins de C:\WhisperClasses i torna-ho a provar.
  pause
  exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" "whisper_gui.py"
