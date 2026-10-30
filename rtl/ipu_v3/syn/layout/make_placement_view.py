"""
KLayout placement view of IPU v3 (Nangate45 cells + OpenRAM score bank).

This is NOT a place-and-route result (OpenROAD is not available where this was made).
The script:
  1. reads the synthesized cell list per block (syn/out/nangate45_stat_hier.txt),
  2. places the OpenRAM macro from its GDS, at the size given by its LEF
     (openram45_256x512_1r1w: 1587.345 x 495.535 um),
  3. places every synthesized standard cell in legal rows of the Nangate45 site
     (0.19 x 1.40 um, alternate rows flipped) at a fixed utilization, in one column
     per RTL block, in a strip along the macro's top edge. The top edge carries the
     read port (dout1[511:0], clk1, csb1): the macro's read data arrives half a cycle
     late, so the blocks that capture it (ipu_pipe, ipu_psel, W buffer) sit right
     above the dout1 pins,
  4. writes a GDS and renders PNGs with KLayout.
There is no routing, clock tree or power grid (only the cells' own metal1 rails); the
din0 pins on the macro's bottom edge would be reached by routing around the macro.

Usage:
  python3 make_placement_view.py <nangate45 platform dir> <stat_hier.txt> <outdir> \
          <macro.gds> <macro.lef>
"""
import json
import math
import os
import random
import re
import sys

import klayout.db as db
import klayout.lay as lay

PLAT, STAT, OUT, MGDS, MLEF = sys.argv[1:6]
os.makedirs(OUT, exist_ok=True)

UTIL = 0.65                           # standard-cell row utilization
SITE_W, ROW_H = 0.19, 1.40
MARGIN = 20.0                         # um: die edge to core
HALO = 10.0                           # um: keep-out between macro and standard cells
COL_GAP = 4.0                         # um: between block columns

# blocks of ipu_top, left -> right (module name fragments; lane_ctl and cmp_shift exist in
# pipe and psel). The first three capture the macro's read data: over the dout1 pins.
BLOCKS = [
    ("ipu_psel", ["ipu_psel", "ipu_lane_ctl", "ipu_cmp_shift"]),
    ("ipu_pipe", ["ipu_pipe", "ipu_ingress", "ipu_accum", "ipu_min_tree",
                  "ipu_min_track", "ipu_lane_ctl", "ipu_cmp_shift"]),
    ("ipu_wr_eng + W buffer", ["ipu_wr_eng", "ipu_fifo$63e8"]),
    ("top glue", ["ipu_top"]),
    ("ipu_seq_fsm", ["ipu_seq_fsm"]),
    ("ipu_rd_eng", ["ipu_rd_eng"]),
    ("ipu_issue", ["ipu_issue", "ipu_fifo$fb0c"]),
    ("ipu_csr", ["ipu_csr"]),
]
COLORS = [0xc62828, 0x2e7d32, 0x1565c0, 0x5d4037, 0xef6c00, 0x6a1b9a, 0x9e9d24, 0x00838f]

# ---------------- macro LEF: size and pins
lef = open(MLEF).read()
mname = re.search(r"^MACRO (\S+)", lef, re.M).group(1)
mw, mh = map(float, re.search(r"SIZE ([\d.]+) BY ([\d.]+)", lef).groups())
pins = {}
for name, body in re.findall(r"PIN (\S+)\s+DIRECTION \w+ ;(.*?)END \1", lef, re.S):
    r = re.search(r"RECT\s+([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+)", body)
    if r:
        pins.setdefault(name.split("[")[0], []).append(tuple(map(float, r.groups())))
pin_span = {k: (min(p[0] for p in v), max(p[2] for p in v), min(p[1] for p in v), max(p[3] for p in v))
            for k, v in pins.items()}

# ---------------- standard-cell sizes from the LEF
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

area_of = lambda cl: sum(sizes[c][0] * sizes[c][1] * n for c, n in cl.items())
tot_area = sum(area_of(cl) for _, cl in block_cells)
tot_cells = sum(n for _, cl in block_cells for n in cl.values())

