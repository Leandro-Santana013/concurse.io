import os
import sys
import fitz

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

doc = fitz.open('pdfs/19_1787612141.pdf')
print(f"Total pages: {len(doc)}")
for i in range(len(doc)):
    print(f"\n{'='*30} PAGE {i+1} {'='*30}")
    print(doc[i].get_text())
