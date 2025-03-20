from chipchune.furnace.module import FurnaceModule
from chipchune.furnace.data_types import InsFeatureMacro, InsFeatureSNES, InsFeatureAmiga
from chipchune.furnace.enums import MacroCode, MacroItem, MacroType
from chipchune.furnace.enums import InstrumentType, SNESSusMode
import sys, math

subsong = 0
note_transpose = 0
dups = {}

print(sys.argv)
module = FurnaceModule(sys.argv[1])
chnum = module.get_num_channels()
flags = module.chips.list[0].flags

speed_type = len(module.subsongs[subsong].speed_pattern)
song_clock = module.subsongs[subsong].timing.clock_speed
print(module.subsongs[subsong].timing.clock_speed)
notes = ["C_","Cs","D_","Ds","E_","F_","Fs","G_","Gs","A_","As","B_"]

def comp(pat):
    i = 0
    o = []
    n = 0
    while i < len(pat):
        j = i
        k = 0
        if pat[i] >= 0x40 and pat[i] < 128: i += 1
        elif pat[i] == 0xFB: i += 2
        elif pat[i] == 0xFC: i += 2
        elif pat[i] == 0xE0: i += 2
        elif pat[i] == 0xE1: i += 2
        elif pat[i] == 0xE2: i += 2
        elif pat[i] == 0xE3: i += 2
        elif pat[i] == 0xE4: i += 2
        elif pat[i] == 0xE5: i += 3
        elif pat[i] == 0xE6: i += 2
        elif pat[i] == 0xE9: i += 3
        elif pat[i] == 0xEA: i += 3
        elif pat[i] == 0xEB: i += 2
        elif pat[i] == 0xEC: i += 2
        elif pat[i] == 0xED: i += 2
        elif pat[i] == 0xEE: i += 2
        elif pat[i] == 0xEF: i += 1
        elif pat[i] == 0xF0: i += 1
        elif pat[i] == 0xF1: i += 1
        elif pat[i] == 0xF2: i += 1
        elif pat[i] == 0xF3: i += 2
        elif pat[i] == 0xF4: i += 2
        elif pat[i] == 0xF5: i += 2
        elif pat[i] == 0xF6: i += 2
        elif pat[i] == 0xF7: i += 3
        elif pat[i] == 0xFF: i += 2
        elif pat[i] == 0xFD:
            i += 1
            n = 2
        elif pat[i] == 0xFE:
            i += 1
            n = 2
        elif pat[i] >= 128:
            i += 1
            n = 2
        else:
            k = 1
            if n == 0:
                o.append(pat[i])
            elif pat[i] > 1:
                o.append(pat[i]-1)
            #print(i,pat[i])
            i += 1
        n = max(n-1,0)
        if k == 0:
            o.extend(pat[j:i])
    #print(pat,"\n",o,"\n")
    return o

