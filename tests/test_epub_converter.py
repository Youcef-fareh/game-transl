import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from epub_converter import (
    create_epub,
    detect_language,
    natural_sort_key,
    parse_text_file,
    read_text_file,
)


class EpubConverterTests(unittest.TestCase):
    def test_natural_sort_orders_chapter_numbers(self):
        names = ["Chapter 10.txt", "Chapter 2.txt", "Chapter 1.txt"]
        self.assertEqual(sorted(names, key=natural_sort_key), ["Chapter 1.txt", "Chapter 2.txt", "Chapter 10.txt"])

    def test_parses_and_numbers_english_chapters(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "novel.txt"
            path.write_text(
                "Novel title\n\nChapter 10: Last\n\nLast chapter text.\n"
                "Chapter 2 - First\n\nFirst chapter text.\n\nSecond paragraph.",
                encoding="utf-8",
            )
            chapters = parse_text_file(path, sort_by_number=True)
        self.assertEqual([chapter.number for chapter in chapters], [2, 10])
        self.assertEqual(chapters[0].title, "First")
        self.assertEqual(chapters[0].text, "First chapter text.\n\nSecond paragraph.")

    def test_parses_arabic_digits_and_detects_rtl(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "رواية.txt"
            path.write_text("الفصل ٢: البداية\n\nهذه فقرة عربية.", encoding="utf-8")
            chapter = parse_text_file(path)[0]
        self.assertEqual(chapter.number, 2)
        self.assertEqual(chapter.language, "ar")
        self.assertEqual(detect_language("A short English sentence."), "en")

    def test_reads_utf8_bom_and_repairs_mojibake(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "arabic.txt"
            path.write_bytes("عنوان الفصل".encode("utf-8-sig"))
            self.assertEqual(read_text_file(path), "عنوان الفصل")
            path.write_text("الفصل".encode("utf-8").decode("latin-1"), encoding="utf-8")
            self.assertEqual(read_text_file(path), "الفصل")

    def test_generates_valid_rtl_epub_structure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "book.txt"
            output = root / "book.epub"
            source.write_text(
                "الفصل 1: البداية\n\nهذه فقرة عربية.\n\nهذه فقرة ثانية.",
                encoding="utf-8",
            )
            count = create_epub([source], output, "رواية", "كاتب")

            self.assertEqual(count, 1)
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(archive.namelist()[0], "mimetype")
                self.assertEqual(archive.read("mimetype"), b"application/epub+zip")
                self.assertEqual(archive.getinfo("mimetype").compress_type, zipfile.ZIP_STORED)
                package = archive.read("OEBPS/content.opf").decode("utf-8")
                chapter = archive.read("OEBPS/Text/chapter-0001.xhtml").decode("utf-8")
                self.assertIn("page-progression-direction=\"rtl\"", package)
                self.assertIn('dir="rtl"', chapter)
                self.assertIn("<p>هذه فقرة عربية.</p>", chapter)
                self.assertIn("<p>هذه فقرة ثانية.</p>", chapter)
                for name in archive.namelist():
                    if name.endswith((".xml", ".xhtml", ".opf")):
                        ElementTree.fromstring(archive.read(name))


if __name__ == "__main__":
    unittest.main()