# ---------------- floorplan: macro at the bottom, logic strip above its top edge
def columns(nrows):
    """Column (x, width) per block for a strip of nrows rows; +4 um per column absorbs
    row-end quantization in narrow columns."""
    out, x = [], MARGIN
    for label, cl in block_cells:
        w = area_of(cl) / UTIL / (nrows * ROW_H) * 1.03 + 4.0
        w = math.ceil(w / SITE_W) * SITE_W
        out.append((x, w))
        x += w + COL_GAP
    return out, x - COL_GAP - MARGIN


nrows = int(math.ceil(tot_area / UTIL / (mw * ROW_H)))
while columns(nrows)[1] > mw:                            # fit the strip within the macro width
    nrows += 1
cols, _ = columns(nrows)
mx0, my0 = MARGIN, MARGIN
sy0 = my0 + mh + HALO                                    # strip bottom
strip_h = nrows * ROW_H
die_w, die_h = MARGIN + mw + MARGIN, sy0 + strip_h + MARGIN

lib = db.Layout()
lib.read(os.path.join(PLAT, "gds", "NangateOpenCellLibrary.gds"))
mlib = db.Layout()
mlib.read(MGDS)
ly = db.Layout()
ly.dbu = min(lib.dbu, mlib.dbu)
top = ly.create_cell("ipu_top_placement_view")
L_DIE = ly.layer(235, 5)
L_TEXT = ly.layer(241, 0)
L_BLK = [ly.layer(250 + i, 0) for i in range(len(BLOCKS))]
um = lambda v: int(round(v / ly.dbu))

mcell = ly.create_cell(mname)
mcell.copy_tree(mlib.cell(mname))                        # copy_tree rescales the dbu
top.insert(db.CellInstArray(mcell.cell_index(), db.Trans(um(mx0), um(my0))))
top.shapes(L_DIE).insert(db.Box(0, 0, um(die_w), um(die_h)))

cmap = {}
def cell_of(name):
    if name not in cmap:
        cmap[name] = ly.create_cell(name)
        cmap[name].copy_tree(lib.cell(name))
    return cmap[name]

rng = random.Random(7)
placed = 0
report = []
for bi, ((label, cells), (cx, cw)) in enumerate(zip(block_cells, cols)):
    inst = [c for c, n in cells.items() for _ in range(n)]
    rng.shuffle(inst)
    k, row = 0, 0
    while k < len(inst):
        if row >= nrows:
            raise SystemExit(f"{label}: ran out of rows")
        sel, used = [], 0.0
        while k < len(inst) and (not sel or used + sizes[inst[k]][0] <= cw * UTIL / 0.97):
            sel.append(inst[k]); used += sizes[inst[k]][0]; k += 1
        gap = (cw - used) / (len(sel) + 1)
        xx = 0.0
        y = sy0 + row * ROW_H
        flip = row % 2 == 1
        for c in sel:
            xx += gap
            xs = math.floor(xx / SITE_W) * SITE_W
            t = db.Trans(db.Trans.M0 if flip else db.Trans.R0, um(cx + xs), um(y + (ROW_H if flip else 0)))
            top.insert(db.CellInstArray(cell_of(c).cell_index(), t))
            xx = xs + sizes[c][0]
            placed += 1
        row += 1
    top.shapes(L_BLK[bi]).insert(db.Box(um(cx), um(sy0), um(cx + cw), um(sy0 + row * ROW_H)))
    report.append((label, len(inst), area_of(cells), cx, cw, row))

ly.write(os.path.join(OUT, "ipu_v3_placement_view.gds"))

