#!/bin/bash
if [ $# -eq 0 ]
then
    echo "No arguments supplied"
    echo "Make sure to run this command with an argument"
    echo "example: convert.sh test_file.fur"
else
python3 convert_to_asm.py "$1"
echo "converted .fur file to .asm!"
rm -r ./obj
mkdir -p ./obj/snes
make clean
make
echo "compiled .spc file at furSPC-test.spc"
fi