def conv_pattern(pattern):
    out = [0]
    oldtemp = [0,0]
    r = 0
    bitind = 0
    oldins = -1
    for row in pattern.data:
        has03xx = 0
        for l in row.effects:
            k = list(l)
            if k[0] == 0x03 and k[1] > 0:
                has03xx = 1
                break

        temp = []
        notnote = 0
        new_byte = 0
        if row.instrument != 65535 and oldins != row.instrument:
            new_byte = 1
            if row.instrument < 0x40:
                temp.append(row.instrument+0x40)
            else:
                temp.append(0xFB)
                temp.append(row.instrument)
            oldins = row.instrument
        if row.volume != 65535:
            new_byte = 1
            temp.append(0xFC)
            temp.append(row.volume&127)

        hasEffect = [-1,-1]
        has0Dxx = -1
        for l in row.effects:
            k = list(l)
            if k[1] == 65535:
                k[1] = 0

            if k[0] == 0xD:
                new_byte = 1
                has0Dxx = k[1]
                continue
            if k[0] == 0x0B:
                new_byte = 1
                temp.extend([0xED, k[1]])
                has0Dxx = 0
                continue
            if (k[0] == 0x09 or k[0] == 0x0F) and (speed_type == 1):
                new_byte = 1
                temp.extend([0xE1, k[1]])
                temp.extend([0xE0, k[1]])
                continue
            if k[0] == 0x0F and (speed_type == 2):
                new_byte = 1
                temp.extend([0xE1, k[1]])
                continue
            if k[0] == 0x09 and (speed_type == 2):
                new_byte = 1
                temp.extend([0xE0, k[1]])
                continue
            if k[0] >= 0x01 and k[0] <= 0x03 and k[1] == 0:
                new_byte = 1
                temp.extend([0xF1])
                continue
            if ((k[0] == 0xE1 or k[0] == 0xE2) and (k[1]>>4) == 0):
                new_byte = 1
                temp.extend([0xF1])
                continue
            if k[0] == 0x00:
                new_byte = 1
                temp.extend([0xE2, k[1]])
                continue
            if k[0] == 0x01:
                new_byte = 1
                temp.extend([0xE3, k[1]])
                continue
            if k[0] == 0x02:
                new_byte = 1
                temp.extend([0xE4, k[1]])
                continue
            if k[0] == 0x03 and k[1] == 0:
                new_byte = 1
                temp.extend([0xF1])
                continue
            if k[0] == 0x03 and k[1] > 0:
                new_byte = 1
                temp.extend([0xE5, k[1], max(min(notes.index(str(row.note))+(row.octave*12)+note_transpose,0xDF-0x80),0)])
                continue
            if k[0] == 0x04 and (k[1]>>4) == 0:
                new_byte = 1
                temp.extend([0xF2])
                continue
            if k[0] == 0x04 and (k[1]&15) == 0:
                new_byte = 1
                temp.extend([0xF2])
                continue
            if k[0] == 0x04:
                new_byte = 1
                temp.extend([0xE6, k[1]])
                continue
            if k[0] == 0x0A:
                new_byte = 1
                if k[1] == 0:
                    temp.extend([0xF3, 0])
                elif k[1] < 0x10:
                    temp.extend([0xF3, (k[1]|0x10)<<2])
                else:
                    temp.extend([0xF3, (k[1]>>4)<<2])
                continue
            if k[0] == 0xFA:
                new_byte = 1
                if k[1] == 0:
                    temp.extend([0xF3, 0])
                elif k[1] < 0x10:
                    temp.extend([0xF3, (max(min(k[1]*5,15),0)|0x10)<<2])
                else:
                    temp.extend([0xF3, (max(min((k[1]>>4)*5,15),0)|0x10)<<2])
                continue
            if k[0] == 0xE1:
                new_byte = 1
                temp.extend([0xE9, k[1]>>4, k[1]&15])
                continue
            if k[0] == 0xE2:
                new_byte = 1
                temp.extend([0xEA, k[1]>>4, k[1]&15])
                continue
            if k[0] == 0xE5:
                new_byte = 1
                temp.extend([0xEB, k[1]])
                continue
            if k[0] == 0xEC:
                new_byte = 1
                temp.extend([0xEC, k[1]])
                continue
            if k[0] == 0xED:
                new_byte = 1
                temp.extend([0xEE, k[1]])
                continue
            if k[0] == 0xEA:
                new_byte = 1
                if k[1] == 0:
                    temp.extend([0xEF])
                else:
                    temp.extend([0xF0])
                continue
            if k[0] == 0x10:
                new_byte = 1
                temp.extend([0xF4,k[1]])
                continue
            if k[0] == 0x11:
                new_byte = 1
                temp.extend([0xF5,k[1]])
                continue
            if k[0] == 0x1D:
                new_byte = 1
                temp.extend([0xF6,k[1]])
                continue
            if k[0] == 0x13:
                new_byte = 1
                temp.extend([0xF7,0x00,k[1]])
                continue

        if str(row.note) == "OFF_REL":
            notnote = 1
            new_byte = 1
            temp.append(0xFD)
        elif str(row.note) == "REL":
            notnote = 1
            new_byte = 1
            temp.append(0xFD)
        elif str(row.note) == "OFF":
            notnote = 1
            new_byte = 1
            temp.append(0xFE)
        elif str(row.note) == "__" or (has03xx == 1):
            if has03xx == 0:
                notnote = 1
            #temp.append(0x80)
        else:
            new_byte = 1
            temp.append(max(min(notes.index(str(row.note))+(row.octave*12)+note_transpose,0xDF-0x80),0)+0x80)

        if new_byte == 1:
            temp.append(0)
        out.extend(temp)
        durpass = False
        if out[-1] >= 63:
            out.append(0)
        if has0Dxx > -1:
            out[-1] += 1
            if out[0] == 0: out = out[1:]
            out.extend([0xFF, has0Dxx])
            return out
        out[-1] += 1
        r += 1
    out.extend([0xFF, 0])
    if out[0] == 0: out = out[1:]
    return out