mb = mcell.dbbox()
with open(os.path.join(OUT, "placement_report.txt"), "w") as f:
    f.write("IPU v3 placement view (not P&R)\n")
    f.write(f"die {die_w:.1f} x {die_h:.1f} um = {die_w * die_h / 1e6:.3f} mm^2\n")
    f.write(f"macro {mname}: LEF {mw} x {mh} um, GDS bbox {mb.width():.3f} x {mb.height():.3f} um\n")
    for k in ("din0", "dout1", "addr0", "addr1", "clk0", "clk1", "csb0", "csb1"):
        if k in pin_span:
            a = pin_span[k]
            f.write(f"  pins {k:5s} x {a[0]:7.1f}..{a[1]:7.1f}  y {a[2]:6.1f}..{a[3]:6.1f}  ({len(pins[k])})\n")
    f.write(f"logic strip {mw:.1f} x {strip_h:.1f} um above the macro (halo {HALO} um), {nrows} rows, "
            f"utilization target {UTIL}\n")
    f.write(f"standard cells placed {placed} / {tot_cells}, cell area {tot_area:.0f} um^2\n")
    for label, n, a, cx, cw, r in report:
        f.write(f"  {label:24s} {n:6d} cells {a:9.0f} um^2  column x {cx - mx0:7.1f}..{cx - mx0 + cw:7.1f}  {r} rows\n")
print(open(os.path.join(OUT, "placement_report.txt")).read())
json.dump({"die": [die_w, die_h], "macro": [mx0, my0, mw, mh], "strip": [mx0, sy0, mw, strip_h],
           "pins": {k: v for k, v in pin_span.items()},
           "blocks": [[lab, n, a, cx, cw] for lab, n, a, cx, cw, r in report]},
          open(os.path.join(OUT, "floorplan.json"), "w"))

# ---------------- render
view = lay.LayoutView()
view.set_config("background-color", "#ffffff")
view.set_config("grid-visible", "false")
view.load_layout(os.path.join(OUT, "ipu_v3_placement_view.gds"), True)
view.load_layer_props(os.path.join(PLAT, "FreePDK45.lyp"))
view.max_hier()


def add_layer(layer, dt, color, width=1, name=""):
    p = lay.LayerPropertiesNode()
    p.source = f"{layer}/{dt}@1"
    p.fill_color = color
    p.frame_color = color
    p.dither_pattern = 1                                 # hollow
    p.width = width
    p.name = name
    view.insert_layer(view.end_layers(), p)


add_layer(235, 5, 0x000000, width=2, name="die")
for i in range(len(BLOCKS)):
    add_layer(250 + i, 0, COLORS[i], width=3, name=BLOCKS[i][0])


def set_visible(overlay):
    it = view.begin_layers()
    while not it.at_end():
        node = it.current()
        lay_no = node.source.split("/")[0]
        if any(node.source.startswith(f"{250 + i}/") for i in range(len(BLOCKS))):
            node.visible = overlay
        elif lay_no in ("2", "3", "4", "5", "6"):        # wells / implants: hide for clarity
            node.visible = False
        it.next()
    view.set_config("text-visible", "false")


def shot(name, box, w, overlay):
    set_visible(overlay)
    b = db.DBox(*box)
    h = int(round(w * b.height() / b.width()))
    view.zoom_box(b)
    view.save_image_with_options(os.path.join(OUT, name), w, h, 0, 0, 0, b, False)


shot("ipu_v3_die.png", (-5, -5, die_w + 5, die_h + 5), 3000, True)
# macro read-port edge: dout1 pins, macro periphery below, standard cells above
ex = mx0 + 420.0
shot("ipu_v3_edge_zoom.png", (ex, my0 + mh - 45, ex + 100, sy0 + 25), 2400, False)
shot("ipu_v3_cells_zoom.png", (cols[1][0] + 40, sy0 + 20, cols[1][0] + 60, sy0 + 31.2), 2400, False)
ax, ay = mx0 + 450.0, my0 + 250.0
shot("ipu_v3_macro_zoom.png", (ax, ay, ax + 30, ay + 16.8), 2400, False)
print("rendered:", sorted(p for p in os.listdir(OUT) if p.endswith(".png")))
