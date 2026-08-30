import os
import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath('.'))

import fitz

doc = fitz.open('pdfs/56_gab_1788095849.pdf')
page = doc[0]
tabs = page.find_tables()
print("Tables count:", len(tabs.tables) if hasattr(tabs, 'tables') else 0)
for t in (tabs.tables if hasattr(tabs, 'tables') else []):
    print("Extracted table:")
    for row in t.extract():
        print(row)
print("\nRaw text:")
print(page.get_text())