f = open("src/song.s","w")

f.write("TIMER_HZ = "+str(round(song_clock))+"\n")

f.write("echo_info:\n.byte ")
try:
    print(flags)
    f.write(str(0 if bool(flags['echo']) else 32)+", ")
    f.write(str(int(flags['echoVolL'])&0xff)+", ")
    f.write(str(int(flags['echoVolR'])&0xff)+", ")
    f.write(str(int(flags['echoFeedback'])&0xff)+", ")
    f.write(str(int(flags['echoDelay'])&15)+", ")
    for i in range(8):
        f.write(str(int(flags["echoFilter"+str(i)])&0xff)+", ")

    f.write(str(0xff-((int(flags['echoDelay'])&15)<<3))+", ")
    f.write(str(int(flags['echoMask'])+"\n"))
except:
    f.write("32, 0, 0, 0, 0, ")
    for i in range(8):
        f.write("0, ")
    f.write("248\n")

relV = []
relA = []
relD = []
relS = []
relN = []

f.write("ticks_init:")
f.write(".byte ")
if speed_type == 1:
    f.write(str(module.subsongs[subsong].speed_pattern[0])+", ")
    f.write(str(module.subsongs[subsong].speed_pattern[0])+"\n")
elif speed_type == 2:
    f.write(str(module.subsongs[subsong].speed_pattern[0])+", ")
    f.write(str(module.subsongs[subsong].speed_pattern[1])+"\n")

f.write("insVL:\n")
f.write(".lobytes ")
for i in range(len(module.instruments)):
    f.write("ins"+str(i)+"V")
    if i == len(module.instruments)-1:
        f.write("\n")
    else:
        f.write(", ")
f.write("insVH:\n")
f.write(".hibytes ")
for i in range(len(module.instruments)):
    f.write("ins"+str(i)+"V")
    if i == len(module.instruments)-1:
        f.write("\n")
    else:
        f.write(", ")

f.write("insAL:\n")
f.write(".lobytes ")
for i in range(len(module.instruments)):
    f.write("ins"+str(i)+"A")
    if i == len(module.instruments)-1:
        f.write("\n")
    else:
        f.write(", ")
f.write("insAH:\n")
f.write(".hibytes ")
for i in range(len(module.instruments)):
    f.write("ins"+str(i)+"A")
    if i == len(module.instruments)-1:
        f.write("\n")
    else:
        f.write(", ")

f.write("insDL:\n")
f.write(".lobytes ")
for i in range(len(module.instruments)):
    f.write("ins"+str(i)+"D")
    if i == len(module.instruments)-1:
        f.write("\n")
    else:
        f.write(", ")
f.write("insDH:\n")
f.write(".hibytes ")
for i in range(len(module.instruments)):
    f.write("ins"+str(i)+"D")
    if i == len(module.instruments)-1:
        f.write("\n")
    else:
        f.write(", ")

f.write("insEL:\n")
f.write(".lobytes ")
for i in range(len(module.instruments)):
    f.write("ins"+str(i)+"E")
    if i == len(module.instruments)-1:
        f.write("\n")
    else:
        f.write(", ")
f.write("insEH:\n")
f.write(".hibytes ")
for i in range(len(module.instruments)):
    f.write("ins"+str(i)+"E")
    if i == len(module.instruments)-1:
        f.write("\n")
    else:
        f.write(", ")


f.write("insSL:\n")
f.write(".lobytes ")
for i in range(len(module.instruments)):
    f.write("ins"+str(i)+"S")
    if i == len(module.instruments)-1:
        f.write("\n")
    else:
        f.write(", ")
f.write("insSH:\n")
f.write(".hibytes ")
for i in range(len(module.instruments)):
    f.write("ins"+str(i)+"S")
    if i == len(module.instruments)-1:
        f.write("\n")
    else:
        f.write(", ")


f.write("insNL:\n")
f.write(".lobytes ")
for i in range(len(module.instruments)):
    f.write("ins"+str(i)+"N")
    if i == len(module.instruments)-1:
        f.write("\n")
    else:
        f.write(", ")
