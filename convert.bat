@echo off
if [%1]==[] goto usage
python3 convert_to_asm.py %1
echo converted .fur file to .s!
make clean
make
@echo compiled .spc file at furSPC-test.spc
goto :eof
:usage
@echo No arguments supplied
@echo Make sure to run this command with an argument
@echo example: convert.bat test_file.fur
exit /B 1
