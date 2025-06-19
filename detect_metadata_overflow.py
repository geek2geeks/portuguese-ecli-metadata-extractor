#!/usr/bin/env python3
"""Detect PDFs whose page-1 metadata table continues on later pages.

Heuristic:
 1. For each PDF, extract page-1 text and text from page 2.
 2. Look for any metadata field labels (Relator, Nº do Documento, …) on page > 1.
 3. If any label occurs after page 1, mark PDF as *overflow*.

Run with many workers e.g.
   python detect_metadata_overflow.py --pdf-root R:/pdfs --workers 90 --out report_overflow.csv
"""
import argparse, concurrent.futures, re, json, csv, sys
from pathlib import Path
import fitz  # PyMuPDF – fast

FIELD_LABELS = [
    # Core left-column / right-column metadata labels that rarely appear in body text.
    "Relator", "Nº do Documento", "Apenso", "Data do Acordão",
    "Data de decisão sumária", "Votação", "Tribunal de recurso",
    "Processo de recurso", "Recurso", "Referência de processo de recurso",
    "Nível de acesso", "Meio Processual", "Indicações eventuais",
    "Área Temática", "Referências Internacionais", "Jurisprudência Nacional",
    "Legislação Comunitária", "Legislação Estrangeira", "Descritores",
]
# Require at least this many distinct metadata labels on the same later page to
# treat the PDF as overflowing. 3 is a good compromise between recall and precision.
MIN_LABELS_FOR_OVERFLOW = 3  # legacy fallback

# High-confidence label whose continuation indicates overflow
DESCRITORES_PATTERN = re.compile(r"^Descritores\b", re.I | re.M)
# Page-2 section titles that guarantee normal flow (metadata finished)
SECTION_START_PATTERN = re.compile(r"^(Sumário|Decisão Integral)", re.I | re.M)

LABEL_PATTERN = re.compile(r"^(?:" + "|".join(re.escape(l) for l in FIELD_LABELS) + ")", re.I | re.M)


def check_pdf(pdf_path: Path) -> dict:
    """Return dict with overflow flag and evidence page# if any."""
    try:
        doc = fitz.open(pdf_path)
        overflow_page = None
        page1_text = doc.load_page(0).get_text("text")
        page1_has_descritores = bool(DESCRITORES_PATTERN.search(page1_text))

        # Determine overflow based on Descritores presence/continuation
        overflow = not page1_has_descritores

        if not overflow:
            for i in range(1, doc.page_count):  # start at page 2 (index 1)
                txt = doc.load_page(i).get_text("text")

                # If this page clearly starts a new section, metadata finished.
                if SECTION_START_PATTERN.search(txt):
                    break

                # Descritores label appears again ⇒ metadata continues.
                if DESCRITORES_PATTERN.search(txt):
                    overflow = True
                    overflow_page = i + 1
                    break

                # Fallback heuristic: many other labels (legacy logic)
                matches = set(m.group(0).lower() for m in LABEL_PATTERN.finditer(txt))
                if len(matches) >= MIN_LABELS_FOR_OVERFLOW:
                    overflow = True
                    overflow_page = i + 1
                    break

        return {
            "file": str(pdf_path),
            "total_pages": doc.page_count,
            "overflow": overflow,
            "first_label_page": overflow_page or "",
        }
    except Exception as e:
        return {"file": str(pdf_path), "overflow": "ERROR", "error": str(e)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf-root", required=True, help="Root directory containing PDFs (recursively searched)")
    ap.add_argument("--workers", type=int, default=90)
    ap.add_argument("--out", default="overflow_report.csv")
    args = ap.parse_args()

    pdf_paths = list(Path(args.pdf_root).rglob("*.pdf"))
    print(f"Scanning {len(pdf_paths)} PDFs… with {args.workers} workers")

    results = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as ex:
        for res in ex.map(check_pdf, pdf_paths, chunksize=50):
            results.append(res)

    overflow = [r for r in results if r["overflow"] is True]
    print(f"Detected {len(overflow)} PDFs with metadata beyond first page.")

    # write CSV
    fieldnames = ["file", "total_pages", "overflow", "first_label_page", "error"]
    with open(args.out, "w", newline='', encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in results:
            writer.writerow(row)
    print(f"Report written to {args.out}")


if __name__ == "__main__":
    main()