f.write("insNH:\n")
f.write(".hibytes ")
for i in range(len(module.instruments)):
    f.write("ins"+str(i)+"N")
    if i == len(module.instruments)-1:
        f.write("\n")
    else:
        f.write(", ")


all_wavs = []

if len(module.wavetables) > 0:
    for i in range(len(module.wavetables)):
        data = module.wavetables[i].data
        wav = []
        for j in range(128):
            l = module.wavetables[i].meta.width/128
            k = min(int(j*l),module.wavetables[i].meta.width-1)
            fuck = int((data[k]/(module.wavetables[i].meta.height-1))*15)&15
            wav.append((fuck-8)&15)
        all_wavs.append(wav)

adsrModes = []
wav_lens = []
pre_waves = {}
has_noise = []
for i in range(len(module.instruments)):
    features = module.instruments[i].features

    a = filter(
        lambda x: (
            type(x) == InsFeatureAmiga
        ), features
    )

    use_wave = False
    f.write("ins"+str(i)+"W:\n")
    for j in a:
        if j.use_wave:
            f.write(".addr ")
            for m in range(len(module.wavetables)):
                f.write("ins"+str(i)+"W"+str(m))
                if m == (len(module.wavetables)-1):
                    f.write("\n")
                else:
                    f.write(", ")
            wl = ((j.wave_len+1)>>4)<<4
            wav_lens.append(wl)
            l = []
            for k in range(wl):
                fp = (k/(wl-1))*127
                l.append(math.floor(fp))
            for m in range(len(module.wavetables)):
                o = []
                for p in range(len(l)>>4):
                    o.append(0xb0)
                    for q in range(8):
                        o.append((all_wavs[m][l[p*16+q*2]]<<4)|all_wavs[m][l[p*16+q*2+1]])
                o[-9] = 0xb3
                o = str(o)[1:-1]
                if o in pre_waves:
                    f.write("ins"+str(i)+"W"+str(m)+" = "+pre_waves[o]+"\n")
                else:
                    f.write("ins"+str(i)+"W"+str(m)+":\n.byte "+o+"\n")
                    pre_waves[o] = "ins"+str(i)+"W"+str(m)
            use_wave = 1
        break

    if not use_wave:
        wav_lens.append(16)

    a = filter(
        lambda x: (
            type(x) == InsFeatureSNES
        ), features
    )
    adsrMode = 0
    adsrWritten = False
    for j in a:
        adsr = 0
        if j.use_env:
            adsr = 0x8000
            adsr |= (j.envelope.a&15)<<8
            adsr |= (j.envelope.d&7)<<12
            adsr |= (j.envelope.s&7)<<5
            if j.sus == SNESSusMode.DIRECT:
                adsr |= (j.envelope.r&31)
            else:
                adsr |= (j.d2&31)
        else:
            adsr = 0x0000            
        adsr = [(adsr>>8)&0xff,adsr&0xff]
        print(hex(i),[hex(k) for k in adsr])
        f.write("ins"+str(i)+"E:\n.byte "+str(adsr)[1:-1])
        if not j.use_env:
            adsrMode = 3
            f.write(", "+str(j.gain)+"\n")
        elif j.sus == SNESSusMode.SUS_WITH_REL:
            adsrMode = 1
            adsr = (j.envelope.s&7)<<5
            adsr |= (j.envelope.r&31)
            print(hex(i),hex(adsr),j.envelope)
            f.write(", "+str(adsr)+"\n")
        elif j.sus == SNESSusMode.SUS_WITH_DEC:
            adsrMode = 2
            adsr = 0x80
            adsr |= j.envelope.r&31
            print(hex(adsr))
            f.write(", "+str(adsr)+"\n")
        elif j.sus == SNESSusMode.SUS_WITH_EXP:
            adsrMode = 2
            adsr = 0xa0
            adsr |= j.envelope.r&31
            print(hex(adsr))
            f.write(", "+str(adsr)+"\n")
        f.write("\n")
        adsrWritten = True
        break
    if not adsrWritten:
        f.write("ins"+str(i)+"E:\n.byte 255, 224\n")
    adsrModes.append(adsrMode|(use_wave*32))

    a = filter(
        lambda x: (
            type(x) == InsFeatureMacro
        ), features
    )
    arp = [128,0xFF,0xFF]
    duty = [0xFF,0xFF]
    vol = [0x7F,0xFF,0xFF]
    special = [0xFF,0xFF]
    noise = [0xFF,0xFF]
    macros = []
    for j in a:
        macros = j.macros
    hasRelTotal = [0,0,0,0,0]
    has_noise.append(0)
    for j in macros:
        kind = j.kind
        if kind == MacroCode.VOL:
            s = j.speed
            vol = []
            loop = 0xff
            loop2 = 0
            hasRel = 0
            for k in j.data:
                if k == MacroItem.LOOP:
                    loop = loop2
                elif k == MacroItem.RELEASE:
                    vol.append(0xFF)
                    vol.append(loop)
                    relV.append(len(vol))
                    hasRel = 1
                else:
                    loop2 = len(vol)
                    vol.append(k&127)
            if hasRel == 0:
                relV.append(len(vol))
            hasRelTotal[0] = 1
            vol.append(0xFF)
            vol.append(loop)
        if kind == MacroCode.ARP:
            s = j.speed
            arp = []
            loop = 0xff
            hasRel = 0
            oldlen = 0
            if j.data[-1] == MacroItem.LOOP:
                arr = [MacroItem.LOOP, j.data[-2]]
                j.data = j.data[:-2] + arr
            for k in j.data:
                if k == MacroItem.LOOP:
                    loop = oldlen
                elif k == MacroItem.RELEASE:
                    arp.append(0xFF)
                    arp.append(loop)
                    relA.append(len(arp))
                    oldlen = max(len(arp),0)
                    hasRel = 1
                elif (k>>30) > 0:
                    arp.append(0xFE)
                    k = abs(k^(1<<30))
                    k = max(min(k,95),0)
                    arp.append(k%120)
                    oldlen = max(len(arp),0)
                else:
                    if k < 0:
                        arp.append((k%120)-120+128)
                    else:
                        arp.append((k%120)+128)
                    oldlen = max(len(arp),0)
            if hasRel == 0:
                relA.append(len(arp))
            hasRelTotal[1] = 1
            arp.append(0xFF)
            arp.append(loop)
        if kind == MacroCode.WAVE:
            s = j.speed
            duty = []
            loop = 0xff
            loop2 = 0
            hasRel = 0
            for k in j.data:
                if k == MacroItem.LOOP:
                    loop = loop2
                elif k == MacroItem.RELEASE:
                    duty.append(0xFF)
                    duty.append(loop)
                    relD.append(len(duty))
                    hasRel = 1
                else:
                    loop2 = len(duty)
                    duty.append(k)
            if hasRel == 0:
                relD.append(len(duty))
            hasRelTotal[2] = 1
            duty.append(0xFF)
            duty.append(loop)
        if kind == MacroCode.EX1:
            s = j.speed
            special = []
            loop = 0xff
            loop2 = 0
            hasRel = 0
            for k in j.data:
                if k == MacroItem.LOOP:
                    loop = loop2
                elif k == MacroItem.RELEASE:
                    special.append(0xFF)
                    special.append(loop)
                    relS.append(len(special))
                    hasRel = 1
                else:
                    loop2 = len(special)
                    special.append(k&31)
            if hasRel == 0:
                relS.append(len(special))
            hasRelTotal[3] = 1
            special.append(0xFF)
            special.append(loop)
        if kind == MacroCode.DUTY:
            s = j.speed
            noise = []
            loop = 0xff
            loop2 = 0
            hasRel = 0
            for k in j.data:
                if k == MacroItem.LOOP:
                    loop = loop2
                elif k == MacroItem.RELEASE:
                    noise.append(0xFF)
                    noise.append(loop)
                    relS.append(len(noise))
                    hasRel = 1
                else:
                    loop2 = len(noise)
                    noise.append(k&31)
            if hasRel == 0:
                relS.append(len(noise))
            hasRelTotal[4] = 1
            noise.append(0xFF)
            noise.append(loop)
            has_noise[-1] = 1

    if hasRelTotal[0] == 0:
        relV.append(0)
    if hasRelTotal[1] == 0:
        relA.append(0)
    if hasRelTotal[2] == 0:
        relD.append(0)
    if hasRelTotal[3] == 0:
        relS.append(0)
    if hasRelTotal[4] == 0:
        relN.append(0)
    vol = str(vol)[1:-1]
    duty = str(duty)[1:-1]
    arp = str(arp)[1:-1]
    special = str(special)[1:-1]
    noise = str(noise)[1:-1]

    if arp in dups:
        f.write("ins"+str(i)+"A = "+dups[arp]+"\n")
    else:
        f.write("ins"+str(i)+"A:\n")
        f.write(".byte "+arp+"\n")
        dups[arp] = "ins"+str(i)+"A"

    if duty in dups:
        f.write("ins"+str(i)+"D = "+dups[duty]+"\n")
    else:
        f.write("ins"+str(i)+"D:\n")
        f.write(".byte "+duty+"\n")
        dups[duty] = "ins"+str(i)+"D"

    if vol in dups:
        f.write("ins"+str(i)+"V = "+dups[vol]+"\n")
    else:
        f.write("ins"+str(i)+"V:\n")
        f.write(".byte "+vol+"\n")
        dups[vol] = "ins"+str(i)+"V"

    if special in dups:
        f.write("ins"+str(i)+"S = "+dups[special]+"\n")
    else:
        f.write("ins"+str(i)+"S:\n")
        f.write(".byte "+special+"\n")
        dups[special] = "ins"+str(i)+"S"

    if noise in dups:
        f.write("ins"+str(i)+"N = "+dups[noise]+"\n")
    else:
        f.write("ins"+str(i)+"N:\n")
        f.write(".byte "+noise+"\n")
        dups[noise] = "ins"+str(i)+"N"

