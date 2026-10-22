"""Create well-structured multilingual EPUB files using only the standard library."""

from __future__ import annotations

import html
import re
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

CHAPTER_HEADING = re.compile(
    r"^[ \t]*(?:(?P<prefix>.+?)\s*[-–—:]\s*)?"
    r"(?P<label>chapter|ch\.?|الفصل|باب|الجزء)\s*"
    r"(?P<number>\d+)"
    r"(?:\s*[:：.،-]\s*(?P<title>.*?))?[ \t]*$",
    re.IGNORECASE,
)
NUMBERED_TITLE_HEADING = re.compile(
    r"^[ \t]*(?P<prefix>[^—–\-\r\n]{1,100}?)\s*[-–—]\s*"
    r"(?P<number>\d{1,6})\s*[–—:]\s*(?P<title>.+?)[ \t]*$"
)

CSS = """
html, body { margin: 0; padding: 0; }
body { font-family: serif; font-size: 1em; line-height: 1.8; padding: 5% 7%; }
body.rtl { direction: rtl; text-align: right; }
body.ltr { direction: ltr; text-align: left; }
h1 { text-align: center; font-size: 1.5em; line-height: 1.5; margin: 0 0 1.6em; }
p { margin: 0 0 1em; text-indent: 1em; }
.title-page { min-height: 75vh; display: flex; flex-direction: column; justify-content: center; text-align: center; }
.title-page p { text-indent: 0; }
nav ol { line-height: 1.8; }
""".strip()


@dataclass(frozen=True)
class Chapter:
    title: str
    text: str
    number: int | None = None
    language: str = "en"


def natural_sort_key(value: str) -> list[int | str]:
    return [
        int(part) if part.isdigit() else part.casefold()
        for part in re.split(r"(\d+)", value)
    ]


def _arabic_character_count(text: str) -> int:
    return sum("\u0600" <= char <= "\u06ff" or "\u0750" <= char <= "\u077f" for char in text)


def _latin_character_count(text: str) -> int:
    return sum(("a" <= char.lower() <= "z") for char in text)


def _repair_mojibake(text: str) -> str:
    if not any(marker in text for marker in ("Ø", "Ù", "Ã", "Â")):
        return text
    candidates = [text]
    for encoding in ("cp1252", "latin-1"):
        try:
            candidates.append(text.encode(encoding).decode("utf-8"))
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
    return max(candidates, key=_arabic_character_count)


def read_text_file(path: Path) -> str:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        for encoding in ("cp1256", "cp1252"):
            try:
                text = raw.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise UnicodeError(
                f"Unable to decode {path.name} as UTF-8, CP1256, or CP1252."
            )
    return _repair_mojibake(text).replace("\r\n", "\n").replace("\r", "\n")


def detect_language(text: str) -> str:
    return "ar" if _arabic_character_count(text) > _latin_character_count(text) else "en"


