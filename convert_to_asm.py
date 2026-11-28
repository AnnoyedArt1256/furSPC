from chipchune.furnace.module import FurnaceModule
from chipchune.furnace.data_types import InsFeatureMacro, InsFeatureSNES, InsFeatureAmiga, InsFeatureWaveSynth
from chipchune.furnace.enums import MacroCode, MacroItem, MacroType
from chipchune.furnace.enums import InstrumentType, SNESSusMode, SampleType
import sys, math, os

if __name__ == "__main__" and os.environ.get("FURSPC_LOWLEVEL") != "1":
    from convert_cli import main
    raise SystemExit(main())

subsong = 0
note_transpose = 0
dups = {}

print(sys.argv)
module = FurnaceModule(sys.argv[1])
if not module.instruments:
    print(
        "error: no instruments found; add at least one instrument in Furnace",
        file=sys.stderr,
    )
    raise SystemExit(1)
non_brr_samples = []
for sample_index, sample in enumerate(module.samples):
    depth = getattr(sample.meta, "depth", None)
    try:
        is_brr = int(depth) == int(SampleType.SNES_BRR.value)
    except (TypeError, ValueError):
        is_brr = False
    if not is_brr:
        non_brr_samples.append((
            sample_index,
            getattr(sample.meta, "name", "") or "unnamed",
            depth,
        ))
if non_brr_samples:
    print(
        "warning: non-BRR sample detected, please fix in furnace",
        file=sys.stderr,
    )
    for sample_index, sample_name, depth in non_brr_samples:
        print(
            f"  sample {sample_index}: {sample_name} (type {depth})",
            file=sys.stderr,
        )
chnum = module.get_num_channels()
flags = module.chips.list[0].flags


def all_effects(mod):
    for pat in mod.patterns:
        if pat.subsong != subsong:
            continue
        for row in pat.data:
            for cmd, val in row.effects:
                yield cmd, val


def instrument_macros(mod, kind):
    for ins in mod.instruments:
        for feature in ins.features:
            if isinstance(feature, InsFeatureMacro):
                for macro in feature.macros:
                    if macro.kind == kind:
                        yield macro


# Furnace stores the linear-pitch mode as a global compat flag.
linear_pitch = 1 if module.compat_flags.linear_pitch != 0 else 0
pitch_slide_speed = int(module.compat_flags.pitch_slide_speed_in_linear)
if pitch_slide_speed < 1:
    pitch_slide_speed = 1
elif pitch_slide_speed > 255:
    pitch_slide_speed = 255

# Panning is only needed when an effect or a panning macro changes it.
# panl/panr otherwise stay at the centered 0x7f default.
pan_used = any(cmd in (0x08, 0x80, 0x81, 0x82) for cmd, _ in all_effects(module))
if not pan_used:
    for kind in (MacroCode.PAN_L, MacroCode.PAN_R):
        for macro in instrument_macros(module, kind):
            if any(isinstance(value, int) and value != 0x7f for value in macro.data):
                pan_used = True
                break
        if pan_used:
            break

# Macro routines and their instrument tables are only needed when the
# corresponding macro exists somewhere in the module.
macro_vol_used = any(True for _ in instrument_macros(module, MacroCode.VOL))
macro_arp_used = any(True for _ in instrument_macros(module, MacroCode.ARP))
macro_wave_used = any(True for _ in instrument_macros(module, MacroCode.WAVE))
macro_spec_used = any(True for _ in instrument_macros(module, MacroCode.EX1))
macro_gain_used = any(True for _ in instrument_macros(module, MacroCode.EX2))
macro_noise_used = any(True for _ in instrument_macros(module, MacroCode.DUTY))
# Wavetable instruments need their selected wave set on note-on even when
# they have no WAVE macro. Furnace keeps wavetable animation on the first
# frame, so only wave_indices[0] is the default.
wave_default_used = any(
    isinstance(feature, InsFeatureAmiga)
    and feature.use_wave
    and len(module.wavetables) > 0
    for ins in module.instruments
    for feature in ins.features
)
# Furnace macro speed (step length) is per macro; only emit the extra
# counters and tables when at least one macro holds a step for >1 tick.
macro_speed_used = any(
    getattr(macro, "speed", 1) != 1
    for ins in module.instruments
    for feature in ins.features
    if isinstance(feature, InsFeatureMacro)
    for macro in feature.macros
)

