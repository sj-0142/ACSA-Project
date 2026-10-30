"""
KLayout placement view of IPU v3 (Nangate45 cells + OpenRAM score bank).

This is NOT a place-and-route result. OpenROAD is not available where this was made,
and the OpenRAM macro came without LEF/GDS. The script:
  1. reads the synthesized cell list per block (syn/out/nangate45_stat_hier.txt),
  2. draws the die, the OpenRAM macro as an outline (area from its .lib, aspect assumed),
  3. places every synthesized standard cell, block by block, in legal rows of the
     Nangate45 site (0.19 x 1.40 um, alternate rows flipped) at a fixed utilization,
     using the real cell layouts from NangateOpenCellLibrary.gds,
  4. writes a GDS and renders PNGs with KLayout.
There is no routing, clock tree or power grid (only the cells' own metal1 rails).

Usage:
  python3 make_placement_view.py <nangate45 platform dir> <stat_hier.txt> <outdir>
"""
import math
import os
import random
import re
import sys

import klayout.db as db
import klayout.lay as lay

PLAT, STAT, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(OUT, exist_ok=True)

MACRO_AREA = 786585.004575            # um^2, openram45_256x512_1r1w .lib
MACRO_ASPECT = 1.6                    # width / height: ASSUMED (no LEF provided)
UTIL = 0.65                           # standard-cell row utilization
SITE_W, ROW_H = 0.19, 1.40
MARGIN, GAP = 20.0, 20.0              # um: die edge to core, macro to logic

# blocks of ipu_top (module name fragments) -- lane_ctl and cmp_shift exist in pipe and psel
BLOCKS = [
    ("ipu_pipe (score datapath)", ["ipu_pipe", "ipu_ingress", "ipu_accum", "ipu_min_tree",
                                    "ipu_min_track", "ipu_lane_ctl", "ipu_cmp_shift"]),
    ("ipu_psel (prefill selection)", ["ipu_psel", "ipu_lane_ctl", "ipu_cmp_shift"]),
    ("ipu_wr_eng + W buffer", ["ipu_wr_eng", "ipu_fifo$63e8"]),
    ("ipu_rd_eng", ["ipu_rd_eng"]),
    ("ipu_seq_fsm", ["ipu_seq_fsm"]),
    ("ipu_csr", ["ipu_csr"]),
    ("ipu_issue", ["ipu_issue", "ipu_fifo$fb0c"]),
    ("top glue", ["ipu_top"]),
]
COLORS = [0x2e7d32, 0xc62828, 0x1565c0, 0x6a1b9a, 0xef6c00, 0x00838f, 0x9e9d24, 0x5d4037]

# ---------------- cell sizes from the LEF
sizes = {}
cur = None
for line in open(os.path.join(PLAT, "lef", "NangateOpenCellLibrary.macro.mod.lef")):
    t = line.split()
    if t[:1] == ["MACRO"]:
        cur = t[1]
    elif cur and t[:1] == ["SIZE"]:
        sizes[cur] = (float(t[1]), float(t[3]))

# ---------------- cells per module from the hierarchical stat
per_mod = {}
mod = None
for line in open(STAT):
    m = re.match(r"^=== (.*) ===", line)
    if m:
        mod = m.group(1)
        continue
    m = re.match(r"^\s+(\S+)\s+(\d+)\s*$", line)
    if mod and m and m.group(1) in sizes:
        per_mod.setdefault(mod, {})[m.group(1)] = int(m.group(2))


def mod_key(name):
    base = re.sub(r"^\$paramod(\$[0-9a-f]+)?\\", "", name).split("\\")[0]
    h = re.match(r"^\$paramod\$([0-9a-f]{4})", name)
    return base, (h.group(1) if h else "")


block_cells = []
for label, frags in BLOCKS:
    cells = {}
    for name, cnt in per_mod.items():
        base, h = mod_key(name)
        for f in frags:
            fb, _, fh = f.partition("$")
            if base == fb and (not fh or fh == h):
                for c, n in cnt.items():
                    cells[c] = cells.get(c, 0) + n
    block_cells.append((label, cells))

