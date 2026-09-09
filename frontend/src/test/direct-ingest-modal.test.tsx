import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';
import { DirectIngestModal } from '../components/dashboard/DirectIngestModal';
import { UIProvider } from '../context/UIContext';

const apiMocks = vi.hoisted(() => ({
  getActiveDownloads: vi.fn(async () => []),
  ingestExam: vi.fn(async () => ({
    exam_id: 42,
    title: 'Prova em processamento',
    status: 'Processando',
    progress: 5,
    message: 'Processamento assíncrono iniciado com sucesso.',
    reused: false,
    already_in_library: false,
  })),
  getExamProgress: vi.fn(),
}));

vi.mock('../services/api', () => ({ api: apiMocks }));

class FakeEventSource {
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  close = vi.fn();

  constructor(public readonly url: string) {}
}

describe('modal de importação', () => {
  beforeEach(() => {
    vi.stubGlobal('EventSource', FakeEventSource);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('mantém um loader dedicado enquanto a prova está sendo processada', async () => {
    const user = userEvent.setup();
    const { container } = render(
      <MemoryRouter>
        <UIProvider>
          <DirectIngestModal
            isOpen
            onClose={vi.fn()}
            initialExamUrl="https://example.com/prova.pdf"
          />
        </UIProvider>
      </MemoryRouter>,
    );

    await user.click(screen.getByRole('button', { name: 'Processar prova' }));

    await waitFor(() => expect(screen.getByText('Baixando e organizando as questões...')).toBeVisible());
    expect(container.querySelector('.ingest-progress-loader')).toBeInTheDocument();
    expect(container.querySelectorAll('.ingest-progress-loader')).toHaveLength(2);
  });
});