# The pitch clamp is only needed when a reachable note can push the final
# DSP pitch past $3FFF. Use the highest pattern note plus the largest
# positive arpeggio macro offset, evaluated at every sample rate.
_song_note_names = ["C_", "Cs", "D_", "Ds", "E_", "F_", "Fs", "G_", "Gs", "A_", "As", "B_"]
_max_note = -1
for _pat in module.patterns:
    if _pat.subsong != subsong:
        continue
    for _row in _pat.data:
        try:
            _value = (
                _song_note_names.index(str(_row.note))
                + _row.octave * 12
                + note_transpose
            )
        except (TypeError, ValueError):
            continue
        _max_note = max(_max_note, _value)
_max_arp = 0
for _macro in instrument_macros(module, MacroCode.ARP):
    for _value in _macro.data:
        if isinstance(_value, int) and _value >= 0:
            _max_arp = max(_max_arp, _value)
if _max_note >= 0:
    _max_note = min(_max_note + _max_arp, 95)
pitch_clamp_used = False
if _max_note >= 0:
    _cnote = 440 * (2 ** (float(12 * 4 - 69 - 0.5) / 12.0))
    for _sample in module.samples:
        _rate = _sample.meta.sample_rate
        if not _rate:
            continue
        _factor = int((_rate / _cnote) * 16)
        _freq = module.meta.tuning * (2 ** ((_max_note - 57) / 12.0))
        _pitch = (((int(_freq) & 0xFFFF) * _factor) >> 8) & 0xFFFF
        if not linear_pitch:
            _pitch += 0x100
        if _pitch > 0x3FFF:
            pitch_clamp_used = True
            break

# Echo is only useful if it is enabled and at least one channel is routed
# to it, either by the initial mask, a 12xx effect, or an EX1 special macro.
echo_on = bool(flags.get('echo', False))
try:
    echo_mask = int(flags.get('echoMask', 0) or 0)
except (TypeError, ValueError):
    echo_mask = 0
echo_toggle_used = any(cmd == 0x12 for cmd, _ in all_effects(module))
echo_used = echo_on and (echo_mask != 0 or echo_toggle_used)
if echo_on and not echo_used:
    for macro in instrument_macros(module, MacroCode.EX1):
        if any(isinstance(value, int) and (value & 2) for value in macro.data):
            echo_used = True
            break
# The 12xx toggle handler is only needed when the song actually uses it.
echo_toggle_used = echo_toggle_used and echo_used

# SNES envelope release paths are only needed when an instrument uses them.
snes_env_modes = set()
for ins in module.instruments:
    sn = next((feature for feature in ins.features if type(feature) == InsFeatureSNES), None)
    if sn is None:
        snes_env_modes.add("DIRECT")
    elif not sn.use_env:
        snes_env_modes.add("GAIN")
    elif sn.sus == SNESSusMode.SUS_WITH_REL:
        snes_env_modes.add("REL")
    elif sn.sus == SNESSusMode.SUS_WITH_DEC:
        snes_env_modes.add("DEC")
    elif sn.sus == SNESSusMode.SUS_WITH_EXP:
        snes_env_modes.add("EXP")
    else:
        snes_env_modes.add("DIRECT")

