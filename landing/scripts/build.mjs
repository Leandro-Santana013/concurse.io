import { cp, mkdir, readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const landing = fileURLToPath(new URL('../', import.meta.url));
const repositoryRoot = path.resolve(landing, '..');
const manifest = JSON.parse(await readFile(path.join(landing, 'releases.json'), 'utf8'));
const checksums = await readFile(path.join(repositoryRoot, 'downloads/SHA256SUMS.txt'), 'utf8');
const knownHashes = new Map(checksums.trim().split(/\r?\n/).map(line => {
  const match = line.match(/^([a-f0-9]{64})\s+(.+)$/);
  if (!match) throw new Error(`Linha inválida em SHA256SUMS.txt: ${line}`);
  return [match[2], match[1]];
}));
if (!/^[a-f0-9]{40}$/.test(manifest.artifactCommit)) throw new Error('O commit dos downloads deve ser um SHA completo.');
if (!/^[\w-]+\/[\w.-]+$/.test(manifest.repository)) throw new Error('Repositório inválido.');
const site = new URL(process.env.LANDING_SITE_URL || manifest.siteUrl);
if (!['https:', 'http:'].includes(site.protocol)) throw new Error('Protocolo de URL inválido.');
if (!site.pathname.endsWith('/')) site.pathname += '/';
const size = bytes => `${new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 1 }).format(bytes / 1_000_000)} MB`;
const escapeHtml = value => String(value).replaceAll('&', '&amp;').replaceAll('"', '&quot;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');
const values = {
  SITE_URL: site.href,
  SITE_PATH: site.pathname,
  REPOSITORY_URL: `https://github.com/${manifest.repository}/tree/codex/concurse-app`,
  CHECKSUMS_URL: './SHA256SUMS.txt',
};
const published = {};
for (const [key, artifact] of Object.entries(manifest.downloads)) {
  if (knownHashes.get(artifact.file) !== artifact.sha256) throw new Error(`SHA-256 desatualizado: ${artifact.file}`);
  if (!Number.isSafeInteger(artifact.bytes) || artifact.bytes < 1) throw new Error(`Tamanho inválido: ${artifact.file}`);
  if (!/^[\w.-]+$/.test(artifact.file)) throw new Error(`Nome de download inválido: ${artifact.file}`);
  const url = `https://media.githubusercontent.com/media/${manifest.repository}/${manifest.artifactCommit}/downloads/${encodeURIComponent(artifact.file)}`;
  values[`${key}_URL`] = url;
  values[`${key}_VERSION`] = artifact.version;
  if (key === 'ANDROID_APK') {
    if (!Number.isSafeInteger(artifact.androidVersionCode) || artifact.androidVersionCode < 1) throw new Error('Código Android inválido.');
    values.ANDROID_APK_CODE = artifact.androidVersionCode;
  }
  values[`${key}_SIZE`] = size(artifact.bytes);
  values[`${key}_SHA256`] = artifact.sha256;
  published[key] = { ...artifact, url };
}
let html = await readFile(path.join(landing, 'index.html'), 'utf8');
html = html.replace(/\{\{([A-Z_0-9]+)\}\}/g, (_, key) => {
  if (!(key in values)) throw new Error(`Variável desconhecida: ${key}`);
  return escapeHtml(values[key]);
});
const output = path.join(landing, 'dist');
await mkdir(output, { recursive: true });
await Promise.all([
  writeFile(path.join(output, 'index.html'), html),
  cp(path.join(landing, 'styles.css'), path.join(output, 'styles.css')),
  cp(path.join(landing, 'app.js'), path.join(output, 'app.js')),
  cp(path.join(landing, 'assets'), path.join(output, 'assets'), { recursive: true }),
  writeFile(path.join(output, '.nojekyll'), ''),
  writeFile(path.join(output, 'SHA256SUMS.txt'), Object.values(published).map(a => `${a.sha256}  ${a.file}`).join('\n') + '\n'),
  writeFile(path.join(output, 'releases.json'), JSON.stringify({ artifactCommit: manifest.artifactCommit, downloads: published }, null, 2) + '\n'),
  writeFile(path.join(output, 'robots.txt'), `User-agent: *\nAllow: /\nSitemap: ${site.href}sitemap.xml\n`),
  writeFile(path.join(output, 'sitemap.xml'), `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>${escapeHtml(site.href)}</loc></url></urlset>\n`),
]);
console.log(`Landing gerada: ${output}. Três downloads fixados e conferidos em SHA256SUMS.txt.`);
