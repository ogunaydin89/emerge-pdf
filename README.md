# 📄 EmergePDF

> **The ultimate offline universal document and image converter.**

A 100% local, privacy-first document and image converter built with PyQt6. No cloud uploads, no telemetry, no accounts — everything runs natively on your machine.

---

## ✨ Features

| Tool | Description |
|:---|:---|
| **Merge** | Combine PDFs, e-books, and images into a single PDF with drag-and-drop reordering and per-file page range selection |
| **Split** | Extract page ranges into separate PDFs, or rip every page to individual JPGs at 300 DPI |
| **Compress** | 4-level compression (Low → Extreme) for PDFs and images |
| **Doc → Doc** | Convert between PDF, EPUB, and CBZ |
| **Doc → Image** | Rip document pages to PNG, JPEG, WebP, TIFF, BMP, or HEIC |
| **Image → Doc** | Combine images into PDF, EPUB, or CBZ |
| **Image → Image** | Transcode between PNG, JPEG, WebP, TIFF, BMP, and HEIC |

---

## 📁 Supported Formats

- **Document Input:** PDF, EPUB, MOBI, CBZ, XPS, FB2  
- **Image Input:** PNG, JPG, JPEG, TIFF, WebP, BMP, HEIC, HEIF, GIF  

---

## 🌐 Browser Edition

[`web/index.html`](web/index.html) is a single self-contained HTML file — every
library is inlined, so it makes **zero network requests** and runs by opening the
file in any modern browser on any OS, with no Python and no install. It declares
`<!DOCTYPE html>`, so it renders in standards mode rather than quirks mode, which
is what keeps its layout identical across engines.

It is a deliberate subset of the desktop application. The desktop build stands on
PyMuPDF, Pillow, pillow-heif and EbookLib; the browser build stands on pdf-lib,
pdf.js and JSZip, and those libraries cannot reach everywhere the native stack does.

| Tool | Desktop | Browser |
|:---|:---|:---|
| **Merge** | PDF, EPUB, MOBI, CBZ, XPS, FB2 + images; drag-reorder; per-file page ranges | PDF, PNG, JPG only; no per-file ranges |
| **Split** | Ranges into *separate* PDFs, or rip all pages to 300 DPI JPGs | Extract pages into a single PDF |
| **Compress** | 4 levels, PDFs and images | — |
| **Doc → Doc** | PDF, EPUB, CBZ | PDF ⇄ CBZ only (adds CBZ *unpacking*, which the desktop build lacks) |
| **Doc → Image** | PNG, JPEG, WebP, TIFF, BMP, HEIC at 300 DPI | PNG, JPG, delivered as a ZIP |
| **Image → Doc** | PDF, EPUB, CBZ | PDF only |
| **Image → Image** | PNG, JPEG, WebP, TIFF, BMP, HEIC | PNG, JPG, WebP |

Why the gaps:

- **pdf-lib writes PDFs but cannot rasterize; pdf.js rasterizes but cannot write.**
  Every browser tool is stitched from both, which is what narrows each one.
- **No EPUB / MOBI / XPS / FB2 parser exists in that stack**, so e-book input and
  EPUB output are unavailable client-side.
- **Canvas encodes only PNG, JPEG and WebP** — TIFF, BMP and HEIC are out of reach.
- **Compress is omitted on purpose.** PyMuPDF's `garbage=1..4` performs object-stream
  deduplication and xref rebuilding; pdf-lib exposes no equivalent, and a "compress"
  that merely re-saves the file would be misleading rather than useful.

---

## 🚀 Quick Start

### 1. Launch EmergePDF
```bash
./run.sh
```
*The launcher automatically verifies the isolated virtualenv, bootstraps missing dependencies, and opens the application.*

### 2. Manual Execution
```bash
./.venv/bin/python src/main.py
```

---

## 🌐 Language Support

Built-in English / Turkish toggle via the `[ TR ]` / `[ EN ]` button in the top-right corner.

---

## 🛠️ Requirements & Frozen Dependencies

- Python 3.12+ (tested on Python 3.14)
- PyQt6
- PyMuPDF (`fitz`)
- Pillow + pillow-heif
- EbookLib

All exact production dependencies are locked in [`requirements_freeze.txt`](requirements_freeze.txt).

---

## 📄 License

MIT © Ogün Aydın ([ogunaydin89](https://github.com/ogunaydin89))

This project uses **PyQt6**, which is licensed under GPL-3.0 and is installed separately with pip (it is never included in this repository). The code here is MIT; a packaged build that bundles PyQt6 (e.g. an .exe or AppImage) must be distributed under GPL-3.0.