with open("src/features.inc", "w") as feature_file:
    feature_file.write("; generated by convert_to_asm.py\n")
    feature_file.write(".define LINEAR_PITCH %d\n" % linear_pitch)
    feature_file.write(".define PITCH_SLIDE_SPEED %d\n" % pitch_slide_speed)
    feature_file.write(".define PAN_ENABLE %d\n" % (1 if pan_used else 0))
    feature_file.write(".define ECHO_ENABLE %d\n" % (1 if echo_used else 0))
    feature_file.write(".define ECHO_TOGGLE %d\n" % (1 if echo_toggle_used else 0))
    feature_file.write(".define EFFECT_COUNT %d\n" % (24 + int(bool(echo_toggle_used))))
    feature_file.write(".define SNES_ENV_DIRECT %d\n" % (1 if "DIRECT" in snes_env_modes else 0))
    feature_file.write(".define SNES_ENV_REL %d\n" % (1 if "REL" in snes_env_modes else 0))
    feature_file.write(".define SNES_ENV_DEC %d\n" % (1 if "DEC" in snes_env_modes else 0))
    feature_file.write(".define SNES_ENV_EXP %d\n" % (1 if "EXP" in snes_env_modes else 0))
    feature_file.write(".define SNES_ENV_GAIN %d\n" % (1 if "GAIN" in snes_env_modes else 0))
    feature_file.write(".define MACRO_VOL %d\n" % (1 if macro_vol_used else 0))
    feature_file.write(".define MACRO_ARP %d\n" % (1 if macro_arp_used else 0))
    feature_file.write(".define MACRO_WAVE %d\n" % (1 if macro_wave_used else 0))
    feature_file.write(".define MACRO_SPEC %d\n" % (1 if macro_spec_used else 0))
    feature_file.write(".define MACRO_GAIN %d\n" % (1 if macro_gain_used else 0))
    feature_file.write(".define MACRO_NOISE %d\n" % (1 if macro_noise_used else 0))
    feature_file.write(".define MACRO_SPEED %d\n" % (1 if macro_speed_used else 0))
    feature_file.write(".define PITCH_CLAMP %d\n" % (1 if pitch_clamp_used else 0))
    feature_file.write(".define WAVE_DEFAULT %d\n" % (1 if wave_default_used else 0))

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
        elif pat[i] == 0xE7: i += 3
        elif pat[i] == 0xE8: i += 2
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
        elif pat[i] == 0xF8: i += 2
        elif pat[i] == 0xF9: i += 3
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
            if k[0] == 0x04:
                new_byte = 1
                # Furnace stores an empty effect value as -1 and plays it as 0.
                vib = 0 if k[1] == 0xFFFF else (k[1] & 0xFF)
                if vib == 0 or (vib >> 4) == 0 or (vib & 15) == 0:
                    temp.extend([0xF2])
                else:
                    temp.extend([0xE6, vib])
                continue
            if k[0] == 0x08:
                new_byte = 1
                left = ((k[1] >> 4) | (k[1] & 0xf0)) >> 1
                right = ((k[1] & 0x0f) | ((k[1] & 0x0f) << 4)) >> 1
                temp.extend([0xE7, left & 0x7f, right & 0x7f])
                continue
            if k[0] == 0x80:
                new_byte = 1
                temp.extend([0xE7, min(255-k[1], 127), min(k[1], 127)])
                continue
            if k[0] == 0x81:
                new_byte = 1
                temp.extend([0xE8, (k[1] >> 1) & 0x7f])
                continue
            if k[0] == 0x82:
                new_byte = 1
                temp.extend([0xE8, 0x80 | ((k[1] >> 1) & 0x7f)])
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
            if k[0] == 0x12 and echo_toggle_used:
                # 12xx: toggle this channel's EON bit
                new_byte = 1
                temp.extend([0xF8,k[1]])
                continue
            if k[0] >= 0x20 and k[0] <= 0x23:
                new_byte = 1
                temp.extend([0xF9, k[0]-0x20, k[1]&0xff])
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

f.write("song_data_start:\n")
f.write("TIMER_HZ = "+str(round(song_clock))+"\n")

if echo_used:
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

        f.write(str(0xf8-((int(flags['echoDelay'])&15)<<3))+", ")
        f.write(str(int(flags['echoMask']))+"\n")
    except:
        f.write("32, 0, 0, 0, 0, ")
        for i in range(8):
            f.write("0, ")
        f.write("248, 0\n")

