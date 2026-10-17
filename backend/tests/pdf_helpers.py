"""Generates REAL minimal PDFs in memory, to test validation and
extraction without depending on committed binary files.

pdf_valide() builds the PDF by hand (rather than via pypdf.PdfWriter)
because PdfWriter().add_blank_page() produces pages with NO text content
at all — and index_builder.py needs real extractable text to produce
chunks (a blank page yields 0 passages, which makes the rebuild fail with
IndexInvalide("No passage to index")). pypdf reads this hand-built PDF
correctly (with a minor xref recovery warning, with no impact on
extraction)."""

import io

from pypdf import PdfWriter


def pdf_valide(nb_pages: int = 1, texte: str = "Test text for extraction.") -> bytes:
    pages = []
    for _ in range(nb_pages):
        flux = f"BT /F1 12 Tf 10 150 Td ({texte}) Tj ET".encode("latin-1")
        pages.append(flux)

    objets = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[" + b" ".join(f"{3 + i} 0 R".encode() for i in range(nb_pages)) + b"]/Count "
        + str(nb_pages).encode()
        + b">>",
    ]
    numero_contenu_base = 3 + nb_pages
    for i in range(nb_pages):
        objets.append(
            (
                f"<</Type/Page/Parent 2 0 R/Resources<</Font<</F1 {numero_contenu_base + nb_pages} 0 R>>>>"
                f"/MediaBox[0 0 200 200]/Contents {numero_contenu_base + i} 0 R>>"
            ).encode()
        )
    for flux in pages:
        objets.append(f"<</Length {len(flux)}>>\nstream\n".encode() + flux + b"\nendstream")
    objets.append(b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>")

    corps = b"%PDF-1.4\n"
    for i, contenu in enumerate(objets, start=1):
        corps += f"{i} 0 obj".encode() + contenu + b"endobj\n"
    nb_objets_total = len(objets) + 1
    corps += (
        b"xref\n0 " + str(nb_objets_total).encode() + b"\n"
        b"trailer<</Size " + str(nb_objets_total).encode() + b"/Root 1 0 R>>\n"
        b"startxref\n0\n%%EOF\n"
    )
    return corps


def pdf_chiffre() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.encrypt("password")
    tampon = io.BytesIO()
    writer.write(tampon)
    return tampon.getvalue()
