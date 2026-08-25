import re
header_pat = re.compile(
    r'(?i)(?:^|\n|\.\s+|\s{2,})(?:(?:QUEST[AÃ\?]?O\s+|ITEM\s+)(0*\d{1,3})[ \t]*(?:[\.\-–—:\)]|\n+|[ \t]+)|(0*\d{1,3})[ \t]*(?:[\.\-–—:\)]|\n+|\t+|[ \t]+(?=[A-Za-z\u00C0-\u00DC\"\'\(\[]))[ \t]*|\((0*\d{1,3})\)[ \t]+|(?<=\n)\s*(0*\d{1,3})\s*(?=\n|\t))'
)
sample = '''
1 Pode-se inferir do texto que
(A) opcao A
(B) opcao B
2 No período tal
(A) opcao A2
3 O emprego da crase
(A) opcao A3
'''
matches = list(header_pat.finditer(sample))
print('Total matches found:', len(matches))
for m in matches:
    q_str = m.group(1) or m.group(2) or m.group(3) or m.group(4)
    print(f'Match: Q{q_str} at span {m.span()}')