relV = []
relA = []
relD = []
relS = []
relN = []
relPL = []
relPR = []
relG = []
spdV = []
spdA = []
spdD = []
spdS = []
spdG = []
spdPL = []
spdPR = []
spdN = []

f.write("ticks_init:")
f.write(".byte ")
if speed_type == 1:
    f.write(str(module.subsongs[subsong].speed_pattern[0])+", ")
    f.write(str(module.subsongs[subsong].speed_pattern[0])+"\n")
elif speed_type == 2:
    f.write(str(module.subsongs[subsong].speed_pattern[0])+", ")
    f.write(str(module.subsongs[subsong].speed_pattern[1])+"\n")

f.write(".if MACRO_VOL\n")
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
f.write(".endif\n")

f.write(".if MACRO_ARP\n")
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
f.write(".endif\n")

f.write(".if MACRO_WAVE\n")
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
f.write(".endif\n")

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


f.write(".if MACRO_SPEC\n")
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
f.write(".endif\n")


f.write(".if MACRO_GAIN\n")
f.write("insGL:\n")
f.write(".lobytes ")
for i in range(len(module.instruments)):
    f.write("ins"+str(i)+"G")
    if i == len(module.instruments)-1:
        f.write("\n")
    else:
        f.write(", ")
f.write("insGH:\n")
f.write(".hibytes ")
for i in range(len(module.instruments)):
    f.write("ins"+str(i)+"G")
    if i == len(module.instruments)-1:
        f.write("\n")
    else:
        f.write(", ")
f.write(".endif\n")


f.write(".if MACRO_NOISE\n")
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
f.write(".endif\n")

