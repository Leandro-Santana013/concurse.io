const trackingKeys = new Set(['fbclid', 'gclid', 'mc_cid', 'mc_eid', 'ref', 'referrer']);

export function normalizeSourceUrl(value: string): string {
  const url = new URL(value.trim());
  if (!['http:', 'https:'].includes(url.protocol)) throw new Error('A fonte deve ser um endereço HTTP ou HTTPS.');
  url.hash = '';
  url.hostname = url.hostname.toLowerCase().replace(/\.$/, '');
  url.pathname = url.pathname.replace(/\/{2,}/g, '/').replace(/\/$/, '') || '/';
  const entries = [...url.searchParams.entries()]
    .filter(([key]) => !key.toLowerCase().startsWith('utm_') && !trackingKeys.has(key.toLowerCase()))
    .sort(([leftKey, leftValue], [rightKey, rightValue]) =>
      leftKey < rightKey ? -1 : leftKey > rightKey ? 1 : leftValue < rightValue ? -1 : leftValue > rightValue ? 1 : 0);
  url.search = new URLSearchParams(entries).toString();
  return url.toString();
}

export async function sourceKey(value: string): Promise<string> {
  const bytes = new TextEncoder().encode(normalizeSourceUrl(value));
  return [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))]
    .map(byte => byte.toString(16).padStart(2, '0')).join('');
}

export async function ownedSourceKey(userId: number, value: string): Promise<string> {
  const bytes = new TextEncoder().encode(`user:${userId}|source:${normalizeSourceUrl(value)}`);
  return [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))]
    .map(byte => byte.toString(16).padStart(2, '0')).join('');
}

export function isPublicSourceUrl(value: unknown): value is string {
  if (typeof value !== 'string') return false;
  try {
    const url = new URL(value);
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) return false;
    const host = url.hostname.toLowerCase().replace(/\.$/, '');
    if (!host.includes('.') || host.endsWith('.localhost') || host.endsWith('.local')) return false;
    if (/^(?:0\.|10\.|127\.|169\.254\.|192\.168\.|172\.(?:1[6-9]|2\d|3[01])\.)/.test(host)) return false;
    if (host.includes(':')) return false;
    return true;
  } catch { return false; }
}
