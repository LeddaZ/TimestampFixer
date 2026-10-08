@echo off
rem Rebuild dist\TimestampFixer.exe from source.
"%~dp0.venv\Scripts\python.exe" -m PyInstaller --noconfirm "%~dp0TimestampFixer.spec"