if pan_used:
    f.write("insPLL:\n")
    f.write(".lobytes ")
    for i in range(len(module.instruments)):
        f.write("ins"+str(i)+"PL")
        if i == len(module.instruments)-1:
            f.write("\n")
        else:
            f.write(", ")
    f.write("insPLH:\n")
    f.write(".hibytes ")
    for i in range(len(module.instruments)):
        f.write("ins"+str(i)+"PL")
        if i == len(module.instruments)-1:
            f.write("\n")
        else:
            f.write(", ")

    f.write("insPRL:\n")
    f.write(".lobytes ")
    for i in range(len(module.instruments)):
        f.write("ins"+str(i)+"PR")
        if i == len(module.instruments)-1:
            f.write("\n")
        else:
            f.write(", ")
    f.write("insPRH:\n")
    f.write(".hibytes ")
    for i in range(len(module.instruments)):
        f.write("ins"+str(i)+"PR")
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
default_waves = []
pre_waves = {}
env_dups = {}
has_noise = []
for i in range(len(module.instruments)):
    features = module.instruments[i].features
    spd_v = spd_a = spd_d = spd_s = spd_g = 1
    spd_pl = spd_pr = spd_n = 1

    a = filter(
        lambda x: (
            type(x) == InsFeatureAmiga
        ), features
    )

    use_wave = False
    default_wave = 0
    f.write("ins"+str(i)+"W:\n")
    for j in a:
        if j.use_wave and len(module.wavetables) > 0:
            synth = None
            macros = None
            for feature in features:
                if type(feature) == InsFeatureWaveSynth:
                    synth = feature
                elif type(feature) == InsFeatureMacro:
                    macros = feature

            # Use only the wavetables the instrument actually selects.
            # Furnace's synthesizer animation is not emulated; the selected
            # source waveform is emitted as a looping BRR wavetable.
            used_waves = []
            if synth is not None and synth.enabled:
                w = synth.wave_indices[0]
                if 0 <= w < len(module.wavetables):
                    used_waves.append(w)
            if macros is not None:
                for macro in macros.macros:
                    if macro.kind != MacroCode.WAVE:
                        continue
                    for value in macro.data:
                        if isinstance(value, int) and 0 <= value < len(module.wavetables) and value not in used_waves:
                            used_waves.append(value)
            if not used_waves:
                used_waves.append(0)

            if synth is not None and synth.enabled and 0 <= synth.wave_indices[0] < len(module.wavetables):
                default_wave = synth.wave_indices[0]
            else:
                default_wave = used_waves[0]

            wl = max(16, min(256, ((j.wave_len+1)>>4)<<4))
            wav_lens.append(wl)

            # The pointer array is indexed by the raw wave macro value, so
            # keep one entry per module wavetable. Unused entries point at
            # the first selected wave.
            f.write(".addr ")
            for m in range(len(module.wavetables)):
                f.write("ins"+str(i)+"W"+str(m if m in used_waves else used_waves[0]))
                if m == (len(module.wavetables)-1):
                    f.write("\n")
                else:
                    f.write(", ")

            l = []
            for k in range(wl):
                fp = (k/(wl-1))*127
                l.append(math.floor(fp))
            for m in used_waves:
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
    default_waves.append(default_wave)

    a = filter(
        lambda x: (
            type(x) == InsFeatureSNES
        ), features
    )
    adsrMode = 0
    env_bytes = None
    for j in a:
        if j.use_env:
            adsr = 0x8000
            adsr |= (j.envelope.a&15)<<8
            adsr |= (j.envelope.d&7)<<12
            adsr |= (j.envelope.s&7)<<5
            if j.sus == SNESSusMode.DIRECT:
                adsr |= (j.envelope.r&31)
            else:
                adsr |= (j.d2&31)
            env_bytes = [(adsr>>8)&0xff, adsr&0xff]
            if j.sus == SNESSusMode.SUS_WITH_REL:
                adsrMode = 1
                env_bytes.append(((j.envelope.s&7)<<5)|(j.envelope.r&31))
            elif j.sus == SNESSusMode.SUS_WITH_DEC:
                adsrMode = 2
                env_bytes.append(0x80|(j.envelope.r&31))
            elif j.sus == SNESSusMode.SUS_WITH_EXP:
                adsrMode = 2
                env_bytes.append(0xa0|(j.envelope.r&31))
        else:
            adsrMode = 3
            env_bytes = [0, 0, j.gain&0xff]
        break
    if env_bytes is None:
        env_bytes = [255, 224]
    env_text = ", ".join(str(value) for value in env_bytes)
    if env_text in env_dups:
        f.write("ins"+str(i)+"E = "+env_dups[env_text]+"\n")
    else:
        f.write("ins"+str(i)+"E:\n.byte "+env_text+"\n")
        env_dups[env_text] = "ins"+str(i)+"E"
    adsrModes.append(adsrMode|(use_wave*32))

    a = filter(
        lambda x: (
            type(x) == InsFeatureMacro
        ), features
    )
    arp = [128,0xFF,0xFF]
    duty = [default_wave, 0xFF, 0xFF]
    vol = [0x7F,0xFF,0xFF]
    special = [0xFF,0xFF]
    gain = [0xFF,0xFF]
    noise = [0xFF,0xFF]
    panl = [0xFF,0xFF]
    panr = [0xFF,0xFF]
    macros = []
    for j in a:
        macros = j.macros
    hasRelTotal = [0,0,0,0,0,0,0,0]
    has_noise.append(0)
    for j in macros:
        kind = j.kind
        if kind == MacroCode.VOL:
            spd_v = max(1, min(255, int(j.speed)))
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
            spd_a = max(1, min(255, int(j.speed)))
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
            spd_d = max(1, min(255, int(j.speed)))
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
            spd_s = max(1, min(255, int(j.speed)))
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
        if kind == MacroCode.EX2:
            spd_g = max(1, min(255, int(j.speed)))
            gain = []
            loop = 0xff
            loop2 = 0
            hasRel = 0
            for k in j.data:
                if k == MacroItem.LOOP:
                    loop = loop2
                elif k == MacroItem.RELEASE:
                    gain.append(0xFF)
                    gain.append(loop)
                    relG.append(len(gain))
                    hasRel = 1
                else:
                    loop2 = len(gain)
                    gain.append(k & 0xFF)
            if hasRel == 0:
                relG.append(len(gain))
            hasRelTotal[7] = 1
            gain.append(0xFF)
            gain.append(loop)
        if kind == MacroCode.PAN_L:
            spd_pl = max(1, min(255, int(j.speed)))
            panl = []
            loop = 0xff
            loop2 = 0
            hasRel = 0
            for k in j.data:
                if k == MacroItem.LOOP:
                    loop = loop2
                elif k == MacroItem.RELEASE:
                    panl.append(0xFF)
                    panl.append(loop)
                    relPL.append(len(panl))
                    hasRel = 1
                else:
                    loop2 = len(panl)
                    panl.append(k&127)
            if hasRel == 0:
                relPL.append(len(panl))
            hasRelTotal[5] = 1
            panl.append(0xFF)
            panl.append(loop)
        if kind == MacroCode.PAN_R:
            spd_pr = max(1, min(255, int(j.speed)))
            panr = []
            loop = 0xff
            loop2 = 0
            hasRel = 0
            for k in j.data:
                if k == MacroItem.LOOP:
                    loop = loop2
                elif k == MacroItem.RELEASE:
                    panr.append(0xFF)
                    panr.append(loop)
                    relPR.append(len(panr))
                    hasRel = 1
                else:
                    loop2 = len(panr)
                    panr.append(k&127)
            if hasRel == 0:
                relPR.append(len(panr))
            hasRelTotal[6] = 1
            panr.append(0xFF)
            panr.append(loop)
        if kind == MacroCode.DUTY:
            spd_n = max(1, min(255, int(j.speed)))
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
    if hasRelTotal[5] == 0:
        relPL.append(0)
    if hasRelTotal[6] == 0:
        relPR.append(0)
    if hasRelTotal[7] == 0:
        relG.append(0)
    spdV.append(spd_v)
    spdA.append(spd_a)
    spdD.append(spd_d)
    spdS.append(spd_s)
    spdG.append(spd_g)
    spdPL.append(spd_pl)
    spdPR.append(spd_pr)
    spdN.append(spd_n)
    vol = str(vol)[1:-1]
    duty = str(duty)[1:-1]
    arp = str(arp)[1:-1]
    special = str(special)[1:-1]
    gain = str(gain)[1:-1]
    noise = str(noise)[1:-1]
    panl = str(panl)[1:-1]
    panr = str(panr)[1:-1]

    f.write(".if MACRO_ARP\n")
    arp_key = ("A", arp)
    if arp_key in dups:
        f.write("ins"+str(i)+"A = "+dups[arp_key]+"\n")
    else:
        f.write("ins"+str(i)+"A:\n")
        f.write(".byte "+arp+"\n")
        dups[arp_key] = "ins"+str(i)+"A"
    f.write(".endif\n")

    f.write(".if MACRO_WAVE\n")
    duty_key = ("D", duty)
    if duty_key in dups:
        f.write("ins"+str(i)+"D = "+dups[duty_key]+"\n")
    else:
        f.write("ins"+str(i)+"D:\n")
        f.write(".byte "+duty+"\n")
        dups[duty_key] = "ins"+str(i)+"D"
    f.write(".endif\n")

    f.write(".if MACRO_VOL\n")
    vol_key = ("V", vol)
    if vol_key in dups:
        f.write("ins"+str(i)+"V = "+dups[vol_key]+"\n")
    else:
        f.write("ins"+str(i)+"V:\n")
        f.write(".byte "+vol+"\n")
        dups[vol_key] = "ins"+str(i)+"V"
    f.write(".endif\n")

    f.write(".if MACRO_SPEC\n")
    special_key = ("S", special)
    if special_key in dups:
        f.write("ins"+str(i)+"S = "+dups[special_key]+"\n")
    else:
        f.write("ins"+str(i)+"S:\n")
        f.write(".byte "+special+"\n")
        dups[special_key] = "ins"+str(i)+"S"
    f.write(".endif\n")

    f.write(".if MACRO_NOISE\n")
    noise_key = ("N", noise)
    if noise_key in dups:
        f.write("ins"+str(i)+"N = "+dups[noise_key]+"\n")
    else:
        f.write("ins"+str(i)+"N:\n")
        f.write(".byte "+noise+"\n")
        dups[noise_key] = "ins"+str(i)+"N"
    f.write(".endif\n")

    f.write(".if MACRO_GAIN\n")
    gain_key = ("G", gain)
    if gain_key in dups:
        f.write("ins"+str(i)+"G = "+dups[gain_key]+"\n")
    else:
        f.write("ins"+str(i)+"G:\n")
        f.write(".byte "+gain+"\n")
        dups[gain_key] = "ins"+str(i)+"G"
    f.write(".endif\n")

    if pan_used:
        panl_key = ("PL", panl)
        if panl_key in dups:
            f.write("ins"+str(i)+"PL = "+dups[panl_key]+"\n")
        else:
            f.write("ins"+str(i)+"PL:\n")
            f.write(".byte "+panl+"\n")
            dups[panl_key] = "ins"+str(i)+"PL"

        panr_key = ("PR", panr)
        if panr_key in dups:
            f.write("ins"+str(i)+"PR = "+dups[panr_key]+"\n")
        else:
            f.write("ins"+str(i)+"PR:\n")
            f.write(".byte "+panr+"\n")
            dups[panr_key] = "ins"+str(i)+"PR"

