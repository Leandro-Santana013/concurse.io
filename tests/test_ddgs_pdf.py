from duckduckgo_search import DDGS

ddgs = DDGS()
results = ddgs.text("trabalhador portuario avulso prova filetype:pdf", max_results=20)
for r in results:
    if '.pdf' in r['href'].lower():
        print("PDF:", r['href'])
