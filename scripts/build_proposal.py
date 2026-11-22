"""Build docs/proposal.pdf from docs/proposal.md.

The PDF metadata names Omar Vasquez as the author and does not leave a
generator tag. Run from the repository root:

    python scripts/build_proposal.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "proposal.md"
TARGET = ROOT / "docs" / "proposal.pdf"
TITLE = "LogSieve: A Compressed Full Text Index for Fast Security Log Search"
AUTHOR = "Omar Vasquez"

CSS = """
@page {
  size: letter;
  margin: 1in;
  @bottom-center {
    content: counter(page);
    font-family: "Liberation Serif", "DejaVu Serif", serif;
    font-size: 11pt;
    color: #222;
  }
}
html, body {
  font-family: "Liberation Serif", "DejaVu Serif", serif;
  font-size: 11pt;
  line-height: 1.30;
  color: #111;
}
h1 { font-size: 16pt; line-height: 1.25; margin: 0.6em 0 0.3em; }
h2 { font-size: 13.5pt; line-height: 1.25; margin: 0.9em 0 0.3em; }
h3 { font-size: 12pt; margin: 0.7em 0 0.2em; }
p { margin: 0 0 0.55em; }
.title-page { page-break-after: always; }
.title-page h1 { font-size: 20pt; margin-top: 1.4in; }
.meta { margin-top: 0.4in; line-height: 1.45; }
.abstract-label { font-variant: small-caps; letter-spacing: 0.04em; }
table { border-collapse: collapse; width: 100%; margin: 0.4em 0 0.8em; font-size: 9.5pt; line-height: 1.25; }
th, td { border: 1px solid #333; padding: 3px 5px; vertical-align: top; text-align: left; }
th { background: #f3f3f3; }
caption, .caption { font-size: 10.5pt; margin: 0.2em 0 0.8em; }
img.figure { width: 5.5in; height: auto; }
.center { text-align: center; }
code { font-family: "Liberation Mono", "DejaVu Sans Mono", monospace; font-size: 10pt; }
a { color: #111; text-decoration: none; }
"""


def build() -> None:
    try:
        from weasyprint import HTML
    except ImportError:
        print("weasyprint is required to rebuild the PDF", file=sys.stderr)
        sys.exit(1)
    text = SOURCE.read_text(encoding="utf-8")
    body = markdown.markdown(
        text,
        extensions=["tables", "fenced_code", "sane_lists"],
        output_format="html5",
    )
    html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>%s</title>
<meta name="author" content="%s">
<style>%s</style>
</head>
<body>
%s
</body>
</html>
""" % (TITLE, AUTHOR, CSS, body)
    document = HTML(string=html, base_url=str(ROOT / "docs")).render()
    document.metadata.title = TITLE
    document.metadata.authors = [AUTHOR]
    document.metadata.creator = AUTHOR
    document.metadata.producer = AUTHOR
    document.metadata.keywords = []
    document.metadata.description = None
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    document.write_pdf(str(TARGET))
    _scrub_metadata(TARGET)
    print("wrote %s" % TARGET)


def _scrub_metadata(path: Path) -> None:
    """Replace the generator tag with the author name."""

    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError:
        return
    reader = PdfReader(str(path))
    writer = PdfWriter()
    writer.append(reader)
    writer.add_metadata(
        {
            "/Title": TITLE,
            "/Author": AUTHOR,
            "/Creator": AUTHOR,
            "/Producer": AUTHOR,
        }
    )
    with path.open("wb") as handle:
        writer.write(handle)


if __name__ == "__main__":
    build()
