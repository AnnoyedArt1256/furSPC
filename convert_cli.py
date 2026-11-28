#!/usr/bin/env python3
"""Command-line driver for furSPC.

The low-level converter in convert_to_asm.py generates one song's assembly.
This driver handles input expansion, ID666 metadata, compilation/linking, and
the output filename.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import math
from pathlib import Path

from chipchune.furnace.module import FurnaceModule

ROOT = Path(__file__).resolve().parent
LOW_LEVEL = ROOT / "convert_to_asm.py"


def _tool(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    candidates = []
    cc65_bin = os.environ.get("CC65_BIN")
    if cc65_bin:
        candidates.append(Path(cc65_bin) / name)
        candidates.append(Path(cc65_bin) / f"{name}.exe")
    candidates.extend([
        ROOT / "cc65" / "bin" / name,
        Path("D:/opt/cc65/bin") / name,
        Path("D:/opt/cc65/bin") / f"{name}.exe",
    ])
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    raise RuntimeError(
        f"could not find {name}; install cc65 and put its bin directory on PATH"
    )


def _expand_inputs(raw_inputs: list[str], recursive: bool) -> list[Path]:
    inputs: list[Path] = []
    for raw in raw_inputs:
        path = Path(raw).expanduser()
        if path.is_dir():
            iterator = path.rglob("*") if recursive else path.iterdir()
            found = sorted(
                (entry for entry in iterator
                 if entry.is_file() and entry.suffix.lower() == ".fur"),
                key=lambda entry: str(entry).lower(),
            )
            if not found:
                raise ValueError(f"no .fur files found in {path}")
            inputs.extend(found)
        elif path.is_file():
            inputs.append(path)
        else:
            raise FileNotFoundError(path)
    return inputs


def _output_path(input_path: Path, output_arg: str | None, multiple: bool) -> Path:
    if output_arg is None:
        return input_path.with_suffix(".spc")

    output = Path(output_arg).expanduser()
    if multiple:
        if output.exists() and not output.is_dir():
            raise ValueError(
                "with multiple input files, --output must name a directory"
            )
        return output / f"{input_path.stem}.spc"

    if output.is_dir() or output_arg.endswith(("/", os.sep)):
        return output / f"{input_path.stem}.spc"
    return output


def _module_tags(module: FurnaceModule, input_path: Path) -> tuple[str, str, str]:
    meta = module.meta
    subsong = module.subsongs[0]
    title = meta.name or subsong.name or input_path.stem
    album = meta.album or ""
    artist = meta.author or "AArt1256"
    return title, album, artist


def _format_duration(seconds: float) -> str:
    # ID666 stores three ASCII digits. Round up so a fractional final row is
    # not cut off, and leave the fade separate.
    whole = max(0, min(999, int(math.ceil(seconds))))
    return f"{whole:03d}"


def _pattern_rows(module: FurnaceModule, order_index: int) -> int:
    subsong = module.subsongs[0]
    rows = 0
    for channel, order in subsong.order.items():
        if order_index >= len(order):
            continue
        pattern = module.get_pattern(channel, order[order_index], 0)
        if pattern is not None:
            rows = max(rows, len(pattern.data))
    if rows == 0:
        rows = subsong.pattern_length
    return max(1, rows)


def _derive_playback_time(module: FurnaceModule) -> str:
    """Return one-loop time, or the end of the stopping pattern.

    Furnace loops automatically at the end of the order list (and can also
    loop through 0Bxx). In the normal case that means one pass through all
    orders. A 0xFFxx stop effect instead ends at the end of the pattern in
    which it appears, matching Furnace's stop handling.
    """
    subsong = module.subsongs[0]
    orders = subsong.order
    if not orders:
        return "000"

    order_len = max(len(order) for order in orders.values())
    if order_len == 0:
        return "000"

    speeds = [max(1, int(speed)) for speed in subsong.speed_pattern] or [6]
    clock = float(subsong.timing.clock_speed or 60.0)
    if clock <= 0:
        clock = 60.0

    def rows_at(order_index: int) -> int:
        return _pattern_rows(module, order_index)

    def effects_at(order_index: int, row_index: int):
        for channel, order in orders.items():
            if order_index >= len(order):
                continue
            pattern = module.get_pattern(channel, order[order_index], 0)
            if pattern is None or row_index >= len(pattern.data):
                continue
            for command, value in pattern.data[row_index].effects:
                if command != 0xFFFF:
                    yield command, value

    visited: set[tuple[int, int]] = set()
    seconds = 0.0
    row_number = 0
    order_index = 0
    row_index = 0
    stopping = False
    # Generous guard against malformed order/effect data.
    for _ in range(1000000):
        if stopping:
            rows = rows_at(order_index)
            seconds += speeds[row_number % len(speeds)] / clock
            row_number += 1
            row_index += 1
            if row_index >= rows:
                break
            continue

        if (order_index, row_index) in visited:
            break
        visited.add((order_index, row_index))

        rows = rows_at(order_index)
        if row_index >= rows:
            row_index = 0
            order_index += 1
            if order_index >= order_len:
                order_index = 0
            continue

        seconds += speeds[row_number % len(speeds)] / clock
        row_number += 1

        jump_order = None
        jump_row = 0
        for command, value in effects_at(order_index, row_index):
            if value == 0xFFFF:
                value = 0
            value &= 0xFF
            if command == 0xFF:
                stopping = True
            elif command == 0x0B:
                if 0 <= value < order_len:
                    jump_order = value
                    jump_row = 0
            elif command == 0x0D:
                if order_index + 1 < order_len:
                    jump_order = order_index + 1
                    jump_row = min(value, rows_at(jump_order) - 1)
            elif command == 0x09 or command == 0x0F:
                # Ignore tempo/speed changes for the default estimate.
                pass

        if stopping:
            row_index += 1
            if row_index >= rows:
                break
            continue

        if jump_order is not None:
            order_index = jump_order
            row_index = jump_row
        else:
            row_index += 1
            if row_index >= rows:
                row_index = 0
                order_index += 1
                if order_index >= order_len:
                    order_index = 0

    return _format_duration(seconds)


def _normalize_time(value: str | None) -> str | None:
    if value is None:
        return None

    value = str(value).strip()
    if not value:
        raise ValueError("playback time cannot be empty")

    if re.fullmatch(r"\d+", value):
        seconds = int(value)
    elif ":" in value:
        parts = value.split(":")
        if len(parts) not in (2, 3) or any(not part.isdigit() for part in parts):
            raise ValueError(f"invalid playback time: {value!r}")
        numbers = [int(part) for part in parts]
        if len(numbers) == 2:
            seconds = numbers[0] * 60 + numbers[1]
        else:
            seconds = numbers[0] * 3600 + numbers[1] * 60 + numbers[2]
    else:
        raise ValueError(f"invalid playback time: {value!r}")

    if seconds < 0 or seconds > 999:
        raise ValueError("playback time must fit in the SPC ID666 field (0-999 seconds)")
    return f"{seconds:03d}"


def _put_ascii(data: bytearray, offset: int, value: str, length: int) -> None:
    encoded = value.encode("ascii", "replace")[:length]
    data[offset:offset + length] = encoded + b"\0" * (length - len(encoded))


def _patch_id666(
    output: Path,
    title: str,
    album: str,
    artist: str,
    playback_time: str,
    fade_time: str = "5000",
) -> None:
    data = bytearray(output.read_bytes())
    if not data.startswith(b"SNES-SPC700"):
        raise ValueError(f"{output} is not an SPC file")

    dumper = "furSPC by AArt1256"
    if len(dumper.encode("ascii", "replace")) > 16:
        dumper = "furSPC"
    _put_ascii(data, 0x2E, title, 32)
    _put_ascii(data, 0x4E, album, 32)
    _put_ascii(data, 0x6E, dumper, 16)
    _put_ascii(data, 0xB1, artist, 32)
    _put_ascii(data, 0xA9, playback_time, 3)
    _put_ascii(data, 0xAC, fade_time, 5)
    output.write_bytes(data)


def _run(command: list[str], env: dict[str, str] | None = None) -> None:
    result = subprocess.run(command, cwd=ROOT, env=env)
    if result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, command)


def _run(command: list[str], env: dict[str, str] | None = None, capture: bool = False) -> None:
    result = subprocess.run(
        command, cwd=ROOT, env=env,
        capture_output=capture, text=capture,
    )
    output = ""
    if capture:
        output = (result.stdout or "") + (result.stderr or "")
        if output:
            print(output, end="")
    if result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, command, output)


def _object_segment_size(image_obj: Path) -> int | None:
    try:
        od65 = _tool("od65")
        result = subprocess.run(
            [od65, "--dump-segsize", str(image_obj)],
            cwd=ROOT, capture_output=True, text=True,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                match = re.match(r"\s*SPCIMAGE:\s+(\d+)", line)
                if match:
                    return int(match.group(1))
    except Exception:
        pass
    return None


SPC_IMAGE_START = 0x200
SPC_RAM_END = 0x10000
SPC_FILE_SIZE = 0x10200  # 66,048 bytes: header + RAM + DSP regs + padding
SPC_HEADER_SIZE = 0x100
SPC_DSP_SIZE = 0x80
SPC_PADDING_SIZE = 0x80
# The driver places the echo buffer at (0xF8 - delay*8) pages, so its
# highest start page is 0xF8 regardless of the delay.
ECHO_START_PAGE = 0xF8


def _echo_settings() -> tuple[int, int, int]:
    """Return (delay, start_page, size_bytes) for the generated song.

    All zeros when echo is disabled or the module does not use it.
    """
    song = ROOT / "src" / "song.s"
    try:
        lines = song.read_text().splitlines()
        for index, line in enumerate(lines):
            if line.startswith("echo_info:"):
                values = next(
                    item for item in lines[index + 1:]
                    if item.startswith(".byte ")
                )
                fields = [int(value) for value in values[6:].split(",")]
                if len(fields) >= 5 and not (fields[0] & 32):
                    delay = max(0, min(15, fields[4]))
                    if delay:
                        page = (fields[13] if len(fields) > 13
                                else ECHO_START_PAGE - delay * 8)
                        return delay, page & 0xFF, delay * 0x800
                return 0, 0, 0
    except Exception:
        pass
    return 0, 0, 0


class RamFitError(ValueError):
    """The generated image would overlap the echo buffer or RAM end."""


def _check_ram_fit(image_obj: Path) -> None:
    """Fail before linking if the image would run into the echo buffer."""
    image_size = _object_segment_size(image_obj)
    if image_size is None:
        return

    image_end = SPC_IMAGE_START + image_size
    delay, page, echo_size = _echo_settings()
    echo_start = (page << 8) if echo_size else SPC_RAM_END
    if image_end <= echo_start:
        return

    over = image_end - echo_start
    max_image_size = echo_start - SPC_IMAGE_START
    if echo_size:
        # Largest delay whose buffer still starts at or above the image end.
        highest_page = (image_end + 0xFF) >> 8
        max_delay = max(0, (ECHO_START_PAGE - highest_page) // 8)
        if max_delay:
            advice = f"Set the echo delay to at most {max_delay} in Furnace and reconvert."
        else:
            advice = "Disable echo or shorten/remove samples in Furnace and reconvert."
        location = (
            f"but the echo buffer (delay {delay}, {echo_size:,} bytes) starts at "
            f"${echo_start:04X}"
        )
    else:
        advice = "Shorten or remove samples in Furnace and reconvert."
        location = "past the end of APU RAM ($10000 / 65,536)"
    raise RamFitError(
        f"SPC data does not fit in APU RAM: the image ends at ${image_end:04X}, "
        f"{location}; {over:,} bytes over. The maximum image size is "
        f"${max_image_size:04X} ({max_image_size:,} bytes). {advice}"
    )


def _listing_sizes() -> tuple[int | None, int | None, int | None]:
    listing = ROOT / "obj" / "snes" / "spcimage.lst"
    try:
        labels: dict[str, int] = {}
        wanted = {"song_data_start", "sample_data_start", "sample_data_end"}
        for line in listing.read_text(errors="replace").splitlines():
            match = re.match(r"\s*([0-9A-Fa-f]+)r?\s+", line)
            if not match:
                continue
            for name in wanted:
                if f"{name}:" in line:
                    labels[name] = int(match.group(1), 16)
        if len(labels) == len(wanted):
            # SPCIMAGE starts at $0200 in spc.cfg.
            start = labels["song_data_start"] - 0x200
            sample_start = labels["sample_data_start"]
            sample_end = labels["sample_data_end"]
            return start, sample_start - labels["song_data_start"], sample_end - sample_start
    except Exception:
        pass
    return None, None, None


def _print_size_report(input_path: Path, image_obj: Path, failed: bool = False) -> None:
    image_size = _object_segment_size(image_obj)
    delay, page, echo_size = _echo_settings()
    driver_size, song_size, sample_size = _listing_sizes()

    if sample_size is None:
        try:
            module = FurnaceModule(str(input_path))
            sample_size = sum(len(sample.data) for sample in module.samples)
        except Exception:
            sample_size = None

    if image_size is None:
        if failed:
            print("conversion failed: the SPC data does not fit in SPC RAM.", file=sys.stderr)
        return

    image_end = SPC_IMAGE_START + image_size
    echo_start = (page << 8) if echo_size else SPC_RAM_END
    stream = sys.stderr if failed else sys.stdout

    if failed:
        print("conversion failed: too much data to fit in the SPC RAM.", file=stream)
    print(f"SPC size breakdown (file max {SPC_FILE_SIZE:,} bytes):", file=stream)
    print(f"  file header:        {SPC_HEADER_SIZE:,} bytes", file=stream)
    print(f"  DSP registers:      {SPC_DSP_SIZE:,} bytes", file=stream)
    print(f"  padding:            {SPC_PADDING_SIZE:,} bytes", file=stream)
    print(f"  APU RAM:            {SPC_RAM_END:,} bytes", file=stream)
    print(f"    zero page/stack:   {SPC_IMAGE_START:,} bytes", file=stream)
    if driver_size is not None:
        print(f"    driver:            {driver_size:,} bytes", file=stream)
    if song_size is not None:
        print(f"    song/pattern data: {song_size:,} bytes", file=stream)
    sample_text = f"{sample_size:,}" if sample_size is not None else "unknown"
    print(f"    sample data:       {sample_text} bytes", file=stream)
    print(
        f"    image total:       {image_size:,} bytes "
        f"(${SPC_IMAGE_START:04X}-${image_end - 1:04X}, incl. alignment)",
        file=stream,
    )
    if echo_size:
        print(
            f"    echo buffer:       {echo_size:,} bytes at ${echo_start:04X}"
            f" (delay {delay})",
            file=stream,
        )
        reserved = SPC_RAM_END - (echo_start + echo_size)
        print(
            f"    reserved top:      {reserved:,} bytes "
            f"(${echo_start + echo_size:04X}-${SPC_RAM_END - 1:04X})",
            file=stream,
        )
    else:
        print("    echo buffer:       disabled", file=stream)
    max_image_size = echo_start - SPC_IMAGE_START
    print(
        f"    maximum image:     ${max_image_size:04X} ({max_image_size:,} bytes)",
        file=stream,
    )
    if image_end > echo_start:
        print(
            f"    result:            {image_end - echo_start:,} bytes over",
            file=stream,
        )
    else:
        print(
            f"    result:            {echo_start - image_end:,} bytes free",
            file=stream,
        )


def _build(output: Path) -> None:
    ca65 = _tool("ca65")
    ld65 = _tool("ld65")
    objdir = ROOT / "obj" / "snes"
    objdir.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)

    header_obj = objdir / "spcheader.o"
    image_obj = objdir / "spcimage.o"
    _run([ca65, "-g", str(ROOT / "src" / "spcheader.s"), "-o", str(header_obj)])
    _run([
        ca65, "-g",
        "-l", str(objdir / "spcimage.lst"),
        str(ROOT / "src" / "spcimage.s"),
        "-o", str(image_obj),
    ], capture=True)
    _check_ram_fit(image_obj)
    _run([
        ld65,
        "-o", str(output),
        "-m", str(ROOT / "spcmap.txt"),
        "-C", str(ROOT / "spc.cfg"),
        str(header_obj),
        str(image_obj),
    ], capture=True)


def _convert_one(
    input_path: Path,
    output: Path,
    title: str,
    album: str,
    artist: str,
    playback_time: str,
) -> None:
    environment = os.environ.copy()
    environment["FURSPC_LOWLEVEL"] = "1"
    _run([
        sys.executable,
        str(LOW_LEVEL),
        str(input_path),
    ], env=environment)
    _build(output)
    _patch_id666(output, title, album, artist, playback_time)
    _print_size_report(input_path, ROOT / "obj" / "snes" / "spcimage.o")
    print(f"compiled {output}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert Furnace .fur modules to SNES .spc files.",
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        help="one or more .fur files, or directories containing .fur files",
    )
    parser.add_argument(
        "-o", "--output",
        help="output .spc file, or output directory when converting multiple files",
    )
    parser.add_argument("--title", help="ID666 track title (default: from .fur)")
    parser.add_argument("--album", help="ID666 album/game title (default: from .fur)")
    parser.add_argument("--artist", help="ID666 artist (default: from .fur)")
    parser.add_argument(
        "-t", "--time", "--playtime", "--playback-time", dest="time",
        help="ID666 playback time in seconds or MM:SS (default: derived from .fur)",
    )
    parser.add_argument(
        "-r", "--recursive",
        action="store_true",
        help="recurse into subdirectories when an input is a directory",
    )
    args = parser.parse_args(argv)

    try:
        inputs = _expand_inputs(args.inputs, args.recursive)
        if not inputs:
            raise ValueError("no .fur files to convert")
        multiple = len(inputs) > 1 or any(Path(raw).is_dir() for raw in args.inputs)
        custom_time = _normalize_time(args.time)
    except (OSError, ValueError) as error:
        parser.error(str(error))

    failed = 0
    for input_path in inputs:
        input_path = input_path.resolve()
        try:
            module = FurnaceModule(str(input_path))
            if not module.instruments:
                raise ValueError(
                    "no instruments found; add at least one instrument in Furnace"
                )
            if args.title is None or args.album is None or args.artist is None:
                default_title, default_album, default_artist = _module_tags(module, input_path)
            else:
                default_title = default_album = default_artist = ""
            title = args.title if args.title is not None else default_title
            album = args.album if args.album is not None else default_album
            artist = args.artist if args.artist is not None else default_artist
            playback_time = custom_time if custom_time is not None else _derive_playback_time(module)
            output = _output_path(input_path, args.output, multiple).resolve()
            _convert_one(input_path, output, title, album, artist, playback_time)
        except Exception as error:
            failed += 1
            print(f"error: {input_path}: {error}", file=sys.stderr)
            output = getattr(error, "output", "") or ""
            if isinstance(error, RamFitError):
                _print_size_report(
                    input_path,
                    ROOT / "obj" / "snes" / "spcimage.o",
                    failed=True,
                )
            elif isinstance(error, subprocess.CalledProcessError) and (
                "Range error" in output or "not in [0..65535]" in output
            ):
                _print_size_report(
                    input_path,
                    ROOT / "obj" / "snes" / "spcimage.o",
                    failed=True,
                )

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
