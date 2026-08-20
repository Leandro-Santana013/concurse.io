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
  // Tokeniza primeiro blocos $$...$$, depois inline $...$
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

              // Texto puro com quebras de parágrafo naturais
              return (
                <span key={iIdx} className="whitespace-pre-wrap">
                  {iPart}
                </span>
              );
            })}
          </span>
        );
      })}
    </span>
  );
};