tot_area = sum(sizes[c][0] * sizes[c][1] * n for _, cl in block_cells for c, n in cl.items())
tot_cells = sum(n for _, cl in block_cells for n in cl.values())

# ---------------- floorplan
mh = math.sqrt(MACRO_AREA / MACRO_ASPECT)
mw = MACRO_AREA / mh
core_h = mh
nrows = int(core_h // ROW_H)
row_sites = int(math.ceil(1.03 * tot_area / UTIL / (nrows * ROW_H) / SITE_W))  # +3 %: block-end rows
logic_w = row_sites * SITE_W
lx0, ly0 = MARGIN + mw + GAP, MARGIN
die_w, die_h = lx0 + logic_w + MARGIN, MARGIN + mh + MARGIN

lib = db.Layout()
lib.read(os.path.join(PLAT, "gds", "NangateOpenCellLibrary.gds"))
ly = db.Layout()
ly.dbu = lib.dbu
top = ly.create_cell("ipu_top_placement_view")
L_DIE = ly.layer(235, 5)
L_MACRO = ly.layer(240, 0)
L_TEXT = ly.layer(241, 0)
L_BLK = [ly.layer(250 + i, 0) for i in range(len(BLOCKS))]

cmap = {}
def cell_of(name):
    if name not in cmap:
        cmap[name] = ly.create_cell(name)
        cmap[name].copy_tree(lib.cell(name))
    return cmap[name]

um = lambda v: int(round(v / ly.dbu))
top.shapes(L_DIE).insert(db.Box(0, 0, um(die_w), um(die_h)))
top.shapes(L_MACRO).insert(db.Box(um(MARGIN), um(MARGIN), um(MARGIN + mw), um(MARGIN + mh)))
for i, txt in enumerate(["openram45_256x512_1r1w  (16 KB, 1R1W)",
                         "outline only: area 786,585 um^2 from .lib, aspect 1.6 assumed (no LEF/GDS)"]):
    top.shapes(L_TEXT).insert(db.Text(txt, db.Trans(um(MARGIN + 30), um(MARGIN + mh / 2 - i * 40))))

# ---------------- row placement
rng = random.Random(7)
row = 0
placed = 0
report = []
for bi, (label, cells) in enumerate(block_cells):
    inst = [c for c, n in cells.items() for _ in range(n)]
    rng.shuffle(inst)
    area = sum(sizes[c][0] * sizes[c][1] for c in inst)
    r0 = row
    k = 0
    while k < len(inst):
        if row >= nrows:
            raise SystemExit("ran out of rows")
        # take cells until the row reaches the utilization target
        sel, used = [], 0
        while k < len(inst) and (used + sizes[inst[k]][0]) <= logic_w * UTIL + 1e-6 or (k < len(inst) and not sel):
            sel.append(inst[k]); used += sizes[inst[k]][0]; k += 1
        free = logic_w - used
        gap = free / (len(sel) + 1)
        x = 0.0
        y = ly0 + row * ROW_H
        flip = row % 2 == 1
        for c in sel:
            x += gap
            xs = round(x / SITE_W) * SITE_W                   # snap to the site grid
            t = db.Trans(db.Trans.M0 if flip else db.Trans.R0, um(lx0 + xs), um(y + (ROW_H if flip else 0)))
            top.insert(db.CellInstArray(cell_of(c).cell_index(), t))
            x += sizes[c][0]
            placed += 1
        row += 1
    y0, y1 = ly0 + r0 * ROW_H, ly0 + row * ROW_H
    top.shapes(L_BLK[bi]).insert(db.Box(um(lx0), um(y0), um(lx0 + logic_w), um(y1)))
    top.shapes(L_TEXT).insert(db.Text(label, db.Trans(um(lx0 + 2), um((y0 + y1) / 2))))
    report.append((label, len(inst), area, row - r0))

ly.write(os.path.join(OUT, "ipu_v3_placement_view.gds"))

with open(os.path.join(OUT, "placement_report.txt"), "w") as f:
    f.write("IPU v3 placement view (not P&R)\n")
    f.write(f"die {die_w:.1f} x {die_h:.1f} um = {die_w * die_h / 1e6:.3f} mm^2\n")
    f.write(f"macro outline {mw:.1f} x {mh:.1f} um (aspect assumed {MACRO_ASPECT})\n")
    f.write(f"logic region {logic_w:.1f} x {nrows * ROW_H:.1f} um, {nrows} rows, utilization target {UTIL}\n")
    f.write(f"standard cells placed {placed} / {tot_cells}, cell area {tot_area:.0f} um^2\n")
    for label, n, a, r in report:
        f.write(f"  {label:32s} {n:6d} cells {a:9.0f} um^2 {r:4d} rows\n")
print(open(os.path.join(OUT, "placement_report.txt")).read())

# ---------------- render
view = lay.LayoutView()
view.set_config("background-color", "#ffffff")
view.set_config("grid-visible", "false")
view.set_config("text-font", "3")
view.set_config("default-text-size", "6")
ci = view.load_layout(os.path.join(OUT, "ipu_v3_placement_view.gds"), True)
view.load_layer_props(os.path.join(PLAT, "FreePDK45.lyp"))
view.max_hier()


def add_layer(layer, dt, color, fill=True, dither=0, width=1, name=""):
    p = lay.LayerPropertiesNode()
    p.source = f"{layer}/{dt}@1"
    p.fill_color = color
    p.frame_color = color
    p.dither_pattern = dither if fill else 1
    p.width = width
    p.name = name
    view.insert_layer(view.end_layers(), p)


add_layer(235, 5, 0x000000, fill=False, width=2, name="die")
add_layer(240, 0, 0x1f5fbf, dither=2, width=2, name="OpenRAM macro")
add_layer(241, 0, 0x000000, fill=False, name="labels")
for i in range(len(BLOCKS)):
    add_layer(250 + i, 0, COLORS[i], dither=4, width=2, name=BLOCKS[i][0])


def set_visible(overlay, labels):
    it = view.begin_layers()
    while not it.at_end():
        node = it.current()
        src = node.source
        if src.startswith("250/") or any(src.startswith(f"{250 + i}/") for i in range(len(BLOCKS))):
            node.visible = overlay
        if src.startswith("241/"):
            node.visible = labels
        it.next()
    view.set_config("text-visible", "true" if labels else "false")


def shot(name, box, w, h, overlay, labels):
    set_visible(overlay, labels)
    view.zoom_box(db.DBox(*box))
    view.save_image_with_options(os.path.join(OUT, name), w, h, 0, 0, 0, db.DBox(*box), False)


view.set_config("default-text-size", "14")
shot("ipu_v3_die.png", (-5, -5, die_w + 5, die_h + 5), 2400, int(2400 * (die_h + 10) / (die_w + 10)), True, False)
shot("ipu_v3_die_cells.png", (-5, -5, die_w + 5, die_h + 5), 2400, int(2400 * (die_h + 10) / (die_w + 10)), False, False)
shot("ipu_v3_logic.png", (lx0 - 3, ly0 - 3, lx0 + logic_w + 3, ly0 + nrows * ROW_H + 3), 700, 2400, True, False)
cy = ly0 + 40.0
shot("ipu_v3_cells_zoom.png", (lx0 + 10, cy, lx0 + 30, cy + 11.2), 2400, 1344, False, False)
with open(os.path.join(OUT, "floorplan.json"), "w") as f:
    import json
    json.dump({"die": [die_w, die_h], "macro": [MARGIN, MARGIN, mw, mh],
               "logic": [lx0, ly0, logic_w, nrows * ROW_H],
               "blocks": [[lab, n, a, r] for lab, n, a, r in report]}, f)
print("rendered:", sorted(p for p in os.listdir(OUT) if p.endswith(".png")))
