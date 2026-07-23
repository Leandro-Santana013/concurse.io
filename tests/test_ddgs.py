from duckduckgo_search import DDGS

ddgs = DDGS()
results = ddgs.text("trabalhador portuario avulso prova ext:pdf", max_results=5)
print(results)
