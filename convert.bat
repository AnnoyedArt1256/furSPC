@echo off
if [%1]==[] goto usage
python "%~dp0convert_to_asm.py" %*
if errorlevel 1 exit /b %errorlevel%
goto :eof

:usage
@echo No arguments supplied
@echo Make sure to run this command with an input .fur file or directory
@echo example: convert.bat song.fur
@echo example: convert.bat --title "Song" --artist "Artist" song.fur
@echo example: convert.bat --output build song_dir
exit /B 1
