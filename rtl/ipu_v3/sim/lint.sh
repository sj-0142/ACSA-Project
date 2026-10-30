#!/bin/bash
# Verilator lint of the full IPU (must be clean). The OpenRAM macro is replaced by the
# cycle-equivalent behavioural bank (IPU_SRAM_BEHAV): its model is not lint-clean code.
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
verilator --lint-only -Wall -DIPU_SRAM_BEHAV -Wno-DECLFILENAME -I"$ROOT/src" $(ls "$ROOT"/src/ipu_*.sv) --top-module ipu_top && echo "lint clean"
