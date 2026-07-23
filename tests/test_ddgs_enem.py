from duckduckgo_search import DDGS
ddgs = DDGS()
results = ddgs.text("enem prova concurso pdf", max_results=30)
found = 0
for r in results:
    if '.pdf' in r['href'].lower():
        print("PDF:", r['href'])
        found += 1
if found == 0:
    print("NO PDF FOUND")
