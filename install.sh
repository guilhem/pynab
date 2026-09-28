#!/bin/sh
# The A/B layout cannot be installed by upgrading the historical live filesystem.
printf '%s\n' 'Pynab requires a fresh Raspberry Pi OS Lite + RAUC image. See README.md and docs/build.md; use the local web interface for subsequent signed updates.' >&2
exit 1
