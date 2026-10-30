"""Annotated slide (SVG + PNG) from the KLayout renders of make_placement_view.py."""
import base64, json, os, sys
OUT = sys.argv[1]
fp = json.load(open(os.path.join(OUT, "floorplan.json")))
die_w, die_h = fp["die"]
mx, my, mw, mh = fp["macro"]
lx, lyy, lw, lh = fp["logic"]
COLORS = ["#2e7d32", "#c62828", "#1565c0", "#6a1b9a", "#ef6c00", "#00838f", "#9e9d24", "#5d4037"]
b64 = lambda f: base64.b64encode(open(os.path.join(OUT, f), "rb").read()).decode()
W = 1300.0
H = W * (die_h + 10) / (die_w + 10)
X0, Y0 = 40, 100
px = lambda x: X0 + (x + 5) / (die_w + 10) * W
py = lambda y: Y0 + H - (y + 5) / (die_h + 10) * H          # layout y up, SVG y down
blocks = fp["blocks"]
tot_cells = sum(b[1] for b in blocks); tot_area = sum(b[2] for b in blocks)

s = [f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="1800" height="{int(Y0 + H + 190)}" font-family="Helvetica, Arial, sans-serif">',
     f'<rect width="1800" height="{int(Y0 + H + 190)}" fill="#fff"/>',
     '<text x="40" y="44" font-size="26" font-weight="bold" fill="#111">IPU v3 — KLayout placement view (Nangate45 + OpenRAM 16 KB 1R1W)</text>',
     f'<text x="40" y="72" font-size="15" fill="#444">Die {die_w:.0f} × {die_h:.0f} µm = {die_w*die_h/1e6:.3f} mm² · synthesized area 0.859 mm² (macro 0.787 + logic 0.071) · {tot_cells:,} standard cells at 65 % row utilization</text>',
     f'<image x="{X0}" y="{Y0}" width="{W}" height="{H}" xlink:href="data:image/png;base64,{b64("ipu_v3_die.png")}"/>']
# macro labels
cx, cy = px(mx + mw / 2), py(my + mh / 2)
s += [f'<text x="{cx}" y="{cy - 30}" font-size="30" font-weight="bold" fill="#0d3c84" text-anchor="middle">openram45_256x512_1r1w</text>',
      f'<text x="{cx}" y="{cy + 8}" font-size="20" fill="#0d3c84" text-anchor="middle">score bank · 256 words × 512 bits = 16 KB · 1 write port + 1 read port</text>',
      f'<text x="{cx}" y="{cy + 40}" font-size="20" fill="#0d3c84" text-anchor="middle">786,585 µm² = 0.787 mm² (91.6 % of the synthesized area)</text>',
      f'<text x="{cx}" y="{cy + 72}" font-size="16" fill="#555" text-anchor="middle" font-style="italic">outline only: area from the .lib, aspect ratio 1.6 assumed (no LEF/GDS supplied)</text>']
# scale bar
sb = 200.0
x1, x2, yb = px(mx + 20), px(mx + 20 + sb), py(my + 25)
s += [f'<line x1="{x1}" y1="{yb}" x2="{x2}" y2="{yb}" stroke="#111" stroke-width="4"/>',
      f'<text x="{(x1+x2)/2}" y="{yb - 10}" font-size="15" text-anchor="middle" fill="#111">200 µm</text>']
# right panel: blocks
rx = X0 + W + 30
s.append(f'<text x="{rx}" y="{Y0 + 18}" font-size="18" font-weight="bold" fill="#111">Standard-cell column (right edge)</text>')
s.append(f'<text x="{rx}" y="{Y0 + 40}" font-size="14" fill="#444">{lw:.0f} × {lh:.0f} µm, blocks top → bottom:</text>')
order = list(range(len(blocks)))[::-1]                      # placed bottom-up; list top-down
yy = Y0 + 66
for i in order:
    lab, n, a, r = blocks[i]
    s.append(f'<rect x="{rx}" y="{yy - 13}" width="16" height="16" fill="{COLORS[i]}" opacity="0.8"/>')
    s.append(f'<text x="{rx + 24}" y="{yy}" font-size="14" fill="#111">{lab}</text>')
    s.append(f'<text x="{rx + 24}" y="{yy + 17}" font-size="12.5" fill="#555">{n:,} cells · {a:,.0f} µm²</text>')
    yy += 40
# zoom inset
zy = yy + 10
s += [f'<text x="{rx}" y="{zy}" font-size="15" font-weight="bold" fill="#111">Zoom: 20 × 11 µm of ipu_pipe</text>',
      f'<image x="{rx}" y="{zy + 8}" width="410" height="230" xlink:href="data:image/png;base64,{b64("ipu_v3_cells_zoom.png")}"/>',
      f'<rect x="{rx}" y="{zy + 8}" width="410" height="230" fill="none" stroke="#333"/>',
      f'<text x="{rx}" y="{zy + 258}" font-size="12.5" fill="#444">real Nangate45 cell layouts (active, poly, contacts,</text>',
      f'<text x="{rx}" y="{zy + 274}" font-size="12.5" fill="#444">metal1) in 1.4 µm rows, alternate rows flipped</text>']
# caveat
cyb = Y0 + H + 25
s += [f'<rect x="40" y="{cyb}" width="1720" height="150" rx="8" fill="#fff8e1" stroke="#c99a00"/>',
      f'<text x="58" y="{cyb + 28}" font-size="16" font-weight="bold" fill="#6b4e00">What this picture is — and is not</text>',
      f'<text x="58" y="{cyb + 54}" font-size="14" fill="#4a3a00">Is: every cell from the Yosys/ABC Nangate45 netlist, placed legally on the 0.19 × 1.40 µm site grid, grouped by RTL block, drawn with the cells\' real GDS; the OpenRAM macro at its real .lib area.</text>',
      f'<text x="58" y="{cyb + 78}" font-size="14" fill="#4a3a00">Is not: an OpenROAD place-and-route. No timing-driven placement, no clock tree, no routing between cells, no power grid beyond the cells\' own rails, no pins, no DRC/LVS.</text>',
      f'<text x="58" y="{cyb + 102}" font-size="14" fill="#4a3a00">The macro is an outline because only its .lib/.v were supplied (its LEF/GDS would give the true shape and pins). Placement script: rtl/ipu_v3/syn/layout/make_placement_view.py.</text>',
      f'<text x="58" y="{cyb + 126}" font-size="14" fill="#4a3a00">Label it on a slide as "placement view (pre-P&amp;R)", not "layout" or "die photo".</text>',
      '</svg>']
open(os.path.join(OUT, "ipu_v3_layout_annotated.svg"), "w").write("\n".join(s))
print("written", os.path.join(OUT, "ipu_v3_layout_annotated.svg"))
