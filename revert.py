import re

with open(r'c:\Users\Santana\Documents\GitHub\concurse.io\templates\index.html', 'r', encoding='utf-8') as f:
    html = f.read()

html = re.sub(r'<a href="#" class="nav-item" data-view="downloads".*?</a>', '', html, flags=re.DOTALL)
html = re.sub(r'<!-- View: Downloads -->.*?</section>', '', html, flags=re.DOTALL)
html = re.sub(r'<button id="zen-mode-btn".*?</button>', '', html, flags=re.DOTALL)
html = re.sub(r'<!-- Floating Download Widget -->.*?</div>\s*</div>\s*</div>', '', html, flags=re.DOTALL)

with open(r'c:\Users\Santana\Documents\GitHub\concurse.io\templates\index.html', 'w', encoding='utf-8') as f:
    f.write(html)

with open(r'c:\Users\Santana\Documents\GitHub\concurse.io\static\css\style.css', 'r', encoding='utf-8') as f:
    css = f.read()

idx = css.find('/* ===== DOWNLOAD BADGE ===== */')
if idx != -1:
    css = css[:idx].strip()
    if not css.endswith('}'):
        css += '\n}'
    with open(r'c:\Users\Santana\Documents\GitHub\concurse.io\static\css\style.css', 'w', encoding='utf-8') as f:
        f.write(css)

with open(r'c:\Users\Santana\Documents\GitHub\concurse.io\static\js\main.js', 'r', encoding='utf-8') as f:
    js = f.read()

idx = js.find('// ===== GLOBAL DOWNLOAD WIDGET =====')
if idx != -1:
    js_top = js[:idx].strip()
    js_top += "\n\n});\n"
    js_top = re.sub(r'initDownloadWidget\(\);\s*', '', js_top)
    js_top = re.sub(r'initZenMode\(\);\s*', '', js_top)
    js_top = js_top.replace("if (viewId === 'view-downloads') renderDownloadsView();", '')
    js_top = re.sub(r'// Z for Zen mode\s*else if \(e\.key\.toLowerCase\(\) === \'z\'.*?toggleZenMode\(\);\s*', '', js_top)
    with open(r'c:\Users\Santana\Documents\GitHub\concurse.io\static\js\main.js', 'w', encoding='utf-8') as f:
        f.write(js_top)

print("Revertido")
