"""Print build: hoist full-width elements out of the column flow, then add IEEE print CSS."""
import re
from pathlib import Path
D = Path(__file__).resolve().parent
c = (D / "doppelganger-screens.html").read_text(encoding="utf-8")

TAG = re.compile(r'<(/?)div\b[^>]*>', re.I)
def end_div(s, i):
    m = TAG.match(s, i); depth, pos = 1, m.end()
    while depth:
        m2 = TAG.search(s, pos)
        depth += -1 if m2.group(1) else 1
        pos = m2.end()
    return pos

out, i, moved = [], 0, 0
while True:
    mf = c.find('<figure class="fig span">', i)
    mt = c.find('<div class="tblwrap span">', i)
    cands = [x for x in (mf, mt) if x != -1]
    if not cands:
        out.append(c[i:]); break
    j = min(cands)
    if j == mf:
        e = c.index('</figure>', j) + len('</figure>')
    else:
        e = end_div(c, j)
    out.append(c[i:j])
    out.append('</div>\n' + c[j:e] + '\n<div class="cols">')
    moved += 1
    i = e
c = "".join(out)
# an empty column block left by two adjacent spanners renders as a stray gap
c = re.sub(r'<div class="cols">\s*</div>', '', c)
probe = re.sub(r'data:image/[a-z]+;base64,[A-Za-z0-9+/=]+', '', c)
print("hoisted:", moved, "| div balance:", len(re.findall(r'<div\b', probe)) - len(re.findall(r'</div>', probe)))

PRINT = """
<style>
@page{size:A4;margin:16mm 14mm 18mm}
html{-webkit-print-color-adjust:exact;print-color-adjust:exact}
body{font-size:9.2pt;line-height:1.32;background:#fff;color:#000}
.page{max-width:none;padding:0}
.ttl{font-size:20pt;line-height:1.14;margin-bottom:5pt}
.auth{font-size:10.5pt}.aff{font-size:8.6pt}.stamp{font-size:7.4pt;margin-bottom:10pt}
.lead{padding:8pt 0 6pt;margin-bottom:9pt}
.abs,.idx{font-size:9pt;line-height:1.36}
h2{font-size:10pt;font-weight:700;margin:10pt 0 3pt;break-after:avoid;page-break-after:avoid}
h3{font-size:9.3pt;font-weight:700;margin:8pt 0 2pt;break-after:avoid;page-break-after:avoid}
.cols{column-count:2;column-gap:6.5mm;column-fill:balance;orphans:3;widows:3}
figure{margin:6pt 0 7pt}
figure.span{margin:8pt 0 9pt}
figure img{display:block;margin:0 auto;width:auto;max-width:100%;max-height:58mm}
figure.span img{max-height:60mm}
figcaption{font-size:7.5pt;line-height:1.26;margin-top:3pt}
table{font-size:7.3pt}th,td{padding:2pt 4pt}
.tcap{font-size:8pt}.tcap span{font-size:7.6pt}
.ref{font-size:7.1pt;line-height:1.17;margin:0 0 1.2px}
code{font-size:7.6pt}
.plate img{max-height:none}
figure,.tblwrap,.plate>div{break-inside:avoid}
a{color:inherit;text-decoration:none}
</style>
"""
doc = ('<!doctype html><html lang="en" data-theme="light"><head><meta charset="utf-8">'
       '<meta name="viewport" content="width=device-width,initial-scale=1">'
       '<style>body{margin:0}img{max-width:100%}</style></head><body>\n' + c + PRINT + "</body></html>")
(D / "print.html").write_text(doc, encoding="utf-8")
print("print build:", f"{len(doc):,} bytes")