relV = str(relV)[1:-1]
relD = str(relD)[1:-1]
relA = str(relA)[1:-1]
relS = str(relS)[1:-1]
f.write("insArel:\n")
f.write(".byte "+relA+"\n")
f.write("insDrel:\n")
f.write(".byte "+relD+"\n")
f.write("insVrel:\n")
f.write(".byte "+relV+"\n")
f.write("insSrel:\n")
f.write(".byte "+relS+"\n")

for i in range(chnum):
    order = module.subsongs[subsong].order[i]
    f.write("order"+str(i)+"len = "+str(len(order))+"\n")
    f.write("order"+str(i)+"L:\n")
    f.write(".byte ")
    for o in range(len(order)):
        f.write("<(patCH"+str(i)+"N"+str(order[o])+"-1)")
        if o == len(order)-1:
            f.write("\n")
        else:
            f.write(", ")
    f.write("order"+str(i)+"H:\n")
    f.write(".byte ")
    for o in range(len(order)):
        f.write(">(patCH"+str(i)+"N"+str(order[o])+"-1)")
        if o == len(order)-1:
            f.write("\n")
        else:
            f.write(", ")

total_maps = []
for i in range(len(module.instruments)):
    features = module.instruments[i].features
    a = filter(
        lambda x: (
            type(x) == InsFeatureAmiga
        ), features
    )
    use_map = False
    for j in a:
        if j.use_note_map == True:
            use_map = True
            break
    a = filter(
        lambda x: (
            type(x) == InsFeatureAmiga
        ), features
    )
    f.write("ins"+str(i)+"DP:\n")
    if use_map == True:
        f.write(".byte ")
        for j in a:
            for k in range(len(j.sample_map)):
                f.write(str(j.sample_map[k].freq))
                if k == (len(j.sample_map)-1):
                    f.write("\n")
                else:
                    f.write(", ")
            break
    else:
        f.write(".byte 255\n")
    f.write("ins"+str(i)+"DI:\n")
    a = filter(
        lambda x: (
            type(x) == InsFeatureAmiga
        ), features
    )
    if use_map == True:
        f.write(".byte ")
        for j in a:
            for k in range(len(j.sample_map)):
                if j.sample_map[k].sample_index == 65535:
                    f.write("0")
                else:
                    f.write(str(j.sample_map[k].sample_index))
                if k == (len(j.sample_map)-1):
                    f.write("\n")
                else:
                    f.write(", ")
            break
    else:
        init_sample = 0
        for j in a:
            if j.init_sample > 0 and j.init_sample != 65535:
                init_sample = j.init_sample
                break
        f.write(".byte "+str(init_sample)+"\n")

