@echo off
if [%1]==[] goto usage
python3 convert_to_asm.py %1
echo converted .fur file to .s!
rmdir /s /q obj
md obj\snes
ca65 -g src\spcheader.s -o obj\snes\spcheader.o
ca65 -g src\spcimage.s -o obj\snes\spcimage.o
ld65 -o furSPC-test.spc -m spcmap.txt -C spc.cfg obj\snes\spcheader.o obj\snes\spcimage.o
@echo compiled .spc file at furSPC-test.spc
goto :eof
:usage
@echo No arguments supplied
@echo Make sure to run this command with an argument
@echo example: convert.bat test_file.fur
exit /B 1
