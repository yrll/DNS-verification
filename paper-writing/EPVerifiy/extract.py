import PyPDF2
import sys

def extract_text(pdf_path, txt_path, num_pages=3):
    try:
        with open(pdf_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            text = ""
            for i in range(min(num_pages, len(reader.pages))):
                text += reader.pages[i].extract_text() + "\n"
            
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write(text)
        print(f"Successfully extracted {pdf_path} to {txt_path}")
    except Exception as e:
        print(f"Error extracting {pdf_path}: {e}")

extract_text(r"c:\Users\yrl\Desktop\research\DNS-verification\EPVerifiy\flash-sigcomm22.pdf", "flash.txt", 4)
extract_text(r"c:\Users\yrl\Desktop\research\DNS-verification\EPVerifiy\nsdi24-zhao.pdf", "nsdi.txt", 4)
