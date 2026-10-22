# -*- coding: utf-8 -*-
"""Convert an Arabic novel TXT file into an organized EPUB.

Expected chapter heading format:
    الفصل 1: عنوان الفصل
or:
    الفصل ١٦١٤: عنوان الفصل

The script:
- detects chapters automatically (Arabic-Indic and Western digits)
- puts every chapter in its own XHTML file
- creates an EPUB 3 table of contents
- applies RTL Arabic layout and Arabic-friendly fonts
- optionally removes common source/promotional notices
- requires only Python's standard library
"""

from pathlib import Path
import argparse
import re
import html
import zipfile
from xml.sax.saxutils import escape as xml_escape
from datetime import datetime, timezone

# ============================================================
# CONFIGURATION
# ============================================================
PROJECT_DIR = Path(__file__).resolve().parent
INPUT_DIR = PROJECT_DIR / "large-txt"
OUTPUT_DIR = PROJECT_DIR / "files"

# True = remove recurring website/source notices from the reading copy.
# False = preserve every paragraph from the TXT except separators.
REMOVE_SOURCE_NOTICES = True

# Chapter headings such as "الفصل 1: ..." or "الفصل ١٦١٤: ..."
# Python's \d supports both Western and Arabic-Indic digits.
CHAPTER_RE = re.compile(
    r"(?m)^[ \t]*الفصل\s+(\d+)\s*[:：]\s*(.+?)\s*$"
)

SOURCE_NOTICE_PATTERNS = [
    re.compile(r"مجرة الروايات"),
    re.compile(r"مَجـرَّة الرِّوايات"),
    re.compile(r"مَجَرَّة الرِّوَايـات"),
    re.compile(r"galaxynovels\.com", re.I),
    re.compile(r"هذا الفصل ترجم من"),
    re.compile(r"تذكّير من .* الصلاة"),
    re.compile(r"لا تدع القراءة تلهيك عن صلاتك"),
]

CSS = r"""
html, body { margin: 0; padding: 0; }
body {
  direction: rtl;
  text-align: right;
  font-family: "Noto Naskh Arabic", "Amiri", "Scheherazade New",
               "DejaVu Sans", serif;
  font-size: 1em;
  line-height: 1.95;
  padding: 5% 7%;
  word-wrap: break-word;
}
h1 {
  text-align: center;
  font-size: 1.45em;
  line-height: 1.5;
  margin: 0 0 1.6em 0;
}
p {
  margin: 0 0 1em 0;
  text-indent: 1em;
}
.title-page {
  min-height: 80vh;
  display: flex;
  flex-direction: column;
  justify-content: center;
  text-align: center;
}
.title-page h1 { font-size: 2em; }
.title-page p { text-indent: 0; }
.chapter-list {
  list-style: none;
  padding: 0;
}
.chapter-list li { margin: 0.45em 0; }
a { text-decoration: none; }
""".strip()


def is_source_notice(paragraph: str) -> bool:
    return any(pattern.search(paragraph) for pattern in SOURCE_NOTICE_PATTERNS)


def clean_text(raw: str) -> str:
    """Normalize line endings and remove separator-only lines."""
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    kept = []
    for line in raw.split("\n"):
        if line.strip() in {"---", "———", "___", "***"}:
            continue
        kept.append(line.rstrip())

    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()


def paragraphize(chapter_text: str):
    """Turn blank-line-separated TXT blocks into EPUB paragraphs."""
    blocks = re.split(r"\n\s*\n+", chapter_text.strip())
    paragraphs = []

    for block in blocks:
        # Keep a multi-line text block as one paragraph, which prevents
        # accidental paragraph fragmentation from line wrapping.
        paragraph = " ".join(part.strip() for part in block.splitlines()).strip()
        if not paragraph:
            continue

        if REMOVE_SOURCE_NOTICES and is_source_notice(paragraph):
            continue

        paragraphs.append(paragraph)

    return paragraphs


def split_chapters(text: str):
    matches = list(CHAPTER_RE.finditer(text))
    if not matches:
        raise ValueError(
            "No chapter headings found. Expected lines like: الفصل 1: عنوان الفصل"
        )

    chapters = []
    for i, match in enumerate(matches):
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[match.end():body_end].strip()

        # Remove optional end-of-chapter marker.
        body = re.sub(
            r"(?m)^\s*✦\s*انتهى الفصل\s*✦\s*$", "", body
        ).strip()

        number_text = match.group(1)
        title = match.group(2).strip()
        chapters.append(
            {
                "number": int(number_text),
                "title": title,
                "paragraphs": paragraphize(body),
            }
        )

    return chapters


def xhtml_page(title: str, body_html: str) -> str:
    return f'''<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="ar" xml:lang="ar" dir="rtl">
<head>
  <meta charset="utf-8" />
  <title>{html.escape(title)}</title>
  <link rel="stylesheet" type="text/css" href="../Styles/style.css" />
</head>
<body dir="rtl">
{body_html}
</body>
</html>'''


