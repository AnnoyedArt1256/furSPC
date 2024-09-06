; main.s
.global main, nmi_handler, irq_handler
.globalzp oam_used
.global chr_bin, chr_bin_size

; ppuclear.s
.global ppu_copy_oam, ppu_pack_oamhi, ppu_clear_oam
.global ppu_copy, ppu_clear_nt, ppu_vsync
.global OAM, OAMHI

; bg.s
.global load_bg_tiles, draw_bg

; blarggapu.s
.global spc_boot_apu
