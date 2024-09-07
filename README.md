# furSPC
an SNES sound driver for Furnace

### **THIS SOUND DRIVER IS CURRENTLY A WIP**
### **IF THERE ARE ANY BUGS IN THE DRIVER PLEASE LET ME KNOW!!!**

FINALLY, an SNES driver that is not total dogwater to use!

* You have to have [Python](https://www.python.org/) and the [CC65 toolchain](https://cc65.github.io/) installed
* You **have** to set the pitch linearity option to "None". You can do this by going to `window -> song -> compatability flags -> Pitch/Playback -> Pitch linearity` and then setting the option to "None".

* The driver only supports **volume, arpeggio, waveform, noise freq and special** macros in each instrument and it DOESN'T support LFO and ADSR macros nor delay and step length

* The furSPC driver only supports these effects:
  * 00xx: arpeggio
  * 01xx: pitch slide up
  * 02xx: pitch slide down
  * 03xx: portamento
  * 04xx: vibrato
  * 09xx: set speed 1
  * 0Axx: volume slide
  * 0Bxx: jump to pattern
  * 0Dxx: jump to next pattern
  * 0Fxx: set speed 2
  * 10xx: set waveform
  * 11xx: toggle noise mode
  * 13xx: toggle pitch modulation
  * 1Dxx: set noise freq
  * E1xx: note slide up
  * E2xx: note slide down
  * E5xx: note fine-pitch
  * EAxx: legato
  * ECxx: note cut

when you've finished / want to test out this driver:
* open the terminal/command prompt **to the furSPC directory**
* run `convert.sh your_fur_file.fur` or `convert.bat file.fur` (depending on your OS)
* in the `furSPC` directory you'll hopefully see a file called **`furSPC-test.spc`**
  * that's your .spc file that you can run on any .spc compatible player!

Hopefully you'll have fun with this driver alongside [furNES](https://github.com/AnnoyedArt1256/furNES) and [furC64](https://github.com/AnnoyedArt1256/furC64) :D

This project is based off [Pinobatch's](https://github.com/pinobatch) [lorom-template](https://github.com/pinobatch/lorom-template)
Libraries used: chipchune

