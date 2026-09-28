# Pynab A/B boot script for RAUC's U-Boot backend, compiled to boot.scr.
# It lives on the read-only boot partition, so it must keep working for every
# future rootfs: everything slot specific is read from /boot of the chosen slot.
#
# RAUC owns BOOT_ORDER and BOOT_<slot>_LEFT. Each try decrements and saves the
# counter first, so a slot that hangs or fails its health check runs out of
# attempts; a slot whose kernel cannot even be loaded falls through at once.

test -n "${devtype}" || setenv devtype mmc
test -n "${devnum}" || setenv devnum 0
test -n "${pynab_ovl_addr_r}" || setenv pynab_ovl_addr_r ${pxefile_addr_r}

# pynab_target and pynab_dtb (see boot.env.in).
if load ${devtype} ${devnum}:1 ${scriptaddr} boot.env; then env import -t ${scriptaddr} ${filesize} pynab_target pynab_dtb; fi

# Only used if the stored environment is missing or corrupt: same as uboot.env.
test -n "${BOOT_ORDER}" || setenv BOOT_ORDER "A B"
test -n "${BOOT_A_LEFT}" || setenv BOOT_A_LEFT 3
test -n "${BOOT_B_LEFT}" || setenv BOOT_B_LEFT 0

# Hardware overlays, applied before Linux starts. A failed apply leaves the
# blob unusable, so reload the plain DTB: the system then boots without sound
# or ears, fails its health check and rolls back instead of not booting at all.
setenv pynab_apply 'if load ${devtype} ${devnum}:${pynab_part} ${pynab_ovl_addr_r} /boot/overlays/${pynab_ovl}.dtbo && fdt apply ${pynab_ovl_addr_r}; then echo "pynab: overlay ${pynab_ovl} applied"; else setenv pynab_ovl_ok 0; fi'
setenv pynab_overlays 'fdt addr ${fdt_addr_r}; fdt resize 0x10000; setenv pynab_ovl_ok 1; setenv pynab_ovl tagtagtag-sound; run pynab_apply; setenv pynab_ovl tagtagtag-ears; run pynab_apply; if test ${pynab_ovl_ok} = 0; then echo "pynab: overlay failed, using the plain DTB"; load ${devtype} ${devnum}:${pynab_part} ${fdt_addr_r} /boot/dtb/${pynab_dtb}; fi'

# The firmware fills /system/linux,revision only in its own DTB, and U-Boot's
# board fixups do not copy it; rpi_ws281x and /proc/cpuinfo need it.
setenv pynab_fixup 'fdt addr ${fdt_addr_r}; fdt resize 0x1000; if test -n "${board_revision}"; then fdt get value pynab_rev /system linux,revision || fdt mknode / system; fdt set /system linux,revision <${board_revision}>; fdt get value pynab_rev /system linux,revision; echo "pynab: board revision ${pynab_rev}"; fi'

# Kernel and DTB always come from the same root filesystem as userspace.
setenv pynab_boot 'setenv bootargs "root=/dev/mmcblk0p${pynab_part} rootfstype=ext4 rootwait ro fsck.mode=skip init=/usr/lib/pynab/boot-init rauc.slot=${pynab_slot} panic=10 quiet"; if load ${devtype} ${devnum}:${pynab_part} ${kernel_addr_r} /boot/kernel && load ${devtype} ${devnum}:${pynab_part} ${fdt_addr_r} /boot/dtb/${pynab_dtb}; then run pynab_overlays; run pynab_fixup; echo "pynab: booting slot ${pynab_slot}: ${bootargs}"; if test "${pynab_target}" = zero2-arm64; then booti ${kernel_addr_r} - ${fdt_addr_r}; else bootz ${kernel_addr_r} - ${fdt_addr_r}; fi; fi; echo "pynab: slot ${pynab_slot} did not boot"'

setenv pynab_try 'if test "${pynab_slot}" = A; then setenv pynab_part 2; setenv pynab_left ${BOOT_A_LEFT}; else setenv pynab_part 3; setenv pynab_left ${BOOT_B_LEFT}; fi; if test ${pynab_left} -gt 0; then setexpr pynab_left ${pynab_left} - 1; if test "${pynab_slot}" = A; then setenv BOOT_A_LEFT ${pynab_left}; else setenv BOOT_B_LEFT ${pynab_left}; fi; echo "pynab: trying slot ${pynab_slot}, ${pynab_left} attempts left after this one"; saveenv; run pynab_boot; else echo "pynab: slot ${pynab_slot} has no attempts left"; fi'

if test "${BOOT_ORDER}" = "B A" || test "${BOOT_ORDER}" = "B"; then
	setenv pynab_slot B; run pynab_try
	setenv pynab_slot A; run pynab_try
else
	setenv pynab_slot A; run pynab_try
	setenv pynab_slot B; run pynab_try
fi

# Nothing booted: give both slots their attempts back (same value as RAUC's
# boot-attempts) and start over rather than stopping at a prompt.
echo "pynab: no bootable slot, restoring boot attempts"
setenv BOOT_A_LEFT 3
setenv BOOT_B_LEFT 3
saveenv
reset
