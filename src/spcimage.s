.setcpu "none"
.include "spc-65c02.inc"

.define loop_pattern_num 0
.define porta_once 1
.define SLIDE_SPEED 0

; 0: legacy method
; 1: non-legacy (MORE ACCURATE) method (still non-linear though)
.define SLIDE_METHOD 1

.define chnum 8

.macro decx addr
 pha
 lda addr, x
 dec a
 sta addr, x 
 pla
.endmacro

.macro incx addr
 pha
 lda addr, x
 inc a
 sta addr, x 
 pla
.endmacro

.macro ldya addr
.local addr1
addr1 = addr
 lda (<addr), y
.endmacro


.macro stya addr
.local addr1
addr1 = addr
  .assert addr <= $00FE, error, "stya works only in zero page"
  movw <addr, ya
.endmacro

; MMIO at $00F0-$00FF
TIMEREN     := $00F1  ; 0-2: enable timer; 7: enable ROM in $FFC0-$FFFF
DSPADDR     := $00F2
DSPDATA     := $00F3
TIMERPERIOD := $00FA  ; Divisors for timers (0, 1: 8 kHz base; 2: 64 kHz base)
TIMERVAL    := $00FD  ; Number of times timer incremented (bits 3-0; cleared on read)

DSP_CLVOL    = $00
DSP_CRVOL    = $01
DSP_CFREQLO  = $02  ; Playback frequency in 7.8125 Hz units
DSP_CFREQHI  = $03  ; (ignored 
DSP_CSAMPNUM = $04  
DSP_CATTACK  = $05  ; 7: set; 6-4: decay rate; 3-0: attack rate
DSP_CSUSTAIN = $06  ; 7-5: sustain level; 4-0: sustain decay rate
DSP_CGAIN    = $07  ; Used only when attack is disabled

DSP_LVOL     = $0C
DSP_ECHOFB = $0D
DSP_RVOL     = $1C
DSP_LECHOVOL = $2C
DSP_RECHOVOL = $3C
DSP_KEYON    = $4C
DSP_KEYOFF   = $5C
DSP_FLAGS    = $6C  ; 5: disable echo; 4-0: set LFSR rate
DSP_FMCH     = $2D  ; Modulate these channels' frequency by the amplitude before it
DSP_NOISECH  = $3D  ; Replace these channels with LFSR noise
DSP_ECHOCH   = $4D  ; Echo comes from these channels
DSP_SAMPDIR  = $5D  ; High byte of base address of sample table
DSP_ECHOSTRT = $6D
DSP_ECHODEL  = $7D

.export sample_dir, spc_entry

.segment "SPCZEROPAGE"
sample_mapped: .res chnum

kon_mirror: .res 1
koff_mirror: .res 1

patzp: .res 4

patseq: .res chnum*2

temp: .res 5

note_n: .res chnum

note_pitch_lo: .res chnum
note_pitch_hi: .res chnum

macroIns: .res 3

volume_add: .res chnum
vol_tick: .res chnum

vibrato_param: .res chnum
vibrato_phase: .res chnum

note_table_temp: .res 2

inst_prev_note: .res chnum

ch: .res 1

nextpat: .res 1
patind: .res 1
jumppat: .res 1
tick: .res 1
effects_temp: .res 2
slide_amt: .res chnum
slide_amt_sign: .res chnum
slide_buffer_lo: .res chnum
slide_buffer_hi: .res chnum
note_dest: .res chnum
T1: .res 2
T2: .res 2
PRODUCT: .res 6
noise_freq: .res 1
noise_mask: .res 1
pmod_mask: .res 1
flags: .res 1
do_port: .res chnum

.segment "SPCIMAGE"
.align 256
.org $200
sample_dir:
  ; each directory entry is 4 bytes:
  ; a start address then a loop address
  .include "sampledir.s"
  nop  ; resync debugger's disassembly
.res $400-*
  .res 4*8

mframeV: .res chnum
mframeA: .res chnum
mframeS: .res chnum
mframeD: .res chnum
mframeN: .res 1
doMacroV: .res chnum
doMacroA: .res chnum
doMacroS: .res chnum
doMacroD: .res chnum
doMacroN: .res 1
insN: .res 1

special: .res chnum

duty: .res chnum

dur: .res chnum

arp: .res chnum
absarp: .res chnum

isoff: .res chnum

vol: .res chnum
volm: .res chnum
volout: .res chnum

ins: .res chnum
inst_prev: .res chnum

tick_speeds: .res 2
tick_sel: .res 1

didporta: .res chnum

legato: .res chnum

note_tick: .res chnum

finepitch: .res chnum
cut_dur: .res chnum
arpeff1: .res chnum
arpeff2: .res chnum
arpind: .res chnum
note_nums: .res chnum
delay_do: .res 1
note_delay: .res chnum
xt: .res 2
yt: .res 1
wav_length: .res chnum
cursamp: .res chnum

.align 256
spc_entry:
  jsr initaddr
nexttick:
:
  lda TIMERVAL
  beq :-
  jsr playaddr
  jmp nexttick

on_ch:
    pha
    lda kon_mirror
    ora kon_table, x
    sta kon_mirror
    lda koff_mirror
    ora kon_table, x
    sta koff_mirror
    stx xt
    lda ins, x
    sta wav_length, x
    tax
    lda insNhas, x
    beq @skip
    stx insN
    lda #$ff
    sta doMacroN
    lda #0
    sta mframeN
@skip:

    ldx xt
    lda ins, x
    tax
    lda insM, x
    and #3
    cmp #3
    bne on_skip2

    ldx xt

    lda ins, x
    tay
    lda insEL, y
    sta temp+2
    lda insEH, y
    sta temp+3

    txa
    xcn a
    ora #5
    sta DSPADDR
    tax
    lda #0
    sta DSPDATA
    inx
    stx DSPADDR
    lda #0
    sta DSPDATA
    inx
    ldy #2
    ldya temp+2
    stx DSPADDR
    sta DSPDATA

on_skip2:
    ldx xt
    lda #$ff
    sta sample_mapped, x
    pla
    rts

.macro add_off_ch
    .local skip, skip2, skip3
    pha
    stx xt
    sty yt
    lda ins, x
    tax
    lda insM, x
    and #3
    cmp #0
    bne :+
    ldx xt
    lda koff_mirror
    ora kon_table, x
    sta koff_mirror
    jmp skip
:
    lda insM, x
    and #3
    cmp #1
    beq skip2

    ldx xt

    lda ins, x
    tay
    lda insEL, y
    sta temp+2
    lda insEH, y
    sta temp+3
    txa
    xcn a
    ora #7
    sta DSPADDR
    ldy #2
    ldya temp+2
    sta DSPDATA

    txa
    xcn a
    ora #5
    sta DSPADDR
    lda #0
    sta DSPDATA

    jmp skip3
skip2:
    ldx xt
    lda ins, x
    tay
    lda insEL, y
    sta temp+2
    lda insEH, y
    sta temp+3
    txa
    xcn a
    ora #6
    sta DSPADDR
    ldy #2
    ldya temp+2
    sta DSPDATA
skip3:
skip:
    ldx xt
    ldy yt
    pla
.endmacro

off_ch:
  add_off_ch
  rts

kon_table:
.repeat 8, I
    .byte 1<<I
.endrepeat
.repeat 8, I
    .byte 255^(1<<I)
.endrepeat

table_1_to_ff:
table_fil:
  .byte 0
  .res 15, $ff

.proc initaddr
  ldy #$7F
  lda #DSP_LVOL  ; overall output volume left
  stya DSPADDR
  lda #DSP_RVOL  ; overall output volume right
  stya DSPADDR

  ; Disable the APU features we're not using
  ldy echo_info
  sty flags
  lda #DSP_FLAGS
  stya DSPADDR
  ldy #$00
  lda #DSP_KEYON  ; Clear key on
  stya DSPADDR
  lda #DSP_FMCH   ; Clear frequency modulation
  stya DSPADDR

  dey
  lda #DSP_KEYOFF  ; Key off everything
  stya DSPADDR
  iny

  ldy #%00000000
  sty noise_mask
  sty pmod_mask
  lda #DSP_NOISECH  ; LFSR noise on no channels
  stya DSPADDR
  ldy #0
  lda #DSP_ECHOCH  ; Echo on no channels
  stya DSPADDR

  lda #DSP_KEYOFF
  ldy #0
  stya DSPADDR
  lda #DSP_KEYON
  sta DSPADDR

  lda #DSP_SAMPDIR  ; set sample directory start address
  ldy #>sample_dir
  stya DSPADDR

  lda echo_info
  and #32
  bne skip_echo

  ldx #7
:
  txa
  xcn a
  ora #$0f
  sta DSPADDR
  lda echo_info+5, x
  sta DSPDATA
  dex
  bpl :-


  ldy echo_info+3
  lda #DSP_ECHOFB  ; overall output volume left
  stya DSPADDR


  ldy echo_info+13
  lda #DSP_ECHOSTRT
  stya DSPADDR

  ldy echo_info+4
  lda #DSP_ECHODEL
  stya DSPADDR
  
  ldy echo_info+1
  lda #DSP_LECHOVOL  ; overall output volume left
  stya DSPADDR
  ldy echo_info+2
  lda #DSP_RECHOVOL  ; overall output volume right
  stya DSPADDR

skip_echo:

  lda #8000/TIMER_HZ  ; S-Pently will use 125 Hz
  sta TIMERPERIOD
  lda #%10000001
  sta TIMEREN
  lda TIMERVAL

  lda #1
  sta tick_sel

  lda ticks_init
  sta tick_speeds
  lda ticks_init+1
  sta tick_speeds+1

  lda #0
  sta doMacroN
  sta patind
  sta mframeN
  sta delay_do
  ldx #chnum-1
:
  lda #$7f
  sta vol, x
  sta volm, x
  lda #$80
  sta finepitch, x
  lda #1
  sta dur, x
  lda #$ff
  sta note_delay, x
  sta cut_dur, x
  sta vol_tick, x
  sta isoff, x
  lda #0
  sta wav_length, x
  sta special, x
  sta didporta, x
  sta volume_add, x
  sta ins, x
  sta inst_prev, x
  sta arp, x
  sta slide_amt, x
  sta slide_amt_sign, x
  sta slide_buffer_lo, x
  sta slide_buffer_hi, x
  sta vibrato_phase, x
  sta vibrato_param, x
  sta note_dest, x
  sta mframeA, x
  sta mframeD, x
  sta mframeS, x
  sta mframeV, x
  sta doMacroA, x
  sta doMacroD, x
  sta doMacroS, x
  sta doMacroV, x
  sta sample_mapped, x
  lda #4
  sta note_tick, x
  dex
  bpl :-

  ; initialize the EON register
  ldx #0
  ldy echo_info+14 ; echoMask
:
  ; set bit 1 to echo mask 
  tya
  and #1
  asl
  sta special, x

  tya
  lsr
  tay

  inx
  cpx #chnum
  bne :-

  ldx #0
  stx koff_mirror
  stx patind
  jsr set_patseq
  ldx #chnum-1
:
  lda #1
  sta dur, x
  dex
  cpx #$ff
  bne :-

  lda #0
  sta tick
  sta jumppat


  lda #0
  ldx #$4c
  stx DSPADDR
  sta DSPDATA
  sta kon_mirror
  rts
.endproc

.macro get_patzp
  ;incw patzp
  .byte $3a, <patzp
  lda (<patzp), y
.endmacro

.macro add_09xx
effectE0:
  get_patzp
  sta tick_speeds
  jmp begnote
.endmacro


.macro add_0Fxx
effectE1:
  get_patzp
  sta tick_speeds+1
  jmp begnote
.endmacro

.macro add_0Bxx
effectED:
  get_patzp
  sta patind
  lda #$ff
  sta jumppat
  jmp begnote
.endmacro


.macro add_00xx
effectE2:
  get_patzp
  sta effects_temp+1
  ldx ch
  lda #0
  sta arpind, x
  lda effects_temp+1
  and #$0f
  sta arpeff2, x
  lda effects_temp+1
  lsr
  lsr
  lsr
  lsr
  sta arpeff1, x
  jmp begnote
.endmacro


.macro add_01xx
effectE3:
  get_patzp
  ldx ch
  sta slide_amt, x
  lda #$ff
  sta slide_amt_sign, x
  ldx ch
  lda #88
  sta note_dest, x
  lda #$ff
  sta didporta, x
  lda #SLIDE_SPEED+1
  sta do_port, x
  jmp begnote
.endmacro

.macro add_02xx
effectE4:
  get_patzp
  ldx ch
  sta slide_amt, x
  lda #$00
  sta slide_amt_sign, x
  ldx ch
  lda #8
  sta note_dest, x
  lda #$ff
  sta didporta, x
  lda #SLIDE_SPEED+1
  sta do_port, x
  jmp begnote
.endmacro

.macro add_03xx
effectE5:
  get_patzp
  ldx ch
  sta slide_amt, x
  ldy #0
  get_patzp
  ldx ch
  sta note_dest, x

  lda note_n, x
  cmp note_dest, x
  bne :+
  lda #0
  sta slide_amt, x
  sta slide_amt_sign, x
  jmp begnote
:
  bcc :+
  lda #$00
  sta slide_amt_sign, x
  lda #$ff
  sta didporta, x
  lda #SLIDE_SPEED+1
  sta do_port, x
  jmp begnote
:
  lda #$ff
  sta slide_amt_sign, x
  lda #$ff
  sta didporta, x
  lda #SLIDE_SPEED+1
  sta do_port, x
  jmp begnote
.endmacro

.macro add_04xx
  .local retskip
effectE6:
  get_patzp
  ldx ch
  sta vibrato_param, x
  beq retskip
  sta vibrato_phase, x
retskip:
  jmp begnote
.endmacro

.macro add_E1xx
effectE9:
  get_patzp
  ldx ch
  asl
  asl
  sta slide_amt, x
  lda #$ff
  sta slide_amt_sign, x
  ldy #0
  get_patzp
  ldx ch
  ora #$80
  sta note_dest, x
  lda #$ff
  sta didporta, x
  lda #SLIDE_SPEED+1
  sta do_port, x
  jmp begnote
.endmacro

.macro add_E2xx
effectEA:
  get_patzp
  ldx ch
  asl
  asl
  sta slide_amt, x
  lda #$00
  sta slide_amt_sign, x
  ldy #0
  get_patzp
  ldx ch
  ora #$80
  sta note_dest, x
  lda #$ff
  sta didporta, x
  lda #SLIDE_SPEED+1
  sta do_port, x
  jmp begnote
.endmacro


.macro add_E5xx
effectEB:
  get_patzp
  ldx ch
  sta finepitch, x
  jmp begnote
.endmacro

.macro add_ECxx
effectEC:
  get_patzp
  ldx ch
  sta cut_dur, x
  incx cut_dur
  jmp begnote
.endmacro

.macro add_EDxx
effectEE:
  lda delay_do
  beq skip_delay2
  get_patzp
  jmp begnote
skip_delay2:
  get_patzp
  ldx ch
  sta note_delay, x
  lda #1
  sta dur, x
  rts
.endmacro


.macro add_EAxx
effectEF:
  ldx ch
  lda #0
  sta legato, x
  jmp begnote

effectF0:
  ldx ch
  lda #$ff
  sta legato, x
  jmp begnote
.endmacro

.macro add_0Axx
  .local skip, skip2
effectF3:
  get_patzp
  ldx ch
  sta volume_add, x
  cmp #0
  bne skip2
  lda vol_tick, x
  ora #$80
  sta vol_tick, x
  jmp begnote
skip2:
  lda vol_tick, x
  and #3
  sta vol_tick, x
  jmp begnote
skip:
.endmacro



.macro add_10xx
effectF4:
  get_patzp
  ldx ch
  sta duty, x
  jmp begnote
.endmacro

.macro add_11xx
effectF5:
  get_patzp
  ldx ch
  and #1
  cmp #1
  beq :+

  lda noise_mask
  and kon_table+8, x
  sta noise_mask
  jmp begnote
:
  lda noise_mask
  ora kon_table, x
  sta noise_mask
  jmp begnote
.endmacro

.macro add_1Dxx
effectF6:
  get_patzp
  sta noise_freq
  jmp begnote
.endmacro

.macro set_pmod
  .local skip
  get_patzp
  ldx ch
  and #1
  cmp #1
  beq skip

  lda pmod_mask
  and kon_table+8, x
  sta pmod_mask
  jmp begnote
skip:
  lda pmod_mask
  ora kon_table, x
  sta pmod_mask
.endmacro

; EExx (used in unflavoured stock cube for the main cube part)
.macro add_ext
effectF7:
  get_patzp
  cmp #$00
  bne :+
  set_pmod
:
  jmp begnote
.endmacro


add_09xx
add_0Fxx
add_00xx
add_01xx
add_02xx
add_03xx
add_04xx
add_0Axx
add_0Bxx
add_10xx
add_11xx
add_1Dxx
add_E1xx
add_E2xx
add_E5xx
add_EAxx
add_ECxx
add_EDxx
add_ext

other_effects:
  lda effects_temp
  cmp #$FB
  bne :+
  ldx ch
  get_patzp
  sta ins, x
  jmp begnote
:
  cmp #$FC
  bne :+
  get_patzp
  ldx ch
  sta vol, x
  jmp begnote
:

  cmp #$FD
  bne :+
  ldx ch
  lda ins, x
  tay
  lda insVrel, y
  sta mframeV, x
  lda insArel, y
  sta mframeA, x
  lda insDrel, y
  sta mframeD, x
  lda insSrel, y
  sta mframeS, x
  ldx ch
  lda #$ff
  sta isoff, x
  jsr off_ch
  lda #1
  ldx ch
  sta dur, x
  ldy #0
  jmp end_advance
:

  cmp #$FE
  bne :+
  ldx ch
  lda #$ff
  sta isoff, x
  jsr off_ch
  lda #0
  sta doMacroA, x
  sta doMacroV, x
  sta doMacroD, x
  sta doMacroS, x
  lda #1
  sta dur, x
  ldy #0
  jmp end_advance
:
 lda effects_temp
 cmp #224
 bcs :+
 jmp cont_advance
:

 lda effects_temp
 and #$1f
 tax
 lda eff_lo, x
 sta effect_smc+1
 lda eff_hi, x
 sta effect_smc+2
 ldx ch
 lda effects_temp
effect_smc:
 jmp cont_advance

effectE7:
effectE8:
 jmp cont_advance


effectF1:
  ldx ch
  lda #$00
  sta slide_amt_sign, x
  sta slide_amt, x
  sta note_dest, x
  lda #$ff
  sta didporta, x
  jmp begnote

effectF2:
  ldx ch
  lda #0
  sta vibrato_param, x
  sta vibrato_phase, x
  jmp begnote

eff_lo:
.repeat $18, I
    ; i use .ident to automatically make jump tables for effects
    .lobytes .ident(.concat ("effect", .sprintf("%02X",I+$e0)))
.endrepeat
eff_hi:
.repeat $18, I
    ; i use .ident to automatically make jump tables for effects
    .hibytes .ident(.concat ("effect", .sprintf("%02X",I+$e0)))
.endrepeat

.macro add_advance_routine
advance:
  .local skipD, noIns, noVol, beg, blank2, blank3, hasNote, wait
beg:
  lda ch
  asl a
  tax
  lda patseq, x
  sta patzp
  lda patseq+1, x
  sta patzp+1
  ldx ch
  lda dur, x
  dec a
  sta dur, x
  beq begnote
  jmp end_advance
begnote:

  ldy #0
  get_patzp
  sta temp
  sta effects_temp
  and #$80
  bne :+
  jmp wait
:
  lda temp
  cmp #$ff
  bne :+
  jmp blank2
:
  jmp other_effects
cont_advance:
  lda temp
  and #$7f
  ldx ch
  sta note_n, x
  lda note_tick, x
  cmp #96
  bne :+
  lda didporta, x
  bne :+
  lda #0
  sta slide_amt, x
  sta slide_amt_sign, x
  sta do_port, x
:
  lda note_tick, x
  cmp #2
  bcc :+
  lda legato, x
  bne :+
  lda #0
  sta mframeV, x
  sta mframeA, x
  sta mframeD, x
  sta mframeS, x
  sta isoff, x
  jsr on_ch
  lda #$ff
  sta doMacroA, x
  sta doMacroV, x
  sta doMacroD, x
  sta doMacroS, x

  lda ins, x
  tay
  lda insEL, y
  sta temp+2
  lda insEH, y
  sta temp+3
  txa
  xcn a
  ora #5
  sta DSPADDR
  ldy #0
  ldya temp+2
  sta DSPDATA
  txa
  xcn a
  ora #6
  sta DSPADDR
  ldy #1
  ldya temp+2
  sta DSPDATA

:
  lda #0
  sta slide_buffer_lo, x
  sta slide_buffer_hi, x
  sta note_tick, x
  ldx ch
  lda #1
  sta dur, x
  ldy #0
  jmp end_advance

wait:
  lda temp
  and #$40
  beq :+
  ldx ch
  lda temp
  and #$3f
  sta ins, x
  jmp begnote
:
  lda temp
  ldx ch
  sta dur, x
blank2:
  lda temp
  cmp #$ff
  bne end_advance

  lda #$ff
  sta nextpat

end_advance:
  lda ch
  asl a
  tax
  lda patzp
  sta patseq, x
  lda patzp+1
  sta patseq+1, x
  rts
.endmacro

add_advance_routine

.macro add_insarp
insarp:
  .local end, skip1, beg, skip2
beg:
  ldx ch
  lda doMacroA, x
  bne :+
  jmp end
:

  ldx ch
  lda ins, x
  tay
  lda insAL, y
  sta macroIns
  lda insAH, y
  sta macroIns+1
  ldx ch
  lda mframeA, x
  tay
  ldya macroIns
  cmp #$fe
  beq skip2
  cmp #$ff
  bne skip1
  iny
  ldya macroIns
  cmp #$ff
  beq :+
  sta mframeA, x
  jmp beg
:
  lda #0
  sta doMacroA, x
  rts
skip1:
  sec
  sbc #128
  sta arp, x
  lda #0
  sta absarp, x
  incx mframeA
  rts
skip2:
  iny
  ldya macroIns
  sta arp, x
  lda #$ff
  sta absarp, x
  incx mframeA
  incx mframeA
end:
  rts
.endmacro

add_insarp

.macro add_insduty
insduty:
  .local end, skip1, beg, skip2
beg:
  ldx ch
  lda doMacroD, x
  beq end

  ldx ch
  lda ins, x
  tay
  lda insDL, y
  sta macroIns
  lda insDH, y
  sta macroIns+1
  ldx ch
  lda mframeD, x
  tay
  ldya macroIns
  sta temp
  cmp #$ff
  bne skip1
  iny
  ldya macroIns
  cmp #$ff
  beq :+
  sta mframeD, x
  jmp beg
:
  lda #0
  sta doMacroD, x
  rts
skip1:
  lda temp
  ldx ch
  sta duty, x
  incx mframeD
end:
  rts
.endmacro

add_insduty

.macro add_insvol
insvol:
  .local end, skip1, beg, skip2
beg:
  ldx ch
  lda doMacroV, x
  beq end

  ldx ch
  lda ins, x
  tay
  lda insVL, y
  sta macroIns
  lda insVH, y
  sta macroIns+1
  ldx ch
  lda mframeV, x
  tay
  ldya macroIns
  sta temp
  cmp #$ff
  bne skip1
  iny
  ldya macroIns
  cmp #$ff
  beq :+
  sta mframeV, x
  jmp beg
:
  lda #0
  sta doMacroV, x
  rts
skip1:
  lda temp
  ldx ch
  sta volm, x
  incx mframeV
end:
  rts
.endmacro

add_insvol

.macro add_insspec
insspec:
  .local end, skip1, beg, skip2
beg:
  ldx ch
  lda doMacroS, x
  beq end

  ldx ch
  lda ins, x
  tay
  lda insSL, y
  sta macroIns
  lda insSH, y
  sta macroIns+1
  ldx ch
  lda mframeS, x
  tay
  ldya macroIns
  sta temp
  cmp #$ff
  bne skip1
  iny
  ldya macroIns
  cmp #$ff
  beq :+
  sta mframeS, x
  jmp beg
:
  lda #0
  sta doMacroS, x
  rts
skip1:
  lda temp
  ldx ch
  sta special, x
  incx mframeS
end:
  rts
.endmacro

add_insspec


.macro add_insnois
insnois:
  .local end, skip1, beg, skip2
beg:
  lda doMacroN
  beq end

  ldy insN
  lda insNL, y
  sta macroIns
  lda insNH, y
  sta macroIns+1
  ldy mframeN
  ldya macroIns
  sta temp
  cmp #$ff
  bne skip1
  iny
  ldya macroIns
  cmp #$ff
  beq :+
  sta mframeN
  jmp beg
:
  lda #0
  sta doMacroN
  rts
skip1:
  lda temp
  and #31
  sta noise_freq
  incx mframeN
end:
  rts
.endmacro

add_insnois

.macro cmp16 val1, val2
    lda val1
    sec
    sbc val2
    php
    lda val1+1
    sbc val2+1
    php
    pla
    sta macroIns
    pla
    and #%00000010
    ora #%11111101
    and macroIns
    pha
    plp
.endmacro

doFinePitch:

  lda vibrato_param, x
  lsr
  lsr
  lsr
  lsr
  clc
  adc vibrato_phase, x
  and #63
  sta vibrato_phase, x
  tay
  lda vibrato_param, x
  and #$0f
  ora triangle_lookup, y
  tay

  clc
  lda note_pitch_lo, x
  ;adc #($80+$1f)
  ;adc #($80+$40)
  adc #$80
  sta temp
  lda note_pitch_hi, x
  adc #1
  sta temp+1

  sec
  lda temp
  sbc finepitch, x
  sta temp
  bcs :+
  dec temp+1
:
;  bcs skip_pitch
;  lda #0
;  sta temp
;  sta temp+1
;skip_pitch:


.repeat 2
  sec
  lda temp
  sbc tri_vibrato_lookup, y
  sta temp
  bcs :+
  dec temp+1
:
.endrepeat

  rts

.proc playaddr
  ldx tick_sel
  inc tick
  lda tick
  cmp tick_speeds, x
  bcs :+
  jmp skipseq
:
  lda #0
  sta tick

advance_tick:


  lda tick_sel
  eor #1
  sta tick_sel
  lda #0
  sta delay_do
  ; advances each channel's pattern data one by one
  .repeat chnum, I
    lda #I
    sta ch
    jsr advance
  .endrepeat

  lda nextpat
  beq skipnextpat
  lda #0
  sta nextpat
  lda jumppat
  beq :+
  lda #0
  sta jumppat
  jmp :++
:
  inc patind
  lda patind
  cmp #order0len
  bne :+
  lda #0 ; #patloop
  sta patind
:
  jsr set_patseq
  ldx #chnum-1
  lda #1
durloop:
    sta dur, x
    dex
    bpl durloop
  jmp advance_tick
skipnextpat:
  lda jumppat
  beq :+
  lda #$ff
  sta nextpat
:


skipseq:

  lda #$ff
  sta delay_do

  ; support for EDxx

  ldx #chnum-1
note_delay_loop:
  stx ch
  lda note_delay, x
  cmp #$ff
  beq note_delay_loop_end
  decx note_delay
  lda note_delay, x
  cmp #0
  beq :+
  jmp note_delay_loop_end
:
  jsr advance
note_delay_loop_end:
  ldx ch
  dex
  bpl note_delay_loop

  ; this is for the 0Axx effect to work
  ldx #chnum-1
vol_add_loop:
  lda vol_tick, x
  and #$80
  bne vol_add_loop_end
  lda vol_tick, x
  and #3
  sta vol_tick, x
  incx vol_tick
  ora volume_add, x
  tay
  lda vol_slide_lookup, y
  clc
  adc vol, x
  sta vol, x
  and #$80
  cmp #$80
  bne :+
  lda #0
  sta vol, x
  jmp vol_add_loop_end
:
  lda vol, x
  cmp #$7f
  bcc vol_add_loop_end
  lda #$7f
  sta vol, x
vol_add_loop_end:
  dex
  bpl vol_add_loop


  ; ECxx effect implementation
  ldx #chnum-1
note_cut_loop:
  lda cut_dur, x
  cmp #$ff
  beq note_cut_loop_end
  decx cut_dur
  lda cut_dur, x
  beq :+
  jmp note_cut_loop_end
:
  lda #$ff
  sta cut_dur, x
  sta isoff, x
  jsr off_ch

note_cut_loop_end:
  dex
  bpl note_cut_loop
  
  ; this does sample mapping for instruments that have a custom sample map(?)
.repeat 8, I
  lda sample_mapped+I
  beq :+++

  ldx ins+I

  lda insPCMIL, x
  sta patzp
  lda insPCMIH, x
  sta patzp+1

  ldy note_n+I
  ldya patzp
  sta macroIns

  lda insPCMPL, x
  sta patzp
  lda insPCMPH, x
  sta patzp+1

  ldy #0
  ldya patzp
  cmp #$ff
  bne :+
  lda note_n+I
  sta macroIns+1
  lda insPCMIL, x
  sta patzp
  lda insPCMIH, x
  sta patzp+1
  ldy #0
  ldya patzp
  sta macroIns
  jmp :++
:
  ldy note_n+I
  ldya patzp
  sta macroIns+1
:
  lda macroIns
  sta cursamp+I
  lda macroIns+1
  sta note_n+I
  lda #0
  sta sample_mapped+I
:

.endrepeat

  ; pre-pitch-slide code
  ldx #chnum-1
relslide_loop:
  lda note_dest ,x
  and #$80
  beq slide_skip
  eor note_dest ,x
  sta macroIns
  lda slide_amt_sign, x
  beq positive_slide2
  lda note_n, x
  clc
  adc macroIns
  jsr clamp_note
  sta note_dest, x
  jmp slide_skip
positive_slide2:
  lda note_n, x
  sec
  sbc macroIns
  jsr clamp_note
  sta note_dest, x
slide_skip:
  dex
  bpl relslide_loop

  ; now let's do the actual pitch sliding (non-linear atm)

  ldx #chnum-1
slide_loop:
  lda slide_amt, x
  bne :+
  jmp slide_loop2
:
  lda slide_amt_sign, x
  bne positive_slide
  jsr sub_pitch
  lda note_dest, x
  tay
  jsr gen_note_table
  lda note_table_temp
  sta patzp
  lda note_table_temp+1
  sta patzp+1
  lda note_pitch_lo, x
  sta temp
  lda note_pitch_hi, x
  sta temp+1
  cmp16 patzp, temp
  bcs finish_slide
  jmp slide_loop2
positive_slide:
  jsr add_pitch
  jmp :+
finish_slide:
  lda note_dest, x
  sta note_n, x
  lda #0
  sta slide_buffer_lo, x
  sta slide_buffer_hi, x
  sta slide_amt, x
  sta slide_amt_sign, x
  sta do_port, x
  jmp slide_loop2
:
  lda note_dest, x
  tay
  jsr gen_note_table
  lda note_table_temp
  sta patzp
  lda note_table_temp+1
  sta patzp+1
  lda note_pitch_lo, x
  sta temp
  lda note_pitch_hi, x
  sta temp+1
  cmp16 temp, patzp
  bcc slide_loop2
  jmp finish_slide
slide_loop2:
  dex
  bmi slide_loopt
  jmp slide_loop
slide_loopt:

  ldx #chnum-1
:
  lda note_tick, x
  cmp #96
  beq note_tick_loop
  incx note_tick
note_tick_loop:
  dex
  bpl :-

  ; macro tiem
.repeat chnum, I
  lda #I
  sta ch
  jsr insarp
  jsr insvol
  jsr insduty
  jsr insspec
.endrepeat
  jsr insnois

  ; pitch bends go brr
  ldx #chnum-1
note_loop:
  lda absarp, x
  beq nrel
  lda arp, x
  and #127
  jmp nout
nrel:
  lda note_n, x
  clc
  adc arp, x
nout:
  clc
  jsr add_arpeff
  jsr clamp_note
  sta note_nums, x
  tay
  .if SLIDE_METHOD = 1
  jsr gen_note_table_slide
  lda note_table_temp
  sta note_pitch_lo, x
  lda note_table_temp+1
  sta note_pitch_hi, x
  .else
  jsr gen_note_table
  clc
  lda note_table_temp
  adc slide_buffer_lo, x
  sta note_pitch_lo, x
  lda note_table_temp+1
  adc slide_buffer_hi, x
  sta note_pitch_hi, x
  .endif
  dex
  bpl note_loop

  ; calculate final volume from volume column and volume macros
  ldx #chnum-1
vol_loop:
  lda volm, x
  tay
  lda vol, x
  mul ya
  tya
  sta volout, x
  dex
  bpl vol_loop

.repeat 8, I
  lda wav_length+I
  tay
  lda insWL, y
  sta temp
  lda insWH, y
  sta temp+1

  ldy #0
  lda duty+I
  asl a
  tay
  lda (<temp), y
  sta $400+I*4+0
  sta $400+I*4+2
  iny
  lda (<temp), y
  sta $400+I*4+1
  sta $400+I*4+3
.endrepeat

  lda koff_mirror
  cmp #0
  beq :+
  ldx #$5c
  stx DSPADDR
  sta DSPDATA
:


.repeat 8, I
  ldx #I
  jsr doFinePitch
  lda volout+I
  ldx #I<<4
  stx DSPADDR
  sta DSPDATA  
  inx
  stx DSPADDR
  sta DSPDATA  
  lda temp
  inx
  stx DSPADDR
  sta DSPDATA  
  lda temp+1
  inx
  stx DSPADDR
  sta DSPDATA  
  inx
  ldy wav_length+I
  lda insM, y
  and #32
  beq :+
  lda #$80+I
  stx DSPADDR
  sta DSPDATA  
  jmp :++
:
  lda cursamp+I
  stx DSPADDR
  sta DSPDATA  
:
.endrepeat

  lda koff_mirror
  cmp #0
  beq :+
  lda #0
  ldx #$5c
  stx DSPADDR
  sta DSPDATA
  sta koff_mirror
:

  lda kon_mirror
  cmp #0
  beq :+
  ldx #$4c
  stx DSPADDR
  sta DSPDATA
  lda #0
  sta kon_mirror
:

  lda flags
  ora noise_freq
  ldx #$6c
  stx DSPADDR
  sta DSPDATA

  lda #0
.repeat 8, I
  pha
  lda special+I
  and #1
  tax
  pla
  cpx #1
  bne :+
  ora #1<<I
:
.endrepeat
  ora noise_mask
  ldx #$3d
  stx DSPADDR
  sta DSPDATA


  lda #0
.repeat 8, I
  pha
  lda special+I
  and #2
  tax
  pla
  cpx #2
  bne :+
  ora #1<<I
:
.endrepeat
  ldx #$4d
  stx DSPADDR
  sta DSPDATA

  lda #0
.repeat 7, I
  pha
  lda special+I+1
  and #4
  tax
  pla
  cpx #4
  bne :+
  ora #1<<(I+1)
:
.endrepeat
  ora pmod_mask
  and #%11111110
  ldx #$2d
  stx DSPADDR
  sta DSPDATA

  rts
.endproc

set_patseq:
  stx temp+2

  ldx patind

  .repeat chnum, I
    lda .ident(.concat ("order", .sprintf("%d",I), "L")), x
    sta patseq+0+2*I
    lda .ident(.concat ("order", .sprintf("%d",I), "H")), x
    sta patseq+1+2*I
  .endrepeat

  ldx temp+2
  rts

set_patseq_init:
  ldx patind
  .repeat chnum, I
    lda .ident(.concat ("order", .sprintf("%d",I), "L")), x
    sta patseq+0+2*I
    lda .ident(.concat ("order", .sprintf("%d",I), "H")), x
    sta patseq+1+2*I
  .endrepeat
  rts

add_arpeff:
  pha
  incx arpind
  lda arpind, x
  tay
  lda arp_mod, y
  sta arpind, x
  tay
  pla
  cpy #1
  beq arp1
  cpy #2
  beq arp2
  rts

arp1:
  clc
  adc arpeff1, x
  rts

arp2:
  clc
  adc arpeff2, x
  rts

arp_mod:
.byte 0,1,2,0

clamp_note:
  cmp #95
  bcc :+
  lda #95
:
  rts

note_table_lo:
    .incbin "note_lo.bin"
note_table_hi:
    .incbin "note_hi.bin"

.if SLIDE_METHOD = 1
gen_note_table_slide:
    sty PRODUCT+4
    stx PRODUCT+5
    pha

    lda slide_buffer_lo, x
    sta T2
    lda slide_buffer_hi, x
    sta T2+1

    lda T2+1
    asl
    ror T2+1
    ror T2

    lda T2+1
    asl
    ror T2+1
    ror T2

    lda T2+1
    asl
    ror T2+1
    ror T2

    lda note_table_lo, y
    clc
    adc T2
    sta T2
    lda note_table_hi, y
    adc T2+1
    sta T2+1

    lda wav_length, x
    tay
    lda insM, y
    and #32
    beq :+
    lda insWLen, y
    tay
    lda insWAVRL, y
    sta T1
    lda insWAVRH, y
    sta T1+1
    jmp :++
:
    lda cursamp, x
    tax
    lda insPCMRL, x
    sta T1
    lda insPCMRH, x
    sta T1+1
:
    jsr multiply_16bit_unsigned
    ldx PRODUCT+5   
;    lda T1
;    sta $160, x
;    lda T1+1
;    sta $170, x
;.repeat 4, I
;    lda PRODUCT+I
;    sta $100+I*16, x
;.endrepeat

    lda PRODUCT+1
    sta note_table_temp
    lda PRODUCT+2
    sta note_table_temp+1
    pla
    ldy PRODUCT+4
    rts

.endif

gen_note_table:
    sty PRODUCT+4
    stx PRODUCT+5
    pha
    lda note_table_lo, y
    sta T2
    lda note_table_hi, y
    sta T2+1

    lda wav_length, x
    tay
    lda insM, y
    and #32
    beq :+
    lda insWLen, y
    tay
    lda insWAVRL, y
    sta T1
    lda insWAVRH, y
    sta T1+1
    jmp :++
:
    lda cursamp, x
    tax
    lda insPCMRL, x
    sta T1
    lda insPCMRH, x
    sta T1+1
:
    jsr multiply_16bit_unsigned
    ldx PRODUCT+5   
;    lda T1
;    sta $160, x
;    lda T1+1
;    sta $170, x
;.repeat 4, I
;    lda PRODUCT+I
;    sta $100+I*16, x
;.endrepeat

    lda PRODUCT+1
    sta note_table_temp
    lda PRODUCT+2
    sta note_table_temp+1
    pla
    ldy PRODUCT+4
    rts



triangle_lookup:
  .repeat 64, I
    .if (I+0)&32
      .byte ((32-(((I+0)&63)-32)-1)>>1)<<4
    .else
      .byte (((I+0)&63)>>1)<<4
    .endif
  .endrepeat

tri_vibrato_lookup:
  .repeat 16, J
    .repeat 16, I
      ;.byte ((I*((J>>1)-15)*2)/15)+$1f
      .byte ((I*((J<<1)-15)*4)/20)+$80
    .endrepeat
  .endrepeat


add_pitch:
  sty yt
  lda do_port, x
  tay
:
  clc
  lda slide_buffer_lo, x
  adc slide_amt, x
  sta slide_buffer_lo, x
  lda slide_buffer_hi, x
  adc #0
  sta slide_buffer_hi, x
  dey
  bpl :-
  ldy yt
  rts

sub_pitch:
  sty yt
  lda do_port, x
  tay
:
  sec
  lda slide_buffer_lo, x
  sbc slide_amt, x
  sta slide_buffer_lo, x
  lda slide_buffer_hi, x
  sbc #0
  sta slide_buffer_hi, x
  dey
  bpl :-
  ldy yt
  rts


vol_slide_lookup:
  .byte 0,0,0,0
  .byte 1,0,0,0
  .byte 1,0,1,0
  .byte 1,1,1,0
  .byte 1,1,1,1
  .byte 2,1,1,1
  .byte 2,1,2,1
  .byte 2,2,2,1
  .byte 2,2,2,2
  .byte 3,2,2,2
  .byte 3,2,3,2
  .byte 3,3,3,2
  .byte 3,3,3,3
  .byte 4,3,3,3
  .byte 4,3,4,3
  .byte 4,4,4,4

  .byte 000,000,000,000
  .byte 255,000,000,000
  .byte 255,000,255,000
  .byte 255,255,255,000
  .byte 255,255,255,255
  .byte 254,255,255,255
  .byte 254,255,254,255
  .byte 254,254,254,255
  .byte 254,254,254,254
  .byte 253,254,254,254
  .byte 253,254,253,254
  .byte 253,253,253,254
  .byte 253,253,253,253
  .byte 252,253,253,253
  .byte 252,253,252,253
  .byte 252,252,252,252

.proc multiply_16bit_unsigned                                             
                ; <T1 * <T2 = AAaa                                        
                ; <T1 * >T2 = BBbb                                        
                ; >T1 * <T2 = CCcc                                        
                ; >T1 * >T2 = DDdd                                        
                ;                                                         
                ;       AAaa                                              
                ;     BBbb                                                
                ;     CCcc                                                
                ; + DDdd                                                  
                ; ----------                                              
                ;   PRODUCT!                                                               

                ; Perform <T1 * <T2 = AAaa
                lda T2+0     
                ldy T1+0         
                mul ya    
                sta PRODUCT+0                   
                sty _AA+1                 

                ; Perform >T1_hi * <T2 = CCcc
                lda T2+0     
                ldy T1+1       
                mul ya     
                sta _cc+1                
                sty _CC+1                           

                lda T2+1   
                ldy T1+0         
                mul ya    
                sta _bb+1                  
                sty _BB+1                             


                lda T2+1   
                ldy T1+1       
                mul ya    
                sta _dd+1                   
                sty PRODUCT+3 

                ; Add the separate multiplications together
                clc                                        
_AA:            lda #0                                     
_bb:            adc #0                                     
                sta PRODUCT+1                              
_BB:            lda #0                                     
_CC:            adc #0                                     
                sta PRODUCT+2                              
                bcc :+                                     
                    inc PRODUCT+3                          
                    clc                                    
                :                                          
_cc:            lda #0                                     
                adc PRODUCT+1                              
                sta PRODUCT+1                              
_dd:            lda #0                                     
                adc PRODUCT+2                              
                sta PRODUCT+2                              
                bcc :+                                     
                    inc PRODUCT+3                          
                :                                          

                rts
.endproc           

insWAVRL:
    .repeat 16, I
        .lobytes (I+1)*525
    .endrepeat

insWAVRH:
    .repeat 16, I
        .hibytes (I+1)*525
    .endrepeat

.include "song.s"
