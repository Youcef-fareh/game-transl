import os
import re
import html
from ebooklib import epub

# ==========================================
# CONFIGURATION
# ==========================================
script_dir = os.path.dirname(os.path.abspath(__file__))
folder_path = os.path.join(script_dir, 'novel')
output_epub = os.path.join(script_dir, 'warhammer-from-planetary-governor.epub')
book_title = 'warhammer-from-planetary-governor'
author_name = 'Author Name'

# Function for natural sorting (e.g., Chapter 1, Chapter 2 ... Chapter 10)
def natural_sort_key(filename):
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', filename)]

# Helper function to read text files with fallback encodings for Arabic
def read_text_file(file_path):
    # Common encodings for Arabic text files
    encodings_to_try = ['utf-8', 'utf-8-sig', 'cp1256', 'iso-8859-6', 'windows-1252']
    for enc in encodings_to_try:
        try:
            with open(file_path, 'r', encoding=enc) as f:
                text = f.read()
                return text
        except UnicodeDecodeError:
            # If it fails, try the next encoding
            continue

    # Fallback if all strict decodings fail
    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
        return f.read()

# Verify folder exists
if not os.path.exists(folder_path):
    raise FileNotFoundError(f"The specified folder does not exist: {folder_path}")

# Create EPUB instance
book = epub.EpubBook()

# Set metadata
book.set_identifier('id_1234567890')
book.set_title(book_title)
book.set_language('ar')  # Set language to Arabic
book.add_author(author_name)
book.set_direction('rtl')  # Crucial for Arabic: sets Right-to-Left page progression

# Collect text files
files = [f for f in os.listdir(folder_path) if f.lower().endswith('.txt')]
files.sort(key=natural_sort_key)

if not files:
    raise FileNotFoundError(f"No .txt files found in {folder_path}")

print(f"Found {len(files)} files. Compiling EPUB...")

chapters = []
spine = ['nav']

# Define CSS styling optimized for Arabic (RTL)
style = """
@namespace epub "http://www.idpf.org/2007/ops";

body {
    font-family: "Amiri", "Scheherazade", "Traditional Arabic", serif;
    margin: 5%;
    direction: rtl;
    text-align: right;
    line-height: 1.8;
}
h2 {
    text-align: center;
    margin-top: 2em;
    margin-bottom: 1em;
    direction: rtl;
    font-weight: bold;
}
p {
    text-indent: 1.5em;
    margin-bottom: 0.5em;
    direction: rtl;
    text-align: justify;
}
"""

# Create and add CSS item to the book
nav_css = epub.EpubItem(
    uid="style_nav",
    file_name="style/nav.css",
    media_type="text/css",
    content=style
)
book.add_item(nav_css)

# Process chapters
for idx, filename in enumerate(files, start=1):
    file_path = os.path.join(folder_path, filename)

    # Read the text file safely using the fallback function
    raw_text = read_text_file(file_path).strip()

    if not raw_text:
        print(f"Warning: '{filename}' appears to be empty or could not be decoded properly.")
        continue

    # Extract clean title from filename (removes extension)
    chapter_title = os.path.splitext(filename)[0]

    # Convert plain text line breaks into HTML paragraphs with proper HTML escaping
    paragraphs = raw_text.split('\n')
    html_paragraphs = "".join([f"<p>{html.escape(p.strip())}</p>" for p in paragraphs if p.strip()])

    # Build HTML document structure for the chapter
    chapter_content = f"<h2>{html.escape(chapter_title)}</h2>{html_paragraphs}"

    # Create EPUB chapter item
    c = epub.EpubHtml(
        title=chapter_title,
        file_name=f'chap_{idx:03d}.xhtml',
        lang='ar'
    )

    # Proper XHTML structure with RTL direction
    head_content = '<link href="style/nav.css" rel="stylesheet" type="text/css"/>'
    full_html = f"""<html xmlns="http://www.w3.org/1999/xhtml" dir="rtl" lang="ar">
<head>
    <title>{html.escape(chapter_title)}</title>
    {head_content}
</head>
<body>
    {chapter_content}
</body>
</html>"""

    c.set_content(full_html)

    # Add chapter to book
    book.add_item(c)
    chapters.append(c)
    spine.append(c)

# Define Table of Contents and Navigation
book.toc = tuple(chapters)
book.add_item(epub.EpubNcx())
book.add_item(epub.EpubNav())

# Set spine
book.spine = spine

# Write EPUB file to disk
epub.write_epub(output_epub, book, {})
print(f"Successfully created '{output_epub}' with {len(chapters)} chapters!")