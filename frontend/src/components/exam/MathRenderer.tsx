import React from 'react';
import katex from 'katex';

interface MathRendererProps {
  content: string;
  className?: string;
}

// Verifica se um trecho $...$ é uma fórmula LaTeX real ou apenas valor monetário/texto
const isRealLatexFormula = (str: string): boolean => {
  if (!str) return false;
  const trimmed = str.trim();
  
  // Moeda comum (ex: 150, 150 million, 10.00, 500 mil, etc.) -> NÃO é LaTeX!
  if (/^\d+(?:[.,]\d+)?\s*(?:million|billion|trillion|mil|milhões|bilhões|milhoes|bilhoes|k|m|b)?$/i.test(trimmed)) {
    return false;
  }
  
  // Se contiver comandos explícitos de LaTeX ou caracteres matemáticos típicos
  if (/[\\[\]{}^_]|\\[a-zA-Z]+|\\frac|\\sqrt|\\times|\\div|\\leq|\\geq|\\neq|\\in|\\pm|\\alpha|\\beta|\\theta|\\pi|\\cdot/.test(trimmed)) {
    return true;
  }
  
  // Se contiver muitas palavras normais ou pontuação de narrativa -> NÃO é LaTeX
  if (/\b(?:the|and|for|about|according|when|was|were|that|this|with|from|como|para|sobre|entre|pelo|pela)\b/i.test(trimmed)) {
    return false;
  }
  
  // Expressão matemática compacta (ex: x + y = 2, f(x) = 0, a^2 + b^2)
  if (/^[a-zA-Z0-9\s+\-*\/=()<>]+$/.test(trimmed) && trimmed.length <= 40 && /[+\-*\/=^<>]/.test(trimmed)) {
    return true;
  }
  
  return false;
};

