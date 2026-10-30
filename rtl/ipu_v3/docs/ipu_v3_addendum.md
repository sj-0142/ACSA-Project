# IPU v3 — OpenRAM score bank (addendum to the v2 addendum)

Status: RTL v3, 30 Oct 2026. v3 = v2 (end-of-prefill selection) with the score bank
replaced by the OpenRAM FreePDK45 macro `openram45_256x512_1r1w` (files in `macro/`,
as supplied). v1 (`rtl/ipu/`) and v2 (`rtl/ipu_v2/`) are unchanged.
Figure: [placement view](figures/ipu_v3_layout_annotated.svg).

## 1. The macro (from its .lib and .v)

| Property | Value |
|---|---|
| Organisation | 256 words × 512 bits = 16 KB; port 0 write-only (`clk0, csb0, addr0, din0`), port 1 read-only (`clk1, csb1, addr1, dout1`) |
| Area | 786,585.0 µm² (0.787 mm²) |
| Min clock period / pulse width | 2.154 ns (464 MHz) / 1.077 ns |
| Read data | `dout1` changes 0.581 ns after the **falling** edge of the cycle after the request; the model drives X from 1 time unit after the next rising edge |
| Write | inputs registered at the rising edge, array written at the falling edge |
| Setup / hold (all inputs) | 0.009 / 0.001 ns |
| Write mask | none (full 512-bit rows only) |
| Leakage | 0.134 mW |
| Not supplied | LEF, GDS (needed for real place-and-route) |

## 2. RTL changes for the macro

1. `ipu_sram_1r1w`: instantiates the macro (`csb = ~enable`, both clocks = `clk`);
   `IPU_SRAM_BEHAV` selects a cycle-equivalent behavioural array (lint only). A simulation
   check reports any same-cycle read and write of one row (undefined in the macro).
2. `ipu_psel`: registers the returned row (`rq`, 512 flops). Needed twice over: the read
   data arrives late in the cycle (falling edge + 0.581 ns leaves ~0.5 ns at 464 MHz, the
   compare needs ~0.67 ns), and with no write mask the final pass now writes the whole
   row back from `rq` with the demoted tiers set LOW (read-modify-write). The passes gain
   one pipeline stage (+1 cycle per pass).
3. Read data is valid for one cycle only, so:
   - `ipu_pipe`: while stage S1 is stalled holding a beat whose row was read, the row is
     read again every cycle (`hold`, `hold_row`), so it is present when S2 loads.
   - chase rule (`ipu_top` → `ipu_rd_eng`): a row whose read is still in flight is not
     yet free for the next head's prefetch, also after the sweep has ended
     (`sweep_active | v1`, `sweep_rows - v1`). Without this, the prefetch overwrote a row
     the stalled pipe was re-reading (found by the `main` scenario with the real model).
4. CSR VERSION upper half = 0x0004.

## 3. Verification

All tests run with the supplied OpenRAM Verilog model as the bank (not a stand-in):

| Test | Icarus 12 | Verilator 5.020 |
|---|---|---|
| ingress / datapath / tree (unit) | PASS | PASS |
| top edge / raw / main / big | PASS (15 / 176 / 468 / 554 bulk demotes) | PASS |
| same-cycle read+write check | never fires | never fires |
| Verilator -Wall lint (behavioural bank) | clean | |

The testbench uses T_MAX = 256, so 16 of the macro's 256 rows are exercised.

## 4. Synthesis: Nangate45 typical + OpenRAM (Yosys 0.33 + ABC)

| | v2 (FakeRAM45 model) | **v3 (OpenRAM)** |
|---|---|---|
| logic area (flattened) | 68,484 µm² | **72,508 µm²** (+512-flop row register, RMW mux) |
| flip-flops | 5,463 | **5,989** |
| SRAM macro | 135,961 µm² (single-port estimate) | **786,585 µm²** (real OpenRAM .lib) |
| **total** | 0.204 mm² | **0.859 mm²** (macro 91.6 %) |

Timing (pre-layout, no wire load):

| Path | Estimate | Limit at 2.154 ns |
|---|---|---|
| worst logic path (ABC, pipe) | 1.117 + 0.14 ≈ 1.26 ns | OK |
| macro read → capture flop (pipe S2, `rq`, W buffer) | falling edge + 0.581 + ≈0.3 mux + setup → ≈ T/2 + 0.92 ns | needs T ≥ 1.84 ns: OK |
| logic → macro inputs | ≈ 0.4 ns + 0.009 setup | OK |
| **macro minimum period** | **2.154 ns** | **sets fmax = 464 MHz** |

The macro, not the logic, now limits the clock (logic alone ≈ 790 MHz).

## 5. KLayout placement view (not place-and-route)

`syn/layout/make_placement_view.py` + `annotate.py` → `syn/results/ipu_v3_placement_view.gds`,
`docs/figures/`. Every synthesized cell (38,688) is placed legally on the Nangate45 site
grid (0.19 × 1.40 µm, flipped alternate rows), grouped by block at 65 % utilization, using
the real cell GDS; the macro is drawn as an outline at its .lib area with an assumed 1.6
aspect ratio. Die 1,343 × 741 µm (0.995 mm²). No routing, clock tree, power grid or pins:
label it "placement view (pre-P&R)". A real layout needs OpenROAD (not installable here)
and the macro's LEF/GDS.

Run:
```
LIB=<ORFS>/flow/platforms/nangate45/lib/NangateOpenCellLibrary_typical.lib syn/run_synth.sh
python3 syn/layout/make_placement_view.py <ORFS>/flow/platforms/nangate45 syn/out/nangate45_stat_hier.txt syn/out/layout
python3 syn/layout/annotate.py syn/out/layout          # needs: pip install klayout
```
