import sys, os, io, html, re, zipfile
import fitz  # PyMuPDF
from PIL import Image
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except Exception:
    pass
from ebooklib import epub

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QFileDialog, QMessageBox, 
                             QInputDialog, QMenu, QGridLayout, QDialog, QListWidget, QDialogButtonBox)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QAction

APP_VERSION = "0.7.1"

# Pillow's registry is keyed by format name, not by file extension: saving with
# format="JPG" raises KeyError, and HEIC is registered as "HEIF". Every save
# must route its extension through this map.
PIL_SAVE_FORMATS = {
    "png": "PNG", "jpg": "JPEG", "jpeg": "JPEG", "webp": "WEBP",
    "tiff": "TIFF", "tif": "TIFF", "bmp": "BMP", "heic": "HEIF", "heif": "HEIF",
}


def pil_format(ext):
    return PIL_SAVE_FORMATS.get(ext.lower(), ext.upper())


def unique_path(path):
    """Returns path, or path with _1, _2 ... appended before the extension.

    Batches are keyed on the input's basename, so converting book.epub and
    book.cbz in one run wrote both to book.pdf and silently kept only the
    second. Every write into a directory the user did not name file-by-file
    goes through here.
    """
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(path)
    counter = 1
    while os.path.exists(f"{stem}_{counter}{ext}"):
        counter += 1
    return f"{stem}_{counter}{ext}"


def new_epub_book(title):
    """An EpubBook with the nav documents already attached.

    ebooklib only writes nav.xhtml / toc.ncx for items that were explicitly
    added, but every spine here starts with 'nav'. Without these two items the
    spine points at a manifest entry that does not exist and the resulting
    EPUB fails validation in strict readers."""
    book = epub.EpubBook()
    book.set_title(title)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    return book

class Worker(QThread):
    success = pyqtSignal()
    error = pyqtSignal(str)
    def __init__(self, func):
        super().__init__()
        self.func = func
    def run(self):
        try:
            self.func()
            self.success.emit()
        except Exception as e:
            self.error.emit(str(e))

