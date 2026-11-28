# furSPC
an SNES sound driver for Furnace

### **THIS SOUND DRIVER IS CURRENTLY A WIP**
### **IF THERE ARE ANY BUGS IN THE DRIVER PLEASE LET ME KNOW!!!**

FINALLY, an SNES driver that is not total dogwater to use!

* You have to have [Python](https://www.python.org/) and the [CC65 toolchain](https://cc65.github.io/) installed
* Both pitch linearity modes are supported: "None" uses frequency-based pitch slides, "Full" uses semitone-based (1/128 semitone) pitch slides. Legacy "Partial" treated as "Full".
* Unused features are omitted from the generated driver: panning code is only included when a pan effect or pan macro is used, and echo setup/toggle code is only included when a channel is routed to echo.

* The driver only supports **volume, arpeggio, waveform, panning (left/right), noise freq and special** macros in each instrument and it DOESN'T support LFO and ADSR macros nor delay and step length

* MAKE SURE TO CONVERT ALL SAMPLES IN THE MODULE TO **BRR SAMPLES** BEFORE USING THE CONVERTER TOOL
 
* The furSPC driver only supports these effects:
  * 00xx: arpeggio
  * 01xx: pitch slide up
  * 02xx: pitch slide down
  * 03xx: portamento
  * 04xx: vibrato
  * 08xx: set panning
  * 80xx: set panning (linear)
  * 81xx: set panning left
  * 82xx: set panning right
  * 09xx: set speed 1
  * 0Axx: volume slide
  * 0Bxx: jump to pattern
  * 0Dxx: jump to next pattern
  * 0Fxx: set speed 2
  * 10xx: set waveform
  * 11xx: toggle noise mode
  * 12xx: toggle echo on channel
  * 13xx: toggle pitch modulation
  * 1Dxx: set noise freq
  * 20xx: set attack (0 to F)
  * 21xx: set decay (0 to 7)
  * 22xx: set sustain (0 to 7)
  * 23xx: set release (00 to 1F)
  * E1xx: note slide up
  * E2xx: note slide down
  * E5xx: note fine-pitch
  * EAxx: legato
  * ECxx: note cut

when you've finished / want to test out this driver:
* open the terminal/command prompt **to the furSPC directory**
* run `convert.sh your_fur_file.fur` or `convert.bat file.fur` (depending on your OS)

By default, the output is written next to the input with the same name and a `.spc` extension. The output file and ID666 tags can be specified on the command line (or otherwise they will be derived from the .fur):
  * `convert.sh song.fur -o build/song.spc`
  * `convert.sh song.fur --title "Song Title" --album "Album" --artist "Artist" --time 2:38`
  * `--time` accepts seconds (`158`) or `MM:SS` (`2:38`). Default time derived from `.fur`: one loop if the song loops, otherwise the end of the stopping pattern.

An entire directory can be converted at once:
  * `convert.sh songs/ -o build` (add `--recursive` to include subdirectories)

Hopefully you'll have fun with this driver alongside [furNES](https://github.com/AnnoyedArt1256/furNES) and [furC64](https://github.com/AnnoyedArt1256/furC64) :D

This project is based off [Pinobatch's](https://github.com/pinobatch) [lorom-template](https://github.com/pinobatch/lorom-template)
Libraries used: chipchune

