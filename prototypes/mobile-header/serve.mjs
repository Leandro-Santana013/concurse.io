import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { readFile } from 'node:fs/promises';
const root = path.dirname(fileURLToPath(import.meta.url));
const types = { '.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.png': 'image/png', '.woff2': 'font/woff2', '.txt': 'text/plain; charset=utf-8' };
http.createServer(async (req, res) => {
  try {
    const url = new URL(req.url, 'http://localhost:4190');
    const pathname = decodeURIComponent(url.pathname);
    const target = path.resolve(root, pathname === '/' ? 'index.html' : `.${pathname}`);
    if (target !== root && !target.startsWith(root + path.sep)) { res.writeHead(403); res.end('Forbidden'); return; }
    const contents = await readFile(target);
    res.writeHead(200, { 'Content-Type': types[path.extname(target)] || 'application/octet-stream', 'Cache-Control': 'no-store' });
    res.end(contents);
  } catch { res.writeHead(404); res.end('Not found'); }
}).listen(4190, '127.0.0.1', () => console.log('Protótipos disponíveis em http://127.0.0.1:4190/'));
