#!/usr/bin/env bash
# Convert one .fur file, several .fur files, or a directory of .fur files.
set -e

if [ "$#" -eq 0 ]; then
    echo "No arguments supplied"
    echo "Make sure to run this command with an input .fur file or directory"
    echo "example: convert.sh song.fur"
    echo "example: convert.sh --title \"Song\" --artist \"Artist\" song.fur"
    echo "example: convert.sh --output build song_dir"
    exit 1
fi

exec python3 "$(dirname "$0")/convert_to_asm.py" "$@"
