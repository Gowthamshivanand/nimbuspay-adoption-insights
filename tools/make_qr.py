"""Make a QR code for a URL: writes qr.png and qr.svg.
Usage: python tools/make_qr.py https://your-domain.example [--out assets] [--label "text"]
Needs: pip install segno
"""
import argparse, os, segno
a = argparse.ArgumentParser(); a.add_argument("url"); a.add_argument("--out", default="assets"); a.add_argument("--label", default=None)
x = a.parse_args(); os.makedirs(x.out, exist_ok=True)
q = segno.make(x.url, error="m")
q.save(os.path.join(x.out, "qr.png"), scale=10, border=4, dark="#2B2B2B")
q.save(os.path.join(x.out, "qr.svg"), scale=10, border=4, dark="#2B2B2B", title=x.label or x.url)
if x.label:
    try:
        from PIL import Image, ImageDraw
        im = Image.open(os.path.join(x.out, "qr.png")).convert("RGB"); w, h = im.size
        out = Image.new("RGB", (w, h + 40), "white"); out.paste(im, (0, 0)); d = ImageDraw.Draw(out)
        d.text((10, h + 10), x.label, fill=(198, 40, 40)); out.save(os.path.join(x.out, "qr.png"))
    except ImportError:
        pass
print("Wrote", os.path.join(x.out, "qr.png"), "and qr.svg for", x.url)