relV = str(relV)[1:-1]
relD = str(relD)[1:-1]
relA = str(relA)[1:-1]
relS = str(relS)[1:-1]
relPL = str(relPL)[1:-1]
relPR = str(relPR)[1:-1]
relG = str(relG)[1:-1]
f.write(".if MACRO_ARP\n")
f.write("insArel:\n")
f.write(".byte "+relA+"\n")
f.write(".endif\n")
f.write(".if MACRO_WAVE\n")
f.write("insDrel:\n")
f.write(".byte "+relD+"\n")
f.write(".endif\n")
f.write(".if MACRO_VOL\n")
f.write("insVrel:\n")
f.write(".byte "+relV+"\n")
f.write(".endif\n")
f.write(".if MACRO_SPEC\n")
f.write("insSrel:\n")
f.write(".byte "+relS+"\n")
f.write(".endif\n")
f.write(".if MACRO_GAIN\n")
f.write("insGrel:\n")
f.write(".byte "+relG+"\n")
f.write(".endif\n")
if pan_used:
    f.write("insPLrel:\n")
    f.write(".byte "+relPL+"\n")
    f.write("insPRrel:\n")
    f.write(".byte "+relPR+"\n")

if macro_speed_used:
    f.write(".if MACRO_VOL\n")
    f.write("insVspd:\n.byte " + ", ".join(str(v) for v in spdV) + "\n")
    f.write(".endif\n")
    f.write(".if MACRO_ARP\n")
    f.write("insAspd:\n.byte " + ", ".join(str(v) for v in spdA) + "\n")
    f.write(".endif\n")
    f.write(".if MACRO_WAVE\n")
    f.write("insDspd:\n.byte " + ", ".join(str(v) for v in spdD) + "\n")
    f.write(".endif\n")
    f.write(".if MACRO_SPEC\n")
    f.write("insSspd:\n.byte " + ", ".join(str(v) for v in spdS) + "\n")
    f.write(".endif\n")
    f.write(".if MACRO_GAIN\n")
    f.write("insGspd:\n.byte " + ", ".join(str(v) for v in spdG) + "\n")
    f.write(".endif\n")
    if pan_used:
        f.write("insPLspd:\n.byte " + ", ".join(str(v) for v in spdPL) + "\n")
        f.write("insPRspd:\n.byte " + ", ".join(str(v) for v in spdPR) + "\n")
    f.write(".if MACRO_NOISE\n")
    f.write("insNspd:\n.byte " + ", ".join(str(v) for v in spdN) + "\n")
    f.write(".endif\n")

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

