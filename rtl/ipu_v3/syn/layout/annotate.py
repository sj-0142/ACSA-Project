"""Annotated slide (SVG) from the KLayout renders of make_placement_view.py."""
import base64
import json
import os
import sys

OUT = sys.argv[1]
fp = json.load(open(os.path.join(OUT, "floorplan.json")))
die_w, die_h = fp["die"]
mx, my, mw, mh = fp["macro"]
sx, sy, sw, sh = fp["strip"]
pins = fp["pins"]
blocks = fp["blocks"]
COLORS = ["#c62828", "#2e7d32", "#1565c0", "#5d4037", "#ef6c00", "#6a1b9a", "#9e9d24", "#00838f"]
b64 = lambda f: base64.b64encode(open(os.path.join(OUT, f), "rb").read()).decode()

W = 1720.0
H = W * (die_h + 10) / (die_w + 10)
X0, Y0 = 40, 110
px = lambda x: X0 + (x + 5) / (die_w + 10) * W
py = lambda y: Y0 + H - (y + 5) / (die_h + 10) * H            # layout y up, SVG y down
tot_cells = sum(b[1] for b in blocks)
TOT_H = int(Y0 + H + 545)

s = [f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="1800" height="{TOT_H}" font-family="Helvetica, Arial, sans-serif">',
     f'<rect width="1800" height="{TOT_H}" fill="#fff"/>',
     '<text x="40" y="44" font-size="26" font-weight="bold" fill="#111">IPU v3 — KLayout placement view: Nangate45 logic + OpenRAM 16 KB 1R1W macro (real GDS)</text>',
     f'<text x="40" y="72" font-size="15" fill="#444">Die {die_w:.0f} × {die_h:.0f} µm = {die_w * die_h / 1e6:.3f} mm² · macro {mw:.1f} × {mh:.1f} µm from its LEF/GDS · {tot_cells:,} standard cells in a {sw:.0f} × {sh:.0f} µm strip (65 % rows) · not routed</text>',
     f'<image x="{X0}" y="{Y0}" width="{W}" height="{H}" xlink:href="data:image/png;base64,{b64("ipu_v3_die.png")}"/>']

# block labels above the strip
for i, (lab, n, a, cx, cw) in enumerate(blocks):
    xm = px(cx + cw / 2)
    short = lab if cw > 120 else lab.replace("ipu_", "")
    s.append(f'<text x="{xm}" y="{py(sy + sh) - 8}" font-size="12.5" font-weight="bold" fill="{COLORS[i]}" text-anchor="middle">{short}</text>')

# macro annotations
d1, d0 = pins["dout1"], pins["din0"]
s.append(f'<rect x="{px(mx + d1[0])}" y="{py(my + mh) - 3}" width="{px(mx + d1[1]) - px(mx + d1[0])}" height="6" fill="#ff9800"/>')
s.append(f'<rect x="{px(mx + d0[0])}" y="{py(my) - 3}" width="{px(mx + d0[1]) - px(mx + d0[0])}" height="6" fill="#ff9800"/>')
def label(x, y, text, anchor="start", size=13, color="#b35c00"):
    w = len(text) * size * 0.56
    x0 = x if anchor == "start" else x - w / 2
    s.append(f'<rect x="{x0 - 4}" y="{y - size}" width="{w + 8}" height="{size + 7}" fill="#fff" opacity="0.92"/>')
    s.append(f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" font-weight="bold" text-anchor="{anchor}">{text}</text>')


label(px(mx + d1[1]) + 70, py(my + mh) + 22, "← dout1[511:0] read port (+ clk1, csb1): top edge")
label(px(mx + 850), py(my) - 12, "din0[511:0] write port: bottom edge, 2.86 µm pitch over the full width", "middle")
s.append(f'<text x="{px(mx + 400)}" y="{py(my + mh / 2) + 4}" font-size="22" font-weight="bold" fill="#fff" text-anchor="middle" stroke="#000" stroke-width="0.6">bit-cell array + decoders</text>')
s.append(f'<text x="{px(mx + 400)}" y="{py(my + mh / 2) + 30}" font-size="15" fill="#fff" text-anchor="middle" stroke="#000" stroke-width="0.4">256 rows × 512 columns, two ports</text>')
s.append(f'<text x="{px(mx + 1190)}" y="{py(my + mh / 2) - 6}" font-size="20" font-weight="bold" fill="#4a148c" text-anchor="middle">no transistors here:</text>')
s.append(f'<text x="{px(mx + 1190)}" y="{py(my + mh / 2) + 18}" font-size="15" fill="#4a148c" text-anchor="middle">metal3/metal4 wiring fanning din0 out along the bottom edge</text>')
s.append(f'<text x="{px(mx + 1190)}" y="{py(my + mh / 2) + 40}" font-size="15" fill="#4a148c" text-anchor="middle">(about half of the 0.787 mm² macro)</text>')

# insets
iy = Y0 + H + 30
insets = [("ipu_v3_edge_zoom.png", "Macro read edge (100 µm wide)", "cells above · 10 µm halo · macro periphery · array", 500, 400),
          ("ipu_v3_cells_zoom.png", "Standard cells, 20 × 11 µm (ipu_pipe)", "real Nangate45 layouts, flipped rows", 520, 291),
          ("ipu_v3_macro_zoom.png", "OpenRAM bit cells, 30 × 17 µm", "the macro's real GDS (dual-port cells)", 520, 291)]
x = 40
for f, t1, t2, w, h in insets:
    s.append(f'<text x="{x}" y="{iy}" font-size="15" font-weight="bold" fill="#111">{t1}</text>')
    s.append(f'<image x="{x}" y="{iy + 8}" width="{w}" height="{h}" xlink:href="data:image/png;base64,{b64(f)}"/>')
    s.append(f'<rect x="{x}" y="{iy + 8}" width="{w}" height="{h}" fill="none" stroke="#333"/>')
    s.append(f'<text x="{x}" y="{iy + h + 26}" font-size="12.5" fill="#444">{t2}</text>')
    x += w + 40

cy = iy + 8 + 291 + 50
s += [f'<rect x="580" y="{cy}" width="1180" height="140" rx="8" fill="#fff8e1" stroke="#c99a00"/>',
      f'<text x="598" y="{cy + 26}" font-size="15" font-weight="bold" fill="#6b4e00">What this picture is — and is not</text>',
      f'<text x="598" y="{cy + 50}" font-size="13" fill="#4a3a00">Is: the OpenRAM macro from its own GDS at its LEF size; every synthesized cell placed legally on the 0.19 × 1.40 µm site grid,</text>',
      f'<text x="598" y="{cy + 68}" font-size="13" fill="#4a3a00">one column per RTL block, in a strip over the read port (the half-cycle read data path).</text>',
      f'<text x="598" y="{cy + 92}" font-size="13" fill="#4a3a00">Is not: OpenROAD place-and-route. No timing-driven placement, routing, clock tree, power grid or I/O pins; no DRC/LVS.</text>',
      f'<text x="598" y="{cy + 110}" font-size="13" fill="#4a3a00">Label it "placement view (pre-P&amp;R)". Script: rtl/ipu_v3/syn/layout/make_placement_view.py.</text>',
      '</svg>']
open(os.path.join(OUT, "ipu_v3_layout_annotated.svg"), "w").write("\n".join(s))
print("written", os.path.join(OUT, "ipu_v3_layout_annotated.svg"))
