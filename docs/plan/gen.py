"""Regenerate the plan docx in the same raw-XML style as the original."""
import re
import sys
import zipfile
from xml.sax.saxutils import escape

OUT = sys.argv[1]
TPL = sys.argv[2]  # original docx, for [Content_Types].xml and _rels

H = []  # xml chunks


def runs(text, size):
    out = []
    for i, part in enumerate(re.split(r"\*\*", text)):
        if not part:
            continue
        b = "<w:b/>" if i % 2 else ""
        out.append(f'<w:r><w:rPr>{b}<w:sz w:val="{size}"/></w:rPr>'
                   f'<w:t xml:space="preserve">{escape(part)}</w:t></w:r>')
    return "".join(out)


def para(text, before=0, after=120, size=22, ind=""):
    H.append(f'<w:p><w:pPr><w:spacing w:before="{before}" w:after="{after}"/>{ind}</w:pPr>'
             f'{runs(text, size)}</w:p>')


def title(t):
    H.append('<w:p><w:pPr><w:spacing w:before="0" w:after="120"/></w:pPr><w:r><w:rPr><w:b/>'
             f'<w:sz w:val="36"/></w:rPr><w:t xml:space="preserve">{escape(t)}</w:t></w:r></w:p>')


def h(t):
    para(f"**{t}**", before=320, size=28)


def h2(t):
    para(f"**{t}**", before=200, after=80, size=24)


def p(t):
    para(t)


IND = '<w:ind w:left="360" w:hanging="240"/>'


def b(t):
    para("•  " + t, after=80, ind=IND)


def n(items):
    for i, t in enumerate(items, 1):
        para(f"{i}.  " + t, after=80, ind=IND)


def code(lines):
    for ln in lines:
        H.append('<w:p><w:pPr><w:spacing w:before="0" w:after="0"/></w:pPr><w:r><w:rPr>'
                 '<w:rFonts w:ascii="Courier New" w:hAnsi="Courier New" w:cs="Courier New"/>'
                 f'<w:sz w:val="18"/></w:rPr><w:t xml:space="preserve">{escape(ln)}</w:t></w:r></w:p>')
    para("", after=60)


def table(rows):
    cols = len(rows[0])
    w = 9000 // cols
    border = "".join(f'<w:{s} w:val="single" w:sz="4" w:space="0" w:color="999999"/>'
                     for s in ("top", "left", "bottom", "right", "insideH", "insideV"))
    x = [f'<w:tbl><w:tblPr><w:tblW w:w="5000" w:type="pct"/><w:tblBorders>{border}</w:tblBorders>'
         '</w:tblPr><w:tblGrid>' + f'<w:gridCol w:w="{w}"/>' * cols + '</w:tblGrid>']
    for r, row in enumerate(rows):
        x.append("<w:tr>")
        for cell in row:
            t = f"**{cell}**" if r == 0 else cell
            x.append(f'<w:tc><w:tcPr><w:tcW w:w="{w}" w:type="dxa"/></w:tcPr>'
                     f'<w:p><w:pPr><w:spacing w:before="0" w:after="40"/></w:pPr>{runs(t, 20)}</w:p></w:tc>')
        x.append("</w:tr>")
    x.append("</w:tbl>")
    H.append("".join(x))
    para("", after=60)


exec(open(sys.argv[3], encoding="utf-8").read())

body = "".join(H)
doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document '
       'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
       f'{body}<w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1440" w:right="1440" '
       'w:bottom="1440" w:left="1440" w:header="708" w:footer="708" w:gutter="0"/></w:sectPr>'
       '</w:body></w:document>')
with zipfile.ZipFile(TPL) as src, zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as dst:
    for item in src.infolist():
        data = doc.encode() if item.filename == "word/document.xml" else src.read(item.filename)
        dst.writestr(item, data)