f.write("insPCMIL:\n")
f.write(".lobytes ")
for i in range(len(module.instruments)):
    f.write("ins"+str(i)+"DI")
    if i == len(module.instruments)-1:
        f.write("\n")
    else:
        f.write(", ")
f.write("insPCMIH:\n")
f.write(".hibytes ")
for i in range(len(module.instruments)):
    f.write("ins"+str(i)+"DI")
    if i == len(module.instruments)-1:
        f.write("\n")
    else:
        f.write(", ")

f.write("insPCMPL:\n")
f.write(".lobytes ")
for i in range(len(module.instruments)):
    f.write("ins"+str(i)+"DP")
    if i == len(module.instruments)-1:
        f.write("\n")
    else:
        f.write(", ")
f.write("insPCMPH:\n")
f.write(".hibytes ")
for i in range(len(module.instruments)):
    f.write("ins"+str(i)+"DP")
    if i == len(module.instruments)-1:
        f.write("\n")
    else:
        f.write(", ")

for i in range(chnum):
    order = module.subsongs[subsong].order[i]
    avail_patterns = filter(
        lambda x: (
            x.channel == i and
            x.subsong == subsong
        ),
        module.patterns
    )
    for p in avail_patterns:
        patnum = p.index
        #print(patnum,i)
        g = str(comp(conv_pattern(p)))[1:-1]
        f.write("patCH"+str(i)+"N"+str(patnum)+":\n")
        f.write(".byte "+g+"\n")

