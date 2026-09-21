import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { MathRenderer } from '../components/exam/MathRenderer';

describe('MathRenderer', () => {
  it('trata números de parágrafo como marcadores inline, sem alterar o texto', () => {
    const content =
      '> Estou me vendo debaixo de uma árvore.\n\n' +
      '2 Olavo Bilac! – eu disse em voz alta.\n\n' +
      '3 O tal de Lácio eu não sabia onde ficava.\n\n' +
      '4 Fui falar com meu pai.';

    const { container } = render(<MathRenderer content={content} />);

    const markers = container.querySelectorAll('.source-paragraph-number');
    expect(markers).toHaveLength(3);
    expect(Array.from(markers, marker => marker.textContent)).toEqual(['2', '3', '4']);
    expect(container.textContent).toContain('2 Olavo Bilac! – eu disse em voz alta.');
    expect(container.textContent).toContain('3 O tal de Lácio eu não sabia onde ficava.');
    expect(container.textContent).toContain('4 Fui falar com meu pai.');
  });

  it('não reclassifica um número isolado no início de um enunciado', () => {
    const { container } = render(<MathRenderer content="2 respostas são possíveis." />);

    expect(container.querySelector('.source-paragraph-number')).not.toBeInTheDocument();
    expect(container).toHaveTextContent('2 respostas são possíveis.');
  });
});
