import React from 'react';
import katex from 'katex';

interface MathRendererProps {
  content: string;
  className?: string;
}

// Renderiza uma tabela Markdown simples em HTML estilizado
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

// Renderiza Markdown inline básico (**negrito**, *itálico*, links e quebras de linha)
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

  // Divide por marcadores **negrito** e *itálico*
  const tokens = text.split(/(\*\*.*?\*\*|\*.*?\*)/g);
  return tokens.map((token, idx) => {
    if (token.startsWith('**') && token.endsWith('**') && token.length >= 4) {
      return (
        <strong key={idx} className="font-bold text-white">
          {token.slice(2, -2)}
        </strong>
      );
    }
    if (token.startsWith('*') && token.endsWith('*') && token.length >= 2) {
      return (
        <em key={idx} className="italic text-slate-300">
          {token.slice(1, -1)}
        </em>
      );
    }
    return (
      <span key={idx} className="whitespace-pre-wrap">
        {token}
      </span>
    );
  });
};

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
          <p key={pIdx} className="leading-relaxed text-indigo-100/90 text-sm sm:text-base font-reading">
            {renderInlineMarkdown(para)}
          </p>
        ))}
      </div>
    );
  }

  // Parágrafos regulares
  const paragraphs = rawText.split('\n\n').filter(p => p.trim());
  if (paragraphs.length > 1) {
    return (
      <span key={keyPrefix} className="inline-block w-full space-y-4">
        {paragraphs.map((p, pIdx) => (
          <span key={pIdx} className="block leading-relaxed">
            {renderInlineMarkdown(p)}
          </span>
        ))}
      </span>
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

  // 2. Separação de blocos Display $$...$$ e Inline $...$
  const displayParts = content.split(/(\$\$.*?\$\$)/gs);

  return (
    <span className={`inline-block w-full leading-relaxed ${className}`}>
      {displayParts.map((dPart, dIdx) => {
        // Bloco Display $$...$$
        if (dPart.startsWith('$$') && dPart.endsWith('$$')) {
          const formula = dPart.slice(2, -2).trim();
          try {
            const html = katex.renderToString(formula, {
              displayMode: true,
              throwOnError: false,
            });
            return (
              <span
                key={dIdx}
                className="my-3 block overflow-x-auto py-1 text-center font-serif text-indigo-300"
                dangerouslySetInnerHTML={{ __html: html }}
              />
            );
          } catch (e) {
            return <code key={dIdx} className="bg-slate-800 text-amber-300 px-1 rounded">{formula}</code>;
          }
        }

        // Inline $...$ dentro de texto normal
        const inlineParts = dPart.split(/(\$[^\$\n]+?\$)/g);

        return (
          <span key={dIdx}>
            {inlineParts.map((iPart, iIdx) => {
              if (iPart.startsWith('$') && iPart.endsWith('$') && iPart.length > 2) {
                const inlineFormula = iPart.slice(1, -1).trim();
                try {
                  const html = katex.renderToString(inlineFormula, {
                    displayMode: false,
                    throwOnError: false,
                  });
                  return (
                    <span
                      key={iIdx}
                      className="inline-block px-0.5 font-serif text-indigo-200"
                      dangerouslySetInnerHTML={{ __html: html }}
                    />
                  );
                } catch (e) {
                  return <span key={iIdx} className="text-amber-300 font-mono text-sm">{inlineFormula}</span>;
                }
              }

              // Texto puro com renderização enriquecida (parágrafos, negrito, divisores)
              return renderFormattedBlock(iPart, `${dIdx}_${iIdx}`);
            })}
          </span>
        );
      })}
    </span>
  );
};