def make_epub(input_txt: Path, output_epub: Path):
    text = input_txt.read_text(encoding="utf-8-sig", errors="replace")
    text = clean_text(text)
    chapters = split_chapters(text)

    first_chapter = CHAPTER_RE.search(text)
    before_chapters = text[:first_chapter.start()].strip() if first_chapter else ""
    first_line = next((x.strip() for x in before_chapters.splitlines() if x.strip()), "")
    book_title = first_line or input_txt.stem

    modified = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    uid = "urn:txt-to-epub:" + re.sub(r"[^A-Za-z0-9_-]", "-", book_title)[:80]

    manifest_items = [
        '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
        '<item id="titlepage" href="Text/titlepage.xhtml" media-type="application/xhtml+xml"/>',
        '<item id="toc" href="Text/toc.xhtml" media-type="application/xhtml+xml"/>',
        '<item id="css" href="Styles/style.css" media-type="text/css"/>',
    ]
    spine_items = [
        '<itemref idref="titlepage"/>',
        '<itemref idref="toc"/>',
    ]
    nav_links = []
    ncx_points = []
    chapter_files = []

    for index, chapter in enumerate(chapters, start=1):
        filename = f"chapter-{index:04d}.xhtml"
        item_id = f"chapter{index}"
        title = f"الفصل {chapter['number']}: {chapter['title']}"

        body = [f'<h1>{html.escape(title)}</h1>']
        body.extend(f'<p>{html.escape(p)}</p>' for p in chapter["paragraphs"])
        chapter_files.append(
            (f"OEBPS/Text/{filename}", xhtml_page(title, "\n".join(body)))
        )

        manifest_items.append(
            f'<item id="{item_id}" href="Text/{filename}" '
            f'media-type="application/xhtml+xml"/>'
        )
        spine_items.append(f'<itemref idref="{item_id}"/>')
        nav_links.append(
            f'<li><a href="Text/{filename}">{html.escape(title)}</a></li>'
        )
        ncx_points.append(
            f'''<navPoint id="navPoint-{index}" playOrder="{index}">
  <navLabel><text>{xml_escape(title)}</text></navLabel>
  <content src="Text/{filename}"/>
</navPoint>'''
        )

    titlepage = xhtml_page(
        book_title,
        f'''<div class="title-page">
  <h1>{html.escape(book_title)}</h1>
  <p>الكتاب مقسم إلى {len(chapters):,} فصلًا.</p>
</div>''',
    )

    toc_page = xhtml_page(
        "فهرس الفصول",
        '<h1>فهرس الفصول</h1>\n<ul class="chapter-list">\n'
        + "\n".join(nav_links)
        + "\n</ul>",
    )

    nav_xhtml = f'''<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml"
      xmlns:epub="http://www.idpf.org/2007/ops"
      lang="ar" xml:lang="ar" dir="rtl">
<head>
  <meta charset="utf-8" />
  <title>فهرس الفصول</title>
  <link rel="stylesheet" type="text/css" href="Styles/style.css" />
</head>
<body dir="rtl">
  <nav epub:type="toc" id="toc">
    <h1>فهرس الفصول</h1>
    <ol>
      {"\n      ".join(nav_links)}
    </ol>
  </nav>
</body>
</html>'''

    container_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0"
 xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf"
      media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>'''

    content_opf = f'''<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf"
 version="3.0" unique-identifier="book-id" xml:lang="ar" dir="rtl">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="book-id">{xml_escape(uid)}</dc:identifier>
    <dc:title>{xml_escape(book_title)}</dc:title>
    <dc:language>ar</dc:language>
    <meta property="dcterms:modified">{modified}</meta>
  </metadata>
  <manifest>
    {chr(10).join(manifest_items)}
  </manifest>
  <spine page-progression-direction="rtl">
    {chr(10).join(spine_items)}
  </spine>
</package>'''

    ncx = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE ncx PUBLIC "-//NISO//DTD ncx 2005-1//EN"
 "http://www.daisy.org/z3986/2005/ncx-2005-1.dtd">
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1" xml:lang="ar" dir="rtl">
  <head>
    <meta name="dtb:uid" content="{xml_escape(uid)}"/>
  </head>
  <docTitle><text>{xml_escape(book_title)}</text></docTitle>
  <navMap>
{chr(10).join(ncx_points)}
  </navMap>
</ncx>'''

    output_epub.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_epub, "w", compression=zipfile.ZIP_DEFLATED) as epub:
        # EPUB rule: mimetype must be the first entry and STORED (uncompressed).
        epub.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        epub.writestr("META-INF/container.xml", container_xml)
        epub.writestr("OEBPS/content.opf", content_opf)
        epub.writestr("OEBPS/nav.xhtml", nav_xhtml)
        epub.writestr("OEBPS/toc.ncx", ncx)
        epub.writestr("OEBPS/Styles/style.css", CSS)
        epub.writestr("OEBPS/Text/titlepage.xhtml", titlepage)
        epub.writestr("OEBPS/Text/toc.xhtml", toc_page)
        for path, data in chapter_files:
            epub.writestr(path, data)

    return {
        "title": book_title,
        "chapters": len(chapters),
        "bytes": output_epub.stat().st_size,
    }


def main():
    parser = argparse.ArgumentParser(description="Convert a large Arabic TXT book to EPUB.")
    parser.add_argument("input", nargs="?", type=Path, help="Input TXT (defaults to the only TXT in large-txt/)")
    parser.add_argument("output", nargs="?", type=Path, help="Output EPUB (defaults to files/<input-name>.epub)")
    args = parser.parse_args()

    if args.input is not None:
        input_txt = args.input.resolve()
    else:
        input_files = sorted(INPUT_DIR.glob("*.txt"))
        if len(input_files) != 1:
            raise SystemExit(
                f"Expected exactly one .txt file in {INPUT_DIR}, found {len(input_files)}. "
                "Pass the input path as an argument."
            )
        input_txt = input_files[0]

    output_epub = args.output.resolve() if args.output else OUTPUT_DIR / f"{input_txt.stem}.epub"
    result = make_epub(input_txt, output_epub)
    print(f"Created: {output_epub.resolve()}")
    print(f"Title: {result['title']}")
    print(f"Chapters: {result['chapters']:,}")
    print(f"Size: {result['bytes'] / 1024 / 1024:.2f} MB")


if __name__ == "__main__":
    main()
