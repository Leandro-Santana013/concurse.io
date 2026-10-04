import assert from 'node:assert/strict';
import { readFile, stat } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const landing = fileURLToPath(new URL('../', import.meta.url));
const output = path.join(landing, 'dist');
const html = await readFile(path.join(output, 'index.html'), 'utf8');
const manifest = JSON.parse(await readFile(path.join(output, 'releases.json'), 'utf8'));
assert(!/\{\{.*?\}\}/.test(html), 'Variável de build não resolvida.');
assert(/<html[^>]*lang="pt-BR"/.test(html), 'Idioma ausente.');
assert.equal((html.match(/<h1[\s>]/g) || []).length, 1, 'A página deve ter um título principal.');
assert(/name="viewport"/.test(html), 'Configuração de viewport ausente.');
assert(/rel="canonical"/.test(html), 'URL canônica ausente.');
assert(/<main[\s>]/.test(html), 'Área principal ausente.');
const socialCard = html.match(/property="og:image" content="([^"]+)"/);
assert(socialCard, 'Imagem de compartilhamento ausente.');
const socialImage = new URL(socialCard[1]);
assert.equal(socialImage.pathname.split('/').at(-1), 'social-card.png', 'Imagem social deve ser PNG.');
assert((await stat(path.join(output, 'assets/social-card.png'))).size > 0, 'Imagem social vazia.');
const ids = [...html.matchAll(/\bid="([^"]+)"/g)].map(m => m[1]);
assert.equal(new Set(ids).size, ids.length, 'IDs duplicados.');
for (const match of html.matchAll(/(?:href|src)="([^"]+)"/g)) {
  const target = match[1];
  if (target.startsWith('#')) assert(ids.includes(target.slice(1)), `Destino interno ausente: ${target}`);
  else if (target.startsWith('./')) await stat(path.join(output, target.split('#')[0]));
}
for (const artifact of Object.values(manifest.downloads)) {
  assert(html.includes(artifact.url), `Download ausente na página: ${artifact.file}`);
  if (process.argv.includes('--local-artifacts')) {
    const data = await readFile(path.resolve(landing, '../downloads', artifact.file));
    assert.equal(data.length, artifact.bytes, `Tamanho incorreto: ${artifact.file}`);
    assert.equal(createHash('sha256').update(data).digest('hex'), artifact.sha256, `Hash incorreto: ${artifact.file}`);
  }
  if (process.argv.includes('--remote')) {
    const response = await fetch(artifact.url, { method: 'HEAD' });
    assert.equal(response.status, 200, `Download indisponível: ${artifact.file}`);
    assert.equal(Number(response.headers.get('content-length')), artifact.bytes, `Arquivo remoto não corresponde ao instalador: ${artifact.file}`);
    assert.equal(response.headers.get('etag')?.replaceAll('"', ''), artifact.sha256, `Hash remoto incorreto: ${artifact.file}`);
  }
}
console.log('Página, arquivos locais e três downloads conferidos.');