g = open("src/sampledir.s","w")
for i in range(len(module.samples)):
    sample = [int(j) for j in list(module.samples[i].data)]
    start = 0
    end = max(len(sample),1)
    loop = end-1
    loope = len(module.samples[i].data)-9
    sample[loope] |= 1
    if module.samples[i].meta.loop_start != 4294967295:
        loop = int((module.samples[i].meta.loop_start/16)*9)
        sample[loope] |= 2
    #print(i,loop,loope,len(module.samples[i].data))
    g.write(".addr "+"sample"+str(i)+", "+"sample"+str(i)+"+"+str(loop)+"\n")
    f.write(".res 15-(*&15),0\n")
    f.write("sample"+str(i)+":\n.byte "+str(sample)[1:-1]+"\n")  
g.close()

cnote = 440 * (2**(float(12*4-69-0.5)/12.0))
anote = 16
print(cnote,anote)
f.write("insPCMRL:\n")
f.write(".lobytes ")
for i in range(len(module.samples)):
    sr = module.samples[i].meta.sample_rate
    print(i,sr)
    sr = int((sr/cnote)*anote)
    f.write(str(sr))
    if i == len(module.samples)-1:
        f.write("\n")
    else:
        f.write(", ")

f.write("insPCMRH:\n")
f.write(".hibytes ")
for i in range(len(module.samples)):
    sr = module.samples[i].meta.sample_rate
    sr = int((sr/cnote)*anote)
    f.write(str(sr))
    if i == len(module.samples)-1:
        f.write("\n")
    else:
        f.write(", ")

f.write("insM:\n")
f.write(".byte ")
for i in range(len(adsrModes)):
    f.write(str(adsrModes[i]))
    if i == len(adsrModes)-1:
        f.write("\n")
    else:
        f.write(", ")

f.write("insWL:\n")
f.write(".lobytes ")
for i in range(len(module.instruments)):
    f.write("ins"+str(i)+"W")
    if i == len(module.instruments)-1:
        f.write("\n")
    else:
        f.write(", ")

f.write("insWH:\n")
f.write(".hibytes ")
for i in range(len(module.instruments)):
    f.write("ins"+str(i)+"W")
    if i == len(module.instruments)-1:
        f.write("\n")
    else:
        f.write(", ")


f.write("insWLen:\n")
f.write(".byte ")
for i in range(len(wav_lens)):
    f.write(str((wav_lens[i]>>4)-1))
    if i == len(wav_lens)-1:
        f.write("\n")
    else:
        f.write(", ")

f.write("insNhas:\n")
f.write(".byte ")
for i in range(len(has_noise)):
    f.write(str(has_noise[i]))
    if i == len(has_noise)-1:
        f.write("\n")
    else:
        f.write(", ")


f.close()

tuning = module.meta.tuning
f = open("src/note_lo.bin","wb")
for i in range(128):
    freq = tuning * (2**(float(i-57)/12.0))
    f.write(bytearray([int(freq)&0xff]))
f.close()
f = open("src/note_hi.bin","wb")
for i in range(128):
    freq = tuning * (2**(float(i-57)/12.0))
    f.write(bytearray([(int(freq)>>8)&0xff]))
f.close()
