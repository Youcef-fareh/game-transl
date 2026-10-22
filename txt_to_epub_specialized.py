#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Specialized script to convert Arabic text file (القس-المجنون) to EPUB
with proper chapter detection, ordering, and completeness verification.
"""

import re
import os
from pathlib import Path
from collections import OrderedDict
import sys
import io

# Force UTF-8 output on Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

try:
    from ebooklib import epub
except ImportError:
    print("Installing required packages...")
    os.system(f"{sys.executable} -m pip install ebooklib")
    from ebooklib import epub


class ArabicTextToEpub:
    def __init__(self, input_file):
        self.input_file = input_file
        self.chapters = OrderedDict()
        self.book = None
        self.title = ""
        
    def read_file(self):
        """Read the input text file with proper encoding."""
        try:
            with open(self.input_file, 'r', encoding='utf-8') as f:
                return f.read()
        except UnicodeDecodeError:
            with open(self.input_file, 'r', encoding='cp1252') as f:
                return f.read()
    
    def parse_chapters(self, content):
        """
        Parse chapters from content.
        Supports multiple chapter markers:
        - الفصل [number] (Arabic)
        - Chapter [number] (English)
        - === Chapter === format
        """
        # Extract title if present
        title_match = re.search(r'^=+\s*(.+?)\s*=+', content, re.MULTILINE)
        if title_match:
            self.title = title_match.group(1).strip()
        
        chapters_found = {}

        numbered_headings = list(re.finditer(
            r'(?im)^[ \t]*(?:الفصل|Chapter)[ \t]+(\d+)[ \t]*[-–—]?[ \t]*(.*?)[ \t]*\r?$',
            content
        ))
        for index, match in enumerate(numbered_headings):
            chapter_num = int(match.group(1))
            chapter_title = match.group(2).strip()
            body_end = (
                numbered_headings[index + 1].start()
                if index + 1 < len(numbered_headings)
                else len(content)
            )
            chapter_content = content[match.end():body_end].strip()
            chapters_found[chapter_num] = {
                'title': chapter_title,
                'content': chapter_content
            }

        if not chapters_found:
            titled_headings = list(re.finditer(
                r'(?m)^===[ \t]*(.+?)[ \t]*===[ \t]*\r?$',
                content
            ))
            for index, match in enumerate(titled_headings):
                chapter_title = match.group(1).strip()
                body_end = (
                    titled_headings[index + 1].start()
                    if index + 1 < len(titled_headings)
                    else len(content)
                )
                chapters_found[index + 1] = {
                    'title': chapter_title,
                    'content': content[match.end():body_end].strip()
                }
        
        # If no chapters found with patterns, split by lines with "الفصل" or "Chapter"
        if not chapters_found:
            lines = content.split('\n')
            current_chapter = None
            current_content = []
            chapter_num = 0
            
            for line in lines:
                if re.match(r'^\s*(الفصل|Chapter)\s+\d+', line, re.IGNORECASE):
                    if current_chapter is not None:
                        chapters_found[chapter_num] = {
                            'title': current_chapter,
                            'content': '\n'.join(current_content)
                        }
                        current_content = []
                    
                    chapter_match = re.search(r'(الفصل|Chapter)\s+(\d+)\s*[-–—]?\s*(.+)', line, re.IGNORECASE)
                    if chapter_match:
                        try:
                            chapter_num = int(chapter_match.group(2))
                        except ValueError:
                            chapter_num = len(chapters_found) + 1
                        current_chapter = chapter_match.group(3).strip()
                else:
                    current_content.append(line)
            
            # Add last chapter
            if current_chapter is not None:
                chapters_found[chapter_num] = {
                    'title': current_chapter,
                    'content': '\n'.join(current_content)
                }
        
        # Sort by chapter number
        self.chapters = OrderedDict(sorted(chapters_found.items()))
        return self.chapters
    
    def create_epub(self, output_file):
        """Create EPUB with parsed chapters."""
        if not self.chapters:
            print("No chapters found in the input file!")
            return False
        
        # Create EPUB book
        self.book = epub.EpubBook()
        
        # Set metadata
        book_title = self.title or Path(self.input_file).stem
        self.book.set_title(book_title)
        self.book.set_language('ar')  # Arabic
        self.book.add_author('Author')
        
        # Add chapters
        chapter_items = []
        for chapter_num, chapter_data in self.chapters.items():
            chapter_title = chapter_data['title'] or f"الفصل {chapter_num}"
            chapter_content = chapter_data['content']
            
            # Clean content
            chapter_content = self._clean_content(chapter_content)
            
            # Create chapter
            epub_chapter = epub.EpubHtml(
                title=f"Chapter {chapter_num}",
                file_name=f'chap_{chapter_num:03d}.xhtml',
                lang='ar'
            )
            
            epub_chapter.content = f"""
            <html>
            <head>
                <meta charset="UTF-8"/>
                <title>{chapter_title}</title>
                <style>
                    body {{ direction: rtl; text-align: right; font-family: Arial, sans-serif; }}
                    h1 {{ margin-bottom: 1em; }}
                    p {{ margin-bottom: 0.5em; line-height: 1.6; }}
                </style>
            </head>
            <body>
                <h1>{chapter_title}</h1>
                {self._format_content(chapter_content)}
            </body>
            </html>
            """
            
            self.book.add_item(epub_chapter)
            chapter_items.append(epub_chapter)
        
        # Create table of contents
        self.book.toc = tuple(chapter_items)
        
        # Add navigation files
        self.book.add_item(epub.EpubNcx())
        self.book.add_item(epub.EpubNav())
        
        # Define CSS style
        style = 'BODY {color: #000;}'
        nav_css = epub.EpubItem(
            uid='style_nav',
            file_name='style/nav.css',
            media_type='text/css',
            content=style
        )
        self.book.add_item(nav_css)
        
        # Add spine
        self.book.spine = ['nav'] + chapter_items
        
        # Write EPUB file
        try:
            epub.write_epub(output_file, self.book, {})
            print(f"[OK] EPUB created successfully: {output_file}")
            print(f"[OK] Total chapters: {len(self.chapters)}")
            return True
        except Exception as e:
            print(f"[ERROR] Error creating EPUB: {e}")
            return False
    
    def _clean_content(self, content):
        """Clean content for EPUB."""
        # Remove extra whitespace
        content = re.sub(r'\n\s*\n+', '\n\n', content)
        # Remove control characters
        content = re.sub(r'[\x00-\x08\x0B-\x0C\x0E-\x1F]', '', content)
        return content.strip()
    
    def _format_content(self, content):
        """Format content as HTML paragraphs."""
        paragraphs = content.split('\n\n')
        html_content = ''
        for para in paragraphs:
            if para.strip():
                html_content += f'<p>{para.strip()}</p>\n'
        return html_content
    
    def print_summary(self):
        """Print summary of parsed chapters."""
        print(f"\n[BOOK] Title: {self.title or 'N/A'}")
        print(f"[BOOK] Total Chapters: {len(self.chapters)}")
        print(f"\n[CHAPTERS] Chapter List:")
        print("-" * 60)
        for chapter_num, chapter_data in self.chapters.items():
            title = chapter_data['title'][:50] + "..." if len(chapter_data['title']) > 50 else chapter_data['title']
            content_length = len(chapter_data['content'])
            print(f"  {chapter_num:3d}. {title:<50} ({content_length} chars)")
        print("-" * 60)


def main():
    input_file = r"C:\projects\py\large-txt\القس-المجنون (1).txt"
    output_file = r"C:\projects\py\large-txt\القس-المجنون.epub"
    
    if not os.path.exists(input_file):
        print(f"[ERROR] Input file not found: {input_file}")
        return False
    
    print(f"[*] Processing: {input_file}")
    file_size_mb = os.path.getsize(input_file) / 1024 / 1024
    print(f"[*] File size: {file_size_mb:.2f} MB")
    
    # Convert
    converter = ArabicTextToEpub(input_file)
    content = converter.read_file()
    
    print("\n[*] Parsing chapters...")
    converter.parse_chapters(content)
    converter.print_summary()
    
    print(f"\n[*] Creating EPUB: {output_file}")
    if converter.create_epub(output_file):
        print(f"\n[OK] Conversion completed!")
        return True
    else:
        print(f"\n[ERROR] Conversion failed!")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