def _paragraphs(text: str) -> list[str]:
    blocks = re.split(r"\n[ \t]*\n+", text.strip())
    paragraphs = []
    for block in blocks:
        if block.strip():
            paragraph = " ".join(line.strip() for line in block.splitlines() if line.strip())
            paragraphs.append(re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", paragraph))
    return paragraphs


def _heading(line: str) -> tuple[int, str] | None:
    match = CHAPTER_HEADING.match(line)
    if match:
        number = int(match.group("number"))
        title = (match.group("title") or "").strip()
        label = match.group("label")
        if not title:
            title = f"{label} {number}"
        return number, title

    match = NUMBERED_TITLE_HEADING.match(line)
    if match:
        return int(match.group("number")), match.group("title").strip()
    return None


def parse_text_file(path: Path, *, sort_by_number: bool = False) -> list[Chapter]:
    text = read_text_file(path)
    lines = text.splitlines(keepends=True)
    matches: list[tuple[int, int, str, int]] = []
    offset = 0
    for line in lines:
        heading = _heading(line.rstrip("\n"))
        if heading is not None:
            number, title = heading
            matches.append((offset, offset + len(line), title, number))
        offset += len(line)

    if not matches:
        body = text.strip()
        return [Chapter(path.stem, body, language=detect_language(body))]

    chapters: list[Chapter] = []
    for index, (_, body_start, title, number) in enumerate(matches):
        body_end = matches[index + 1][0] if index + 1 < len(matches) else len(text)
        body = text[body_start:body_end].strip()
        chapters.append(Chapter(title, body, number, detect_language(f"{title}\n{body}")))

    if sort_by_number:
        chapters.sort(key=lambda chapter: chapter.number if chapter.number is not None else float("inf"))
    return chapters


def _xhtml_page(title: str, body: str, language: str, direction: str) -> str:
    safe_title = html.escape(title)
    return f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="{language}" xml:lang="{language}" dir="{direction}">
<head>
  <meta charset="utf-8" />
  <title>{safe_title}</title>
  <link rel="stylesheet" type="text/css" href="../Styles/style.css" />
</head>
<body class="{direction}">
{body}
</body>
</html>"""


def create_epub(
    input_paths: list[Path],
    output_path: Path,
    title: str,
    author: str = "",
    *,
    sort_by_number: bool = False,
) -> int:
    if not input_paths:
        raise ValueError("Choose at least one TXT file.")

    chapters = [
        chapter
        for path in input_paths
        for chapter in parse_text_file(path, sort_by_number=sort_by_number)
        if chapter.text.strip()
    ]
    if not chapters:
        raise ValueError("The selected TXT files do not contain any readable text.")

    total_arabic = sum(_arabic_character_count(chapter.text) for chapter in chapters)
    total_latin = sum(_latin_character_count(chapter.text) for chapter in chapters)
    book_language = "ar" if total_arabic > total_latin else "en"
    book_direction = "rtl" if book_language == "ar" else "ltr"
    identifier = f"urn:uuid:{uuid.uuid4()}"
    modified = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    manifest = [
        '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
        '<item id="titlepage" href="Text/titlepage.xhtml" media-type="application/xhtml+xml"/>',
        '<item id="css" href="Styles/style.css" media-type="text/css"/>',
    ]
    spine = ['<itemref idref="titlepage"/>']
    nav_links: list[str] = []
    chapter_files: list[tuple[str, str]] = []

    for index, chapter in enumerate(chapters, start=1):
        filename = f"chapter-{index:04d}.xhtml"
        item_id = f"chapter{index}"
        direction = "rtl" if chapter.language == "ar" else "ltr"
        heading = f"<h1>{html.escape(chapter.title)}</h1>"
        paragraphs = "\n".join(f"<p>{html.escape(paragraph)}</p>" for paragraph in _paragraphs(chapter.text))
        page = _xhtml_page(chapter.title, f"{heading}\n{paragraphs}", chapter.language, direction)
        chapter_files.append((f"OEBPS/Text/{filename}", page))
        manifest.append(
            f'<item id="{item_id}" href="Text/{filename}" media-type="application/xhtml+xml"/>'
        )
        spine.append(f'<itemref idref="{item_id}"/>')
        nav_links.append(
            f'<li><a href="Text/{filename}">{html.escape(chapter.title)}</a></li>'
        )

    safe_book_title = html.escape(title)
    safe_author = html.escape(author)
    titlepage = _xhtml_page(
        title,
        f'<div class="title-page"><h1>{safe_book_title}</h1>'
        + (f"<p>{safe_author}</p>" if author.strip() else "")
        + f"<p>{len(chapters):,} chapters</p></div>",
        book_language,
        book_direction,
    )
    navigation = f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml"
      xmlns:epub="http://www.idpf.org/2007/ops"
      lang="{book_language}" xml:lang="{book_language}" dir="{book_direction}">
<head>
  <meta charset="utf-8" />
  <title>Contents</title>
  <link rel="stylesheet" type="text/css" href="Styles/style.css" />
</head>
<body class="{book_direction}">
  <nav epub:type="toc" id="toc">
    <h1>Contents</h1>
    <ol>
      {"".join(nav_links)}
    </ol>
  </nav>
</body>
</html>"""
    container = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>"""
    package = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0"
         unique-identifier="book-id" xml:lang="{book_language}">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="book-id">{identifier}</dc:identifier>
    <dc:title>{html.escape(title)}</dc:title>
    {f"<dc:creator>{safe_author}</dc:creator>" if author.strip() else ""}
    <dc:language>{book_language}</dc:language>
    <meta property="dcterms:modified">{modified}</meta>
  </metadata>
  <manifest>
    {"".join(manifest)}
  </manifest>
  <spine page-progression-direction="{book_direction}">
    {"".join(spine)}
  </spine>
</package>"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        output_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
    ) as archive:
        archive.writestr(
            "mimetype",
            "application/epub+zip",
            compress_type=zipfile.ZIP_STORED,
        )
        archive.writestr("META-INF/container.xml", container)
        archive.writestr("OEBPS/content.opf", package)
        archive.writestr("OEBPS/nav.xhtml", navigation)
        archive.writestr("OEBPS/Styles/style.css", CSS)
        archive.writestr("OEBPS/Text/titlepage.xhtml", titlepage)
        for path, content in chapter_files:
            archive.writestr(path, content)

    return len(chapters)
