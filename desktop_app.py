"""Small Tk desktop interface for converting TXT novels to EPUB."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
import zipfile
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from epub_converter import create_epub, natural_sort_key


class TxtToEpubApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("TXT to EPUB")
        self.root.geometry("760x640")
        self.root.minsize(620, 480)
        self.files: list[Path] = []
        self.results: queue.Queue[tuple[bool, str]] = queue.Queue()

        self.title_var = tk.StringVar()
        self.author_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.mode_var = tk.StringVar(value="separate")
        self.output_custom = False
        self.sort_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="Add one or more TXT files to begin.")

        self._build_ui()
        self.root.after(150, self._check_results)

    def _build_ui(self) -> None:
        container = ttk.Frame(self.root, padding=16)
        container.pack(fill="both", expand=True)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(2, weight=1)

        ttk.Label(
            container,
            text="Turn TXT novels into an organized EPUB",
            font=("Segoe UI", 16, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            container,
            text="Arabic and English chapter headings are detected automatically. "
            "Review the file order before converting.",
            wraplength=680,
        ).grid(row=1, column=0, sticky="w", pady=(4, 12))

        file_frame = ttk.LabelFrame(
            container, text="TXT files (top to bottom = book order when combining)", padding=10
        )
        file_frame.grid(row=2, column=0, sticky="nsew")
        file_frame.columnconfigure(0, weight=1)
        file_frame.rowconfigure(0, weight=1)

        self.file_list = tk.Listbox(file_frame, selectmode=tk.EXTENDED, height=10)
        self.file_list.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(file_frame, orient="vertical", command=self.file_list.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.file_list.configure(yscrollcommand=scrollbar.set)

        actions = ttk.Frame(file_frame)
        actions.grid(row=0, column=2, sticky="ns", padx=(10, 0))
        ttk.Button(actions, text="Add files...", command=self._add_files).pack(fill="x", pady=(0, 5))
        ttk.Button(actions, text="Add folder...", command=self._add_folder).pack(fill="x", pady=5)
        ttk.Button(actions, text="Sort files", command=self._sort_files).pack(fill="x", pady=5)
        ttk.Button(actions, text="Move up", command=lambda: self._move_selected(-1)).pack(fill="x", pady=5)
        ttk.Button(actions, text="Move down", command=lambda: self._move_selected(1)).pack(fill="x", pady=5)
        ttk.Button(actions, text="Remove", command=self._remove_selected).pack(fill="x", pady=5)
        ttk.Button(actions, text="Clear", command=self._clear_files).pack(fill="x", pady=5)

        mode_frame = ttk.LabelFrame(container, text="Conversion mode", padding=8)
        mode_frame.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        ttk.Radiobutton(
            mode_frame,
            text="Create one EPUB per TXT file",
            value="separate",
            variable=self.mode_var,
            command=self._mode_changed,
        ).pack(side="left", padx=(0, 20))
        ttk.Radiobutton(
            mode_frame,
            text="Combine selected files into one EPUB",
            value="combine",
            variable=self.mode_var,
            command=self._mode_changed,
        ).pack(side="left")

        details = ttk.LabelFrame(container, text="EPUB details", padding=10)
        details.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        details.columnconfigure(1, weight=1)
        ttk.Label(details, text="Book title").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(details, textvariable=self.title_var).grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Label(details, text="Author (optional)").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(details, textvariable=self.author_var).grid(row=1, column=1, sticky="ew", pady=4)
        self.output_label = ttk.Label(details, text="Output folder")
        self.output_label.grid(row=2, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(details, textvariable=self.output_var).grid(row=2, column=1, sticky="ew", pady=4)
        self.browse_button = ttk.Button(details, text="Browse...", command=self._choose_output)
        self.browse_button.grid(
            row=2, column=2, padx=(8, 0), pady=4
        )

        options = ttk.Frame(container)
        options.grid(row=5, column=0, sticky="ew", pady=(8, 0))
        ttk.Checkbutton(
            options,
            text="Sort detected chapters by chapter number within each file",
            variable=self.sort_var,
        ).pack(side="left")

        footer = ttk.Frame(container)
        footer.grid(row=6, column=0, sticky="ew", pady=(12, 0))
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, textvariable=self.status_var).grid(row=0, column=0, sticky="w")
        self.convert_button = ttk.Button(footer, text="Create EPUB", command=self._convert)
        self.convert_button.grid(row=0, column=1, sticky="e")

    def _refresh_files(self) -> None:
        self.file_list.delete(0, tk.END)
        for path in self.files:
            self.file_list.insert(tk.END, str(path))
        if self.files:
            self.status_var.set(f"{len(self.files)} TXT file(s) ready.")
        else:
            self.status_var.set("Add one or more TXT files to begin.")

    def _add_paths(self, paths: tuple[str, ...] | list[Path]) -> None:
        for item in paths:
            path = Path(item)
            if path.is_file() and path.suffix.casefold() == ".txt" and path not in self.files:
                self.files.append(path)
        self._refresh_files()
        if self.files and not self.title_var.get().strip():
            self.title_var.set(self.files[0].stem)
        if self.files and not self.output_var.get().strip():
            self.output_var.set(self._default_output())

    def _add_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Choose TXT files",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        self._add_paths(paths)

    def _add_folder(self) -> None:
        folder = filedialog.askdirectory(title="Choose a folder containing TXT files")
        if folder:
            paths = sorted(Path(folder).glob("*.txt"), key=lambda path: natural_sort_key(path.name))
            self._add_paths(paths)

    def _sort_files(self) -> None:
        self.files.sort(key=lambda path: natural_sort_key(path.name))
        self._refresh_files()

    def _move_selected(self, direction: int) -> None:
        selected = list(self.file_list.curselection())
        if not selected:
            return
        selected_files = [self.files[index] for index in selected]
        order = selected_files if direction < 0 else list(reversed(selected_files))
        for path in order:
            index = self.files.index(path)
            target = index + direction
            if 0 <= target < len(self.files) and self.files[target] not in selected_files:
                self.files[index], self.files[target] = self.files[target], self.files[index]
        self._refresh_files()
        for path in selected_files:
            self.file_list.selection_set(self.files.index(path))

    def _remove_selected(self) -> None:
        selected = set(self.file_list.curselection())
        self.files = [path for index, path in enumerate(self.files) if index not in selected]
        self._refresh_files()

    def _clear_files(self) -> None:
        self.files.clear()
        self._refresh_files()

    def _default_output(self) -> str:
        folder = self.files[0].parent / "epub-output"
        if self.mode_var.get() == "combine":
            return str(folder / self.files[0].with_suffix(".epub").name)
        return str(folder)

    def _mode_changed(self) -> None:
        self.output_label.configure(
            text="Output folder" if self.mode_var.get() == "separate" else "Save as"
        )
        if self.files and not self.output_custom:
            self.output_var.set(self._default_output())

    def _choose_output(self) -> None:
        initial = self.output_var.get()
        if self.mode_var.get() == "separate":
            path = filedialog.askdirectory(
                title="Choose output folder",
                initialdir=initial if Path(initial).is_dir() else None,
            )
        else:
            path = filedialog.asksaveasfilename(
                title="Save EPUB",
                defaultextension=".epub",
                initialfile=Path(initial).name if initial else "book.epub",
                initialdir=str(Path(initial).parent) if initial else None,
                filetypes=[("EPUB files", "*.epub")],
            )
        if path:
            self.output_var.set(path)
            self.output_custom = True

    def _convert(self) -> None:
        if not self.files:
            messagebox.showerror("No input files", "Add at least one TXT file.")
            return
        output_text = self.output_var.get().strip()
        if not output_text:
            messagebox.showerror("Choose an output location", "Choose where to save the EPUB file(s).")
            return
        output = Path(output_text)
        combine = self.mode_var.get() == "combine"
        if combine and output.suffix.casefold() != ".epub":
            messagebox.showerror("Choose an output file", "Choose where to save the .epub file.")
            return
        title = self.title_var.get().strip() or self.files[0].stem
        author = self.author_var.get().strip()
        input_files = self.files.copy()
        sort_by_number = self.sort_var.get()
        self.convert_button.configure(state="disabled")
        self.status_var.set("Reading files and creating EPUB...")

        def worker() -> None:
            try:
                if combine:
                    count = create_epub(
                        input_files, output, title, author, sort_by_number=sort_by_number
                    )
                    self.results.put((True, f"{count:,} chapters saved to {output}"))
                else:
                    output.mkdir(parents=True, exist_ok=True)
                    destinations = [output / f"{path.stem}.epub" for path in input_files]
                    if len(set(destinations)) != len(destinations):
                        raise ValueError(
                            "Some selected files have the same name. Rename them or combine them "
                            "into one EPUB to avoid overwriting a result."
                        )
                    completed: list[str] = []
                    failures: list[str] = []
                    for path, destination in zip(input_files, destinations):
                        try:
                            count = create_epub(
                                [path],
                                destination,
                                title if len(input_files) == 1 else path.stem,
                                author,
                                sort_by_number=sort_by_number,
                            )
                            completed.append(f"{destination.name} ({count:,} chapters)")
                        except (OSError, UnicodeError, ValueError, zipfile.BadZipFile) as error:
                            failures.append(f"{path.name}: {error}")
                    summary = f"Created {len(completed)} of {len(input_files)} EPUB file(s)."
                    if completed:
                        summary += "\n" + "\n".join(completed)
                    if failures:
                        summary += "\n\nFailed:\n" + "\n".join(failures)
                    self.results.put((not failures, summary))
            except (OSError, UnicodeError, ValueError, zipfile.BadZipFile) as error:
                self.results.put((False, str(error)))
            except Exception as error:
                self.results.put((False, f"Unexpected conversion error: {error}"))

        threading.Thread(target=worker, daemon=True).start()

    def _check_results(self) -> None:
        try:
            success, message = self.results.get_nowait()
        except queue.Empty:
            pass
        else:
            self.convert_button.configure(state="normal")
            self.status_var.set(message)
            if success:
                messagebox.showinfo("EPUB created", message)
            else:
                messagebox.showerror("Conversion failed", message)
        self.root.after(150, self._check_results)

def main() -> None:
    root = tk.Tk()
    TxtToEpubApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
