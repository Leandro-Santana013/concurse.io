//! Módulo de tratamento de URLs, decodificação percentual e fontes bibliográficas
use once_cell::sync::Lazy;
use regex::Regex;

pub static URL_RAW_REGEX: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r##"(?i)(?:\*\([Ff]onte:\s*|\(?[Ff]onte\s*:\s*|\(?[Aa]cesso\s+em\s*:\s*)?(?:https?://|://)[a-zA-Z0-9\-_./%?&=#@:+ \u{00C0}-\u{00FC}]+(?:\([a-zA-Z0-9\-_\s./%?&=#@:+\u{00C0}-\u{00FC}]+\)[a-zA-Z0-9\-_./%?&=#@:+ \u{00C0}-\u{00FC}]*)*(?:\.pdf|\.html|\.php|[a-zA-Z0-9/])(?:\)\*|\))?"##).unwrap()
});

pub static URL_EXTRACT_REGEX: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r##"(?i)(?:https?://|://)[a-zA-Z0-9\-_./%?&=#@:+ \u{00C0}-\u{00FC}]+(?:\([a-zA-Z0-9\-_\s./%?&=#@:+\u{00C0}-\u{00FC}]+\)[a-zA-Z0-9\-_./%?&=#@:+ \u{00C0}-\u{00FC}]*)*(?:\.pdf|\.html|\.php|[a-zA-Z0-9/])"##).unwrap()
});

/// Decodifica sequências percent-encoded (ex: %C3%A1 -> á, %20 -> espaço) preservando UTF-8 válido
pub fn percent_decode_utf8(s: &str) -> String {
    let bytes = s.as_bytes();
    let mut decoded_bytes = Vec::with_capacity(bytes.len());
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'%' && i + 2 < bytes.len() {
            let b1 = bytes[i + 1];
            let b2 = bytes[i + 2];
            if b1.is_ascii_hexdigit() && b2.is_ascii_hexdigit() {
                if let Ok(hex_str) = std::str::from_utf8(&bytes[i + 1..i + 3]) {
                    if let Ok(val) = u8::from_str_radix(hex_str, 16) {
                        decoded_bytes.push(val);
                        i += 3;
                        continue;
                    }
                }
            }
        }
        decoded_bytes.push(bytes[i]);
        i += 1;
    }
    String::from_utf8(decoded_bytes).unwrap_or_else(|_| s.to_string())
}

/// Isola e padroniza URLs e fontes bibliográficas em Markdown (ex: *(Fonte: https://...)*)
pub fn format_urls_and_sources(text: &str) -> String {
    URL_RAW_REGEX.replace_all(text, |caps: &regex::Captures| {
        let full = caps.get(0).unwrap().as_str();
        if let Some(m_url) = URL_EXTRACT_REGEX.find(full) {
            let mut raw_url = m_url.as_str().to_string();
            raw_url = raw_url.trim_matches(|c| c == '.' || c == ',' || c == ')' || c == '(' || c == ' ' || c == '\n' || c == '\r' || c == '*').to_string();
            if raw_url.contains('%') {
                raw_url = percent_decode_utf8(&raw_url);
            }
            format!("\n\n*(Fonte: {})*\n\n", raw_url)
        } else {
            full.to_string()
        }
    }).into_owned()
}
