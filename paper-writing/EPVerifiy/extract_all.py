import PyPDF2
import sys

def extract_all(pdf_path, txt_path):
    try:
        with open(pdf_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            text = ""
            for i in range(len(reader.pages)):
                text += reader.pages[i].extract_text() + "\n"
            
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write(text)
        print(f"Successfully extracted all pages to {txt_path}")
    except Exception as e:
        print(f"Error extracting: {e}")

extract_all(r"c:\Users\yrl\Desktop\research\DNS-verification\EPVerifiy\nsdi24-zhao.pdf", "nsdi_all.txt")