def build_sample_map(ins):
    """
    Turn a Furnace sample map into compact runs.

    The driver note numbering uses C-0 = 0; Furnace stores maps with
    C-(-5) = 0, so converter note n reads map entry n+60. Notes without
    a map entry fall back to the instrument's default sample.

    Each run is (sample, freq delta, last converter note) and occupies
    three bytes in the generated SPC instead of the old per-note pair of
    120-byte tables.
    """
    amiga = None
    for feature in ins.features:
        if type(feature) == InsFeatureAmiga:
            amiga = feature
            break
    if amiga is None:
        return [], 0

    default_sample = amiga.init_sample
    if default_sample < 0 or default_sample >= len(module.samples) or default_sample > 255:
        default_sample = 0
    if not amiga.use_note_map:
        return [], default_sample

    runs = []
    current = None
    for conv_note in range(96):
        furnace_note = conv_note + 60
        entry = amiga.sample_map[furnace_note]
        sample = entry.sample_index
        if sample < 0 or sample == 65535 or sample >= len(module.samples) or sample > 255:
            if current is not None:
                runs.append(current)
                current = None
            continue
        delta = int(entry.freq) - furnace_note
        delta = max(-128, min(127, delta))
        if (current is not None and current[2] == sample and
                current[3] == delta and current[1] == conv_note - 1):
            current = (current[0], conv_note, sample, delta)
        else:
            if current is not None:
                runs.append(current)
            current = (conv_note, conv_note, sample, delta)
    if current is not None:
        runs.append(current)
    return runs, default_sample


