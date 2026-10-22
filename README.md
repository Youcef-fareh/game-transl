# TXT to EPUB

A small Windows desktop app for turning English or Arabic TXT novels into organized EPUB books. The app uses Python's standard library only; the older command-line scripts in this repository remain available separately.

## What it does

- Add one or more TXT files, or add every TXT file in a folder.
- Convert each file to a separate EPUB, or combine selected files into one book.
- Review and change file order, or sort names naturally (`Chapter 2` before `Chapter 10`).
- Detect common English and Arabic chapter headings, including Arabic-Indic numbers.
- Optionally sort detected chapters by number within each file.
- Keep Arabic chapters right-to-left and English chapters left-to-right, with an EPUB contents page.
- Read UTF-8, UTF-8 with BOM, and common Arabic Windows encodings.

Files without detectable chapter headings are included as one chapter named after the file. Batch conversion creates one EPUB per TXT in the chosen output folder. When combining files, choose only files belonging to the same book and use the list controls to set their order.

## Run from source on Windows

Python 3.10 or newer with Tk support is required. The desktop app has no third-party runtime dependencies.

```powershell
.\.venv\Scripts\python.exe .\desktop_app.py
```

In the app, add the source TXT file(s), choose whether to create separate EPUBs or combine the files, check their order if combining, choose the output folder or `.epub` path, and click **Create EPUB**.

## Get a standalone Windows app from GitHub Actions

The **Build standalone Windows app** workflow builds `TxtToEpub.exe` on GitHub Actions. It is a portable, single-file executable; users do not need to install Python or run a post-install step.

1. Push to the `main` or `master` branch, or start the workflow manually from the repository's **Actions** tab.
2. Open the completed workflow run.
3. Download the `TxtToEpub-Windows` artifact.
4. Extract the ZIP and run `TxtToEpub.exe`.

The executable is built by GitHub Actions, not as part of the local development instructions.

## Tests

Run the converter tests with:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```