// Renderiza tabela Markdown simples em HTML estilizado
const renderMarkdownTable = (tableText: string, keyPrefix: string | number) => {
  const lines = tableText.trim().split('\n').filter(l => l.includes('|'));
  if (lines.length < 2) return null;

  const parseRow = (line: string) => {
    return line
      .split('|')
      .slice(1, -1)
      .map(c => c.trim());
  };

  const headerCells = parseRow(lines[0]);
  const isSeparator = (line: string) => /^\|?\s*:?-+:?\s*(\|:?-+:?\s*)+\|?$/.test(line.trim());
  
  const startIndex = isSeparator(lines[1]) ? 2 : 1;
  const bodyRows = lines.slice(startIndex).map(parseRow);

  return (
    <div key={keyPrefix} className="my-4 overflow-x-auto rounded-xl border border-white/10 bg-slate-950/40 p-2 shadow-inner">
      <table className="w-full text-left text-sm text-slate-200 border-collapse">
        {headerCells.length > 0 && (
          <thead>
            <tr className="border-b border-white/10 bg-white/5 font-semibold text-indigo-300">
              {headerCells.map((h, hIdx) => (
                <th key={hIdx} className="px-4 py-2.5">
                  <MathRenderer content={h} />
                </th>
              ))}
            </tr>
          </thead>
        )}
        <tbody>
          {bodyRows.map((row, rIdx) => (
            <tr
              key={rIdx}
              className={`border-b border-white/5 transition hover:bg-white/[0.02] ${
                rIdx % 2 === 1 ? 'bg-white/[0.01]' : ''
              }`}
            >
              {row.map((cell, cIdx) => (
                <td key={cIdx} className="px-4 py-2 text-slate-300">
                  <MathRenderer content={cell} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

// Renderiza KaTeX inline ou display com fallback seguro
const renderKaTeX = (formula: string, displayMode: boolean, key: string | number) => {
  try {
    const html = katex.renderToString(formula, {
      displayMode,
      throwOnError: false,
    });
    if (displayMode) {
      return (
        <span
          key={key}
          className="my-3 block overflow-x-auto py-1 text-center font-serif text-indigo-300"
          dangerouslySetInnerHTML={{ __html: html }}
        />
      );
    }
    return (
      <span
        key={key}
        className="inline-block px-0.5 font-serif text-indigo-200"
        dangerouslySetInnerHTML={{ __html: html }}
      />
    );
  } catch {
    return <span key={key} className="text-amber-300 font-mono text-sm">{formula}</span>;
  }
};

// Sanitiza e normaliza tags HTML antes da renderização
const normalizeInlineTags = (str: string): string => {
  if (!str) return '';
  // Corrige tags malformadas sem fechamento '>' coladas em palavras (ex: </uafirmar -> </u> afirmar)
  let s = str.replace(/<\/([uib])(?=[A-Za-z\u00C0-\u00DC])/gi, '</$1> ');
  s = s.replace(/<([uib])(?=[A-Za-z\u00C0-\u00DC])/gi, '<$1> ');
  s = s.replace(/<\/([uib])(?=[\s\.,;:!\?\)\(\]\[])/gi, '</$1>');
  return s;
};

// Renderiza recursivamente tags HTML (<u>, <b>, <i>, <strong>, <em>) e Markdown (***, **, *)
const renderInlineFormatting = (raw: string, keyPrefix: string): React.ReactNode => {
  if (!raw) return null;

  const normalized = normalizeInlineTags(raw);

  // Tokeniza tags HTML e Markdown mantendo delimitadores
  const tokenRegex = /(<u>[\s\S]*?<\/u>|<b>[\s\S]*?<\/b>|<strong>[\s\S]*?<\/strong>|<i>[\s\S]*?<\/i>|<em>[\s\S]*?<\/em>|\*\*\*[\s\S]*?\*\*\*|\*\*[\s\S]*?\*\*|\*[\s\S]*?\*)/gi;
  const parts = normalized.split(tokenRegex);

  if (parts.length === 1) {
    // Limpa eventuais tags órfãs (ex: <u> ou </u> soltas ou sem '>')
    const cleaned = normalized.replace(/<\/?(?:u|b|i|strong|em)>?/gi, '');
    return <span className="whitespace-pre-wrap">{cleaned}</span>;
  }

  return (
    <>
      {parts.map((part, idx) => {
        if (!part) return null;
        const subKey = `${keyPrefix}_${idx}`;

        // 1. Sublinhado <u>...</u>
        if (/^<u>[\s\S]*<\/u>$/i.test(part)) {
          const inner = part.slice(3, -4);
          return (
            <u key={subKey} className="underline decoration-indigo-400 decoration-1.5 underline-offset-2">
              {renderInlineFormatting(inner, `${subKey}_u`)}
            </u>
          );
        }

        // 2. Negrito + Itálico ***...***
        if (part.startsWith('***') && part.endsWith('***') && part.length >= 6) {
          const inner = part.slice(3, -3);
          return (
            <strong key={subKey} className="font-bold italic text-white">
              {renderInlineFormatting(inner, `${subKey}_bi`)}
            </strong>
          );
        }

        // 3. Negrito <b>, <strong>, **...**
        if (/^<b>[\s\S]*<\/b>$/i.test(part)) {
          const inner = part.slice(3, -4);
          return (
            <strong key={subKey} className="font-bold text-white">
              {renderInlineFormatting(inner, `${subKey}_b`)}
            </strong>
          );
        }
        if (/^<strong>[\s\S]*<\/strong>$/i.test(part)) {
          const inner = part.slice(8, -9);
          return (
            <strong key={subKey} className="font-bold text-white">
              {renderInlineFormatting(inner, `${subKey}_str`)}
            </strong>
          );
        }
        if (part.startsWith('**') && part.endsWith('**') && part.length >= 4) {
          const inner = part.slice(2, -2);
          return (
            <strong key={subKey} className="font-bold text-white">
              {renderInlineFormatting(inner, `${subKey}_bmd`)}
            </strong>
          );
        }

        // 4. Itálico <i>, <em>, *...*
        if (/^<i>[\s\S]*<\/i>$/i.test(part)) {
          const inner = part.slice(3, -4);
          return (
            <em key={subKey} className="italic text-slate-300">
              {renderInlineFormatting(inner, `${subKey}_i`)}
            </em>
          );
        }
        if (/^<em>[\s\S]*<\/em>$/i.test(part)) {
          const inner = part.slice(4, -5);
          return (
            <em key={subKey} className="italic text-slate-300">
              {renderInlineFormatting(inner, `${subKey}_em`)}
            </em>
          );
        }
        if (part.startsWith('*') && part.endsWith('*') && part.length >= 2) {
          const inner = part.slice(1, -1);
          return (
            <em key={subKey} className="italic text-slate-300">
              {renderInlineFormatting(inner, `${subKey}_imd`)}
            </em>
          );
        }

        // Texto plano com limpeza de tags órfãs
        const cleaned = part.replace(/<\/?(?:u|b|i|strong|em)>?/gi, '');
        return (
          <span key={subKey} className="whitespace-pre-wrap">
            {cleaned}
          </span>
        );
      })}
    </>
  );
};

// Renderiza Markdown inline (**negrito**, *itálico*, <u>sublinhado</u>, links e KaTeX inline)
const renderInlineMarkdown = (text: string) => {
  if (!text) return null;

  // Cabeçalho H3 Markdown
  if (text.startsWith('### ')) {
    return (
      <h3 className="text-base sm:text-lg font-bold font-heading text-indigo-200 my-2 border-b border-indigo-500/20 pb-1">
        {text.slice(4)}
      </h3>
    );
  }

  // 1. Processamento de KaTeX Display ($$...$$) e Inline ($...$)
  const mathTokens = text.split(/(\$\$.*?\$\$|\$[^\$\n]+?\$)/gs);

  return mathTokens.map((mToken, mIdx) => {
    // Bloco Display $$...$$
    if (mToken.startsWith('$$') && mToken.endsWith('$$') && mToken.length >= 4) {
      const formula = mToken.slice(2, -2).trim();
      return renderKaTeX(formula, true, `disp_${mIdx}`);
    }

    // Bloco Inline $...$ (somente se for fórmula real, não valor monetário como $150 million)
    if (mToken.startsWith('$') && mToken.endsWith('$') && mToken.length > 2) {
      const inner = mToken.slice(1, -1).trim();
      if (isRealLatexFormula(inner)) {
        return renderKaTeX(inner, false, `inl_${mIdx}`);
      }
    }

    // 2. Formatação rica (HTML <u>, <b>, <i> e Markdown **, *)
    return (
      <React.Fragment key={`fmt_${mIdx}`}>
        {renderInlineFormatting(mToken, `fmt_${mIdx}`)}
      </React.Fragment>
    );
  });
};

// Renderiza blocos estruturais (Divisores, Texto de Apoio, Parágrafos)
const renderFormattedBlock = (rawText: string, keyPrefix: string | number) => {
  if (!rawText) return null;

  // Divisor horizontal markdown ---
  if (rawText.includes('---')) {
    const sections = rawText.split(/(?:\n\s*---\s*\n|^\s*---\s*\n|\n\s*---\s*$)/g);
    if (sections.length > 1) {
      return (
        <span key={keyPrefix} className="inline-block w-full">
          {sections.map((sec, sIdx) => (
            <React.Fragment key={sIdx}>
              {sIdx > 0 && <span className="my-6 block border-b border-indigo-500/25" />}
              {renderFormattedBlock(sec, `${keyPrefix}_sec_${sIdx}`)}
            </React.Fragment>
          ))}
        </span>
      );
    }
  }

  // Bloco de Texto de Apoio Compartilhado
  if (rawText.trim().startsWith('📖')) {
    const paras = rawText.trim().split('\n\n').filter(p => p.trim());
    return (
      <div
        key={keyPrefix}
        className="my-4 rounded-2xl border border-indigo-500/25 bg-gradient-to-br from-indigo-950/40 via-slate-900/60 to-slate-950/60 p-4 sm:p-5 shadow-lg shadow-indigo-950/20 backdrop-blur-sm space-y-3"
      >
        {paras.map((para, pIdx) => (
          <div key={pIdx} className="leading-relaxed text-indigo-100/90 text-sm sm:text-base font-reading">
            {renderInlineMarkdown(para)}
          </div>
        ))}
      </div>
    );
  }

  // Parágrafos regulares e Estrofes de Poema
  const paragraphs = rawText.split('\n\n').filter(p => p.trim());
  if (paragraphs.length > 1) {
    return (
      <span key={keyPrefix} className="inline-block w-full space-y-4">
        {paragraphs.map((p, pIdx) => {
          if (p.trim().startsWith('>')) {
            const lines = p.trim().split('\n').map(l => l.replace(/^>\s?/, ''));
            return (
              <blockquote
                key={pIdx}
                className="my-3 border-l-4 border-indigo-400/70 bg-gradient-to-r from-indigo-950/40 via-indigo-900/10 to-transparent py-3 px-4 rounded-r-xl italic text-indigo-100 font-serif text-sm sm:text-base leading-relaxed tracking-wide space-y-1 shadow-sm backdrop-blur-xs"
              >
                {lines.map((line, lIdx) => (
                  <span key={lIdx} className="block whitespace-pre-wrap">
                    {renderInlineMarkdown(line)}
                  </span>
                ))}
              </blockquote>
            );
          }
          return (
            <span key={pIdx} className="block leading-relaxed">
              {renderInlineMarkdown(p)}
            </span>
          );
        })}
      </span>
    );
  }

  if (rawText.trim().startsWith('>')) {
    const lines = rawText.trim().split('\n').map(l => l.replace(/^>\s?/, ''));
    return (
      <blockquote
        key={keyPrefix}
        className="my-3 border-l-4 border-indigo-400/70 bg-gradient-to-r from-indigo-950/40 via-indigo-900/10 to-transparent py-3 px-4 rounded-r-xl italic text-indigo-100 font-serif text-sm sm:text-base leading-relaxed tracking-wide space-y-1 shadow-sm backdrop-blur-xs"
      >
        {lines.map((line, lIdx) => (
          <span key={lIdx} className="block whitespace-pre-wrap">
            {renderInlineMarkdown(line)}
          </span>
        ))}
      </blockquote>
    );
  }

  return (
    <span key={keyPrefix} className="whitespace-pre-wrap">
      {renderInlineMarkdown(rawText)}
    </span>
  );
};


export const MathRenderer: React.FC<MathRendererProps> = ({ content, className = '' }) => {
  if (!content) return null;

  // 1. Se contiver uma tabela Markdown (| col1 | col2 |)
  if (content.includes('|') && content.includes('---')) {
    const tableRegex = /(\n*\|[^\n]+\|\n\|(?:\s*:?-+:?\s*\|)+\n(?:\|[^\n]+\|\n?)*)/g;
    const tableParts = content.split(tableRegex);

    if (tableParts.length > 1) {
      return (
        <span className={`inline-block w-full leading-relaxed ${className}`}>
          {tableParts.map((tPart, tIdx) => {
            if (tPart.trim().startsWith('|') && tPart.includes('---')) {
              return renderMarkdownTable(tPart, tIdx);
            }
            return <MathRenderer key={tIdx} content={tPart} />;
          })}
        </span>
      );
    }
  }

  // 2. Renderiza a estrutura de blocos e formatação do documento
  return (
    <span className={`inline-block w-full leading-relaxed ${className}`}>
      {renderFormattedBlock(content, 'root')}
    </span>
  );
};