sample_map_dups = {}
for i in range(len(module.instruments)):
    runs, default_sample = build_sample_map(module.instruments[i])
    lines = ".byte "+str(len(runs))+", "+str(default_sample)+"\n"
    for start_note, end_note, sample, delta in runs:
        lines += ".byte "+str(start_note)+", "+str(end_note)+", "+str(sample)+", "+str(delta & 0xff)+"\n"
    if lines in sample_map_dups:
        f.write("ins"+str(i)+"SM = "+sample_map_dups[lines]+"\n")
    else:
        f.write("ins"+str(i)+"SM:\n"+lines)
        sample_map_dups[lines] = "ins"+str(i)+"SM"

f.write("insPCMIL:\n")
f.write(".lobytes ")
for i in range(len(module.instruments)):
    f.write("ins"+str(i)+"SM")
    if i == len(module.instruments)-1:
        f.write("\n")
    else:
        f.write(", ")
f.write("insPCMIH:\n")
f.write(".hibytes ")
for i in range(len(module.instruments)):
    f.write("ins"+str(i)+"SM")
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
f.write("sample_data_start:\n")
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
f.write("sample_data_end:\n")

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

f.write(".if WAVE_DEFAULT\n")
f.write("insWD:\n")
f.write(".byte " + ", ".join(str(w) for w in default_waves) + "\n")
f.write(".endif\n")

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

f.write(".if MACRO_NOISE\n")
f.write("insNhas:\n")
f.write(".byte ")
for i in range(len(has_noise)):
    f.write(str(has_noise[i]))
    if i == len(has_noise)-1:
        f.write("\n")
    else:
        f.write(", ")
f.write(".endif\n")


f.close()

tuning = module.meta.tuning
f = open("src/note_lo.bin","wb")
for i in range(98):
    freq = tuning * (2**(float(i-57)/12.0))
    f.write(bytearray([int(freq)&0xff]))
f.close()
f = open("src/note_hi.bin","wb")
for i in range(98):
    freq = tuning * (2**(float(i-57)/12.0))
    f.write(bytearray([(int(freq)>>8)&0xff]))
f.close()
