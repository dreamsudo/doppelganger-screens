"""Stamp page numbers onto the rendered PDF. Chromium cannot draw them, so they are
merged in afterwards from a transparent overlay."""
import sys
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
matplotlib.rcParams["pdf.fonttype"] = 42      # TrueType: IEEE PDF eXpress rejects Type 3
matplotlib.rcParams["ps.fonttype"] = 42
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from pypdf import PdfReader, PdfWriter

D = Path(__file__).resolve().parent
src = D / "doppelganger-screens.pdf"
reader = PdfReader(str(src))
n = len(reader.pages)
box = reader.pages[0].mediabox
W, H = float(box.width) / 72.0, float(box.height) / 72.0   # inches

overlay = D / "_numbers.pdf"
with PdfPages(overlay) as pdf:
    for i in range(1, n + 1):
        fig = plt.figure(figsize=(W, H))
        fig.text(0.5, 0.042, str(i), ha="center", va="center",
                 fontsize=9, color="#000000", family="serif")
        pdf.savefig(fig, transparent=True)
        plt.close(fig)

nums = PdfReader(str(overlay))
out = PdfWriter()
for i, page in enumerate(reader.pages):
    page.merge_page(nums.pages[i])
    out.add_page(page)
with open(src, "wb") as f:
    out.write(f)
overlay.unlink()
print(f"stamped {n} page numbers")
