"""
Tools to manipulate Furnace .fur files.

- :mod:`chipchune.furnace.module`: Tools to inspect and manipulate module files.
- :mod:`chipchune.furnace.instrument`: Tools to inspect and manipulate instrument data from within or without the module.
- :mod:`chipchune.furnace.sample`: Tools to inspect and manipulate sample data (might be merged with inst?)
- :mod:`chipchune.furnace.wavetable`: Tools to inspect and manipulate wavetable data
- :mod:`chipchune.furnace.enums`: Various constants that apply to Furnace.
- :mod:`chipchune.furnace.data_types`: Various data types that apply to Furnace.


### Example

    from chipchune.furnace.module import FurnaceModule

    module = FurnaceModule("tests/samples/furnace/skate_or_die.143.fur")

    pattern = module.get_pattern(0, 0, 0)

    print(pattern.as_clipboard())

    for row in pattern.data:
        print(row)
"""
