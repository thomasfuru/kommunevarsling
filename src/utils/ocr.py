import io
import pytesseract
from pdf2image import convert_from_bytes
from pypdf import PdfReader
import sys
import os

# Legger til forelder-mappen i søkestien
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config import Config  # <--- Riktig måte

# ... resten av koden ...

# Konfigurer Tesseract for Windows hvis nødvendig
if Config.TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = Config.TESSERACT_CMD

def les_pdf_tekst(pdf_bytes):
    """
    Prøver først digital lesing, deretter OCR hvis nødvendig.
    """
    # 1. Digital lesing
    tekst_digital = ""
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        for page in reader.pages:
            t = page.extract_text()
            if t: tekst_digital += t + "\n"
    except Exception as e:
        print(f"    (Digital lesing feilet: {e})")

    if len(tekst_digital.strip()) > 50:
        return tekst_digital

    # 2. OCR (Fallback)
    print("    ... Bilde-PDF oppdaget. Kjører OCR (Dette tar tid)...")
    tekst_ocr = ""
    try:
        bilder = convert_from_bytes(pdf_bytes, dpi=300)
        for bilde in bilder:
            tekst_ocr += pytesseract.image_to_string(bilde, lang='nor') + "\n"
    except Exception as e:
        print(f"    (OCR feilet: {e})")
    
    return tekst_ocr