class ReorderDialog(QDialog):
    def __init__(self, files, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Drag & Drop to Reorder Files")
        self.setMinimumSize(500, 350)
        self.setStyleSheet("QDialog { background-color: #1e1e2e; color: #cdd6f4; } QListWidget { background-color: #313244; color: #cdd6f4; font-size: 14px; padding: 10px; border-radius: 5px; }")
        layout = QVBoxLayout(self)
        
        label = QLabel("Drag and drop the files below to reorder them before merging:")
        label.setStyleSheet("color: #a6e3a1; font-weight: bold; font-size: 14px;")
        layout.addWidget(label)
        
        self.list_widget = QListWidget()
        self.list_widget.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        for f in files: self.list_widget.addItem(f)
        layout.addWidget(self.list_widget)
        
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.setStyleSheet("QPushButton { background-color: #89b4fa; color: #11111b; font-weight: bold; padding: 8px; border-radius: 4px; }")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        
    def get_ordered_files(self):
        return [self.list_widget.item(i).text() for i in range(self.list_widget.count())]

class EmergePDFMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.current_lang = "EN"
        self.translations = {
            "EN": {
                "subtitle": "The ultimate offline universal format converter.",
                "merge": "Merge Documents", "split": "Split Document", "compress": "Compress File",
                "convert": "Format Conversions ▼", 
                "d2d": "Document to Document", "d2i": "Document to Image",
                "i2d": "Image to Document", "i2i": "Image to Image",
                "footer": f"EmergePDF v{APP_VERSION} | 100% Offline & Private",
                "lang_btn": "[ TR ]", "success": "Success", "error": "Error"
            },
            "TR": {
                "subtitle": "Çevrimdışı evrensel format dönüştürücü.",
                "merge": "Belgeleri Birleştir", "split": "Belge Böl", "compress": "Dosya Sıkıştır",
                "convert": "Format Dönüştür ▼", 
                "d2d": "Belgeden Belgeye", "d2i": "Belgeden Resme",
                "i2d": "Resimden Belgeye", "i2i": "Resimden Resme",
                "footer": f"EmergePDF v{APP_VERSION} | %100 Çevrimdışı ve Güvenli",
                "lang_btn": "[ EN ]", "success": "Başarılı", "error": "Hata"
            }
        }

        self.setWindowTitle("EmergePDF")
        self.setMinimumSize(800, 600)
        self.setStyleSheet("""
            QMainWindow { background-color: #1e1e2e; }
            QLabel { color: #cdd6f4; }
            QPushButton {
                background-color: #89b4fa; color: #11111b;
                border-radius: 8px; padding: 15px; font-weight: bold; font-size: 14px;
            }
            QPushButton:hover { background-color: #b4befe; }
            QPushButton::menu-indicator { image: none; }
            QPushButton#LangBtn { background-color: #313244; color: #cdd6f4; padding: 5px 10px; font-size: 12px; }
            QPushButton#LangBtn:hover { background-color: #45475a; }
            QMenu { background-color: #313244; color: #cdd6f4; border: 1px solid #45475a; border-radius: 4px; padding: 5px; }
            QMenu::item:selected { background-color: #45475a; }
        """)

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)

        top_bar = QHBoxLayout()
        top_bar.addStretch()
        self.btn_lang = QPushButton("[ TR ]")
        self.btn_lang.setObjectName("LangBtn")
        self.btn_lang.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_lang.clicked.connect(self.toggle_language)
        top_bar.addWidget(self.btn_lang)
        layout.addLayout(top_bar)

        self.title_label = QLabel("EmergePDF")
        self.title_label.setFont(QFont("Segoe UI", 32, QFont.Weight.Bold))
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setStyleSheet("color: #cba6f7;")
        layout.addWidget(self.title_label)

        self.subtitle_label = QLabel(self.translations["EN"]["subtitle"])
        self.subtitle_label.setFont(QFont("Segoe UI", 12))
        self.subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.subtitle_label)
        layout.addSpacing(30)

        button_layout = QGridLayout()
        self.btn_merge = QPushButton(self.translations["EN"]["merge"])
        self.btn_split = QPushButton(self.translations["EN"]["split"])
        self.btn_compress = QPushButton(self.translations["EN"]["compress"])
        self.btn_convert = QPushButton(self.translations["EN"]["convert"])
        
        self.convert_menu = QMenu(self)
        self.action_d2d = QAction(self.translations["EN"]["d2d"], self)
        self.action_d2i = QAction(self.translations["EN"]["d2i"], self)
        self.action_i2d = QAction(self.translations["EN"]["i2d"], self)
        self.action_i2i = QAction(self.translations["EN"]["i2i"], self)
        self.convert_menu.addAction(self.action_d2d)
        self.convert_menu.addAction(self.action_d2i)
        self.convert_menu.addAction(self.action_i2d)
        self.convert_menu.addAction(self.action_i2i)
        self.btn_convert.setMenu(self.convert_menu)

        button_layout.addWidget(self.btn_merge, 0, 0)
        button_layout.addWidget(self.btn_split, 0, 1)
        button_layout.addWidget(self.btn_compress, 0, 2)
        button_layout.addWidget(self.btn_convert, 1, 0, 1, 3)
        layout.addLayout(button_layout)
        layout.addStretch()

        self.footer_label = QLabel(self.translations["EN"]["footer"])
        self.footer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.footer_label.setStyleSheet("color: #6c7086; font-size: 10px;")
        layout.addWidget(self.footer_label)

        self.btn_merge.clicked.connect(self.merge_pdfs)
        self.btn_split.clicked.connect(self.split_pdf)
        self.btn_compress.clicked.connect(self.compress_pdf)
        self.action_d2d.triggered.connect(self.doc_to_doc)
        self.action_d2i.triggered.connect(self.doc_to_image)
        self.action_i2d.triggered.connect(self.image_to_doc)
        self.action_i2i.triggered.connect(self.image_to_image)

    def toggle_language(self):
        self.current_lang = "TR" if self.current_lang == "EN" else "EN"
        t = self.translations[self.current_lang]
        self.subtitle_label.setText(t["subtitle"])
        self.btn_merge.setText(t["merge"])
        self.btn_split.setText(t["split"])
        self.btn_compress.setText(t["compress"])
        self.btn_convert.setText(t["convert"])
        self.action_d2d.setText(t["d2d"])
        self.action_d2i.setText(t["d2i"])
        self.action_i2d.setText(t["i2d"])
        self.action_i2i.setText(t["i2i"])
        self.footer_label.setText(t["footer"])
        self.btn_lang.setText(t["lang_btn"])

    def parse_ranges(self, range_str, max_len, label=""):
        """Expands "1-3, 7" into zero-based page indices.

        Raises on anything it cannot honour: returning an empty list instead
        used to make the caller fall through to "no selection", which silently
        wrote the *whole* document when the range was a typo. A descending part
        ("5-2") keeps its descending order, matching parsePageRange() in the
        browser edition so both builds answer the same input the same way.
        """
        where = f" for '{label}'" if label else ""
        pages = []
        for part in range_str.split(','):
            part = part.strip()
            if not part:
                continue
            m = re.fullmatch(r"(\d+)(?:-(\d+))?", part)
            if not m:
                raise ValueError(f"Invalid page range{where}: '{part}'.")
            a = int(m.group(1))
            b = int(m.group(2)) if m.group(2) else a
            if min(a, b) < 1 or max(a, b) > max_len:
                raise ValueError(
                    f"Page {max(a, b)} is out of range{where}: "
                    f"this document has {max_len} page(s).")
            step = 1 if a <= b else -1
            pages.extend(range(a - 1, b - 1 + step, step))
        # dict.fromkeys keeps the requested order while dropping duplicates,
        # which fitz.Document.select() would otherwise reproduce as real pages.
        return list(dict.fromkeys(pages))

    def run_heavy(self, func, success_msg="Operation Complete!"):
        self.buttons_to_lock = [self.btn_merge, self.btn_split, self.btn_compress, self.btn_convert, self.btn_lang]
        for btn in self.buttons_to_lock: btn.setEnabled(False)
        
        self.original_subtitle = self.subtitle_label.text()
        self.dot_count = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate_dots)
        self.timer.start(400)
        
        self.worker = Worker(func)
        self.worker.success.connect(lambda: self.on_heavy_finished(None, success_msg))
        self.worker.error.connect(lambda err: self.on_heavy_finished(err, success_msg))
        self.worker.start()

    def animate_dots(self):
        self.dot_count = (self.dot_count + 1) % 4
        dots = "." * self.dot_count
        self.subtitle_label.setText(f"PROCESSING{dots}")
        self.subtitle_label.setStyleSheet("color: #a6e3a1; font-weight: bold; font-size: 16px;")

    def on_heavy_finished(self, err, success_msg):
        self.timer.stop()
        self.subtitle_label.setText(self.original_subtitle)
        self.subtitle_label.setStyleSheet("")
        for btn in self.buttons_to_lock: btn.setEnabled(True)
        
        if err:
            QMessageBox.critical(self, self.translations[self.current_lang]["error"], str(err))
        else:
            QMessageBox.information(self, self.translations[self.current_lang]["success"], success_msg)

    def merge_pdfs(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Select Files", "", "All Supported (*.pdf *.epub *.mobi *.cbz *.xps *.fb2 *.png *.jpg *.jpeg *.tiff *.heic *.webp)")
        if not files:
            return
        if len(files) < 2:
            QMessageBox.information(
                self, self.translations[self.current_lang]["error"],
                "Select at least two files to merge.")
            return
        dialog = ReorderDialog(files, self)
        if dialog.exec() != QDialog.DialogCode.Accepted: return
        files = dialog.get_ordered_files()
        
        ranges = []
        for f in files:
            name = os.path.basename(f)
            r, ok = QInputDialog.getText(self, "Page Range", f"Pages for '{name}' (e.g. 1-3, 5, or blank for ALL):")
            if not ok: return
            ranges.append(r)
            
        save_path, _ = QFileDialog.getSaveFileName(self, "Save Merged PDF", "merged.pdf", "PDF (*.pdf)")
        if not save_path: return

        def task():
            merged_doc = fitz.open()
            for f, r_str in zip(files, ranges):
                ext = f.lower().split('.')[-1]
                if ext in ['png', 'jpg', 'jpeg', 'tiff', 'webp', 'bmp', 'heic', 'heif']:
                    img = Image.open(f)
                    if img.mode in ("RGBA", "P"): img = img.convert("RGB")
                    b = io.BytesIO(); img.save(b, format="PNG")
                    src = fitz.open("pdf", fitz.open("png", b.getvalue()).convert_to_pdf())
                else:
                    src = fitz.open(f)
                    if not src.is_pdf: src = fitz.open("pdf", src.convert_to_pdf())
                
                if r_str.strip():
                    src.select(self.parse_ranges(
                        r_str, len(src), os.path.basename(f)))
                merged_doc.insert_pdf(src)
                src.close()
            merged_doc.save(save_path)
            merged_doc.close()

        self.run_heavy(task, "Merged strictly into PDF!")

    def split_pdf(self):
        file, _ = QFileDialog.getOpenFileName(self, "Select Document", "", "Documents (*.pdf *.epub *.mobi *.cbz *.xps *.fb2)")
        if not file: return
        mode, ok = QInputDialog.getItem(self, "Split Mode", "Select Split Mode:", ["Extract specific pages to PDF", "Rip ALL pages to JPGs"], 0, False)
        if not ok: return
        name = os.path.splitext(os.path.basename(file))[0]

        if "JPG" in mode:
            save_dir = QFileDialog.getExistingDirectory(self, "Select Save Directory")
            if not save_dir: return
            def task():
                src = fitz.open(file)
                for i in range(len(src)):
                    pix = src.load_page(i).get_pixmap(dpi=300)
                    pix.save(unique_path(
                        os.path.join(save_dir, f"{name}_page_{i+1}.jpg")))
                src.close()
            self.run_heavy(task, "All pages ripped to JPG!")
        else:
            page_str, ok = QInputDialog.getText(self, "Split Ranges", "Enter comma-separated ranges to split into MULTIPLE files (e.g., 1-100, 101-200):")
            if not ok or not page_str: return
            save_dir = QFileDialog.getExistingDirectory(self, "Select Save Directory for the split PDFs")
            if not save_dir: return
            def task():
                src = fitz.open(file)
                if not src.is_pdf: src = fitz.open("pdf", src.convert_to_pdf())
                
                parts = [p.strip() for p in page_str.split(',') if p.strip()]
                if not parts: raise Exception("No valid ranges provided.")

                written = 0
                failures = []
                for part in parts:
                    temp = fitz.open()
                    try:
                        pages = self.parse_ranges(part, len(src))
                        for page in pages:
                            temp.insert_pdf(src, from_page=page, to_page=page)
                        label = (f"{pages[0]+1}-{pages[-1]+1}"
                                 if len(pages) > 1 else str(pages[0] + 1))
                        temp.save(unique_path(
                            os.path.join(save_dir, f"{name}_split_{label}.pdf")))
                        written += 1
                    except Exception as exc:
                        failures.append(f"{part}: {exc}")
                    finally:
                        temp.close()
                src.close()
                if not written:
                    raise Exception("No ranges could be split.\n\n"
                                    + "\n".join(failures))
                if failures:
                    raise Exception(
                        f"Wrote {written} file(s), but these ranges failed:\n\n"
                        + "\n".join(failures))
            self.run_heavy(task, "Successfully split into multiple PDFs!")

    def compress_pdf(self):
        file, _ = QFileDialog.getOpenFileName(self, "Select File", "", "Files (*.pdf *.png *.jpg *.jpeg *.webp *.heic *.tiff)")
        if not file: return
        
        ratio, ok = QInputDialog.getItem(self, "Compression Level", "Select compression level:", 
                                         ["Low (Better Quality)", "Medium", "High", "Extreme (Smallest File)"], 2, False)
        if not ok: return
        
        ext = file.lower().split('.')[-1]
        save_path, _ = QFileDialog.getSaveFileName(self, "Save Compressed", f"compressed.{ext}", f"File (*.{ext})")
        if not save_path: return
        
        selected_level = ratio.split(" ")[0]
        pdf_garbage = {"Low": 1, "Medium": 2, "High": 3, "Extreme": 4}
        img_quality = {"Low": 85, "Medium": 65, "High": 45, "Extreme": 20}
        
        def task():
            if ext != "pdf" and ext not in PIL_SAVE_FORMATS:
                raise ValueError(
                    f"Cannot compress a .{ext} file. Supported: pdf, "
                    + ", ".join(sorted(PIL_SAVE_FORMATS)) + ".")
            if ext == "pdf":
                doc = fitz.open(file)
                doc.save(save_path, garbage=pdf_garbage[selected_level], deflate=True)
                doc.close()
            else:
                img = Image.open(file)
                if img.mode in ("RGBA", "P") and ext in ("jpeg", "jpg", "heic", "heif", "bmp"):
                    img = img.convert("RGB")
                save_fmt = pil_format(ext)
                save_kwargs = {}
                if ext in ("jpg", "jpeg", "webp", "heic", "heif"):
                    save_kwargs["quality"] = img_quality[selected_level]
                if ext in ("jpg", "jpeg", "png"):
                    save_kwargs["optimize"] = True
                img.save(save_path, format=save_fmt, **save_kwargs)
        self.run_heavy(task, f"Compressed successfully at {selected_level} level!")

    def doc_to_doc(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Select Documents", "", "Documents (*.pdf *.epub *.mobi *.cbz *.xps *.fb2)")
        if not files: return
        target, ok = QInputDialog.getItem(self, "Format", "Convert to:", ["pdf", "epub", "cbz"], 0, False)
        if not ok: return
        save_dir = QFileDialog.getExistingDirectory(self, "Select Save Directory")
        if not save_dir: return
        def task():
            for f in files:
                name = os.path.splitext(os.path.basename(f))[0]
                out_path = unique_path(os.path.join(save_dir, f"{name}.{target}"))
                src = fitz.open(f)
                if target == "pdf":
                    if not src.is_pdf:
                        pdf_doc = fitz.open("pdf", src.convert_to_pdf())
                        pdf_doc.save(out_path)
                        pdf_doc.close()
                    else:
                        src.save(out_path)
                elif target == "epub":
                    book = new_epub_book(name)
                    text = "\n".join([page.get_text() for page in src])
                    c = epub.EpubHtml(title="Content", file_name="main.xhtml")
                    # Page text is re-parsed as XHTML on write, so anything
                    # shaped like a tag is swallowed unless it is escaped.
                    c.content = (f"<h1>{html.escape(name)}</h1>"
                                 f"<pre>{html.escape(text)}</pre>")
                    book.add_item(c)
                    book.toc = (c,)
                    book.spine = ['nav', c]
                    epub.write_epub(out_path, book)
                elif target == "cbz":
                    with zipfile.ZipFile(out_path, 'w') as zf:
                        for i in range(len(src)):
                            pix = src.load_page(i).get_pixmap(dpi=150)
                            zf.writestr(f"page_{i}.png", pix.tobytes("png"))
                src.close()
        self.run_heavy(task, "Converted successfully!")

    def doc_to_image(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Select Documents", "", "Documents (*.pdf *.epub *.mobi *.cbz *.xps *.fb2)")
        if not files: return
        target, ok = QInputDialog.getItem(self, "Format", "Convert pages to:", ["png", "jpeg", "webp", "tiff", "bmp", "heic"], 0, False)
        if not ok: return
        save_dir = QFileDialog.getExistingDirectory(self, "Select Save Directory")
        if not save_dir: return
        def task():
            for f in files:
                name = os.path.splitext(os.path.basename(f))[0]
                src = fitz.open(f)
                for i in range(len(src)):
                    pix = src.load_page(i).get_pixmap(dpi=300)
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    img_out = unique_path(
                        os.path.join(save_dir, f"{name}_page_{i+1}.{target}"))
                    img.save(img_out, pil_format(target))
                src.close()
        self.run_heavy(task, "Ripped to Images successfully!")

    def image_to_doc(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Select Images", "", "Images (*.png *.jpg *.jpeg *.tiff *.webp *.bmp *.heic *.heif *.gif)")
        if not files: return
        target, ok = QInputDialog.getItem(self, "Format", "Combine images into:", ["pdf", "epub", "cbz"], 0, False)
        if not ok: return
        save_path, _ = QFileDialog.getSaveFileName(self, f"Save {target.upper()}", f"images.{target}", f"{target.upper()} (*.{target})")
        if not save_path: return
        def task():
            if target == "pdf":
                doc = fitz.open()
                for f in files:
                    img = Image.open(f)
                    if img.mode in ("RGBA", "P"): img = img.convert("RGB")
                    b = io.BytesIO(); img.save(b, format="PNG")
                    img_doc = fitz.open("pdf", fitz.open("png", b.getvalue()).convert_to_pdf())
                    doc.insert_pdf(img_doc); img_doc.close()
                doc.save(save_path); doc.close()
            elif target == "epub":
                book = new_epub_book("Image Book")
                spine = ['nav']
                chapters = []
                for i, f in enumerate(files):
                    img = Image.open(f)
                    if img.mode in ("RGBA", "P"): img = img.convert("RGB")
                    b = io.BytesIO(); img.save(b, format="JPEG")
                    img_item = epub.EpubItem(uid=f"img_{i}", file_name=f"img_{i}.jpg", media_type="image/jpeg", content=b.getvalue())
                    book.add_item(img_item)
                    c = epub.EpubHtml(title=f"Page {i+1}", file_name=f"page_{i}.xhtml")
                    c.content = f'<img src="img_{i}.jpg"/>'
                    book.add_item(c); spine.append(c); chapters.append(c)
                book.toc = tuple(chapters)
                book.spine = spine
                epub.write_epub(save_path, book)
            elif target == "cbz":
                # Pad the index so readers order pages correctly, and so two
                # source files with the same basename cannot collide.
                with zipfile.ZipFile(save_path, 'w') as zf:
                    for i, f in enumerate(files):
                        zf.write(f, f"{i+1:04d}_{os.path.basename(f)}")
        self.run_heavy(task, "Combined successfully!")

    def image_to_image(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Select Images", "", "Images (*.png *.jpg *.jpeg *.tiff *.webp *.bmp *.heic *.heif *.gif)")
        if not files: return
        target, ok = QInputDialog.getItem(self, "Format", "Convert to:", ["png", "jpeg", "webp", "tiff", "bmp", "heic"], 0, False)
        if not ok: return
        save_dir = QFileDialog.getExistingDirectory(self, "Select Save Directory")
        if not save_dir: return
        save_fmt = pil_format(target)
        count = len(files)
        def task():
            for f in files:
                img = Image.open(f)
                if img.mode in ("RGBA", "P") and target in ("jpeg", "heic", "bmp"):
                    img = img.convert("RGB")
                name = os.path.splitext(os.path.basename(f))[0]
                out_path = unique_path(os.path.join(save_dir, f"{name}.{target}"))
                img.save(out_path, format=save_fmt)
        self.run_heavy(task, f"Transcoded {count} image(s) successfully!")

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName("EmergePDF")
    # Wayland takes the xdg-shell app_id from the desktop file name; without
    # this Qt falls back to the interpreter basename ("python") and the window
    # never matches emerge-pdf.desktop, so the taskbar shows a generic icon.
    app.setDesktopFileName("emerge-pdf")
    window = EmergePDFMainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
