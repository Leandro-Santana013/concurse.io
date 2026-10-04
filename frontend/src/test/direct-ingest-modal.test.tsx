import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';
import { DirectIngestModal } from '../components/dashboard/DirectIngestModal';
import { UIProvider } from '../context/UIContext';

const apiMocks = vi.hoisted(() => ({
  apiUrl: (path: string) => path,
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
  getExamProgress: vi.fn(async () => ({ status: 'Processando', progress: 5 })),
  getLocalExamProgress: vi.fn(async () => ({ status: 'Processando', progress: 5 })),
  syncLocalExam: vi.fn(async () => ({ exam_id: 99, status: 'Aprovada', progress: 100, message: 'Prova sincronizada' })),
}));

vi.mock('../services/api', () => ({
  api: apiMocks,
  apiUrl: apiMocks.apiUrl,
  LOCAL_ENGINE: false,
}));

describe('modal de importação', () => {
  beforeEach(() => {
    vi.clearAllMocks();
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

    await waitFor(() => expect(apiMocks.getExamProgress).toHaveBeenCalledWith(42));
    expect(screen.getByRole('progressbar')).toHaveAttribute('value', '5');
    expect(container.querySelector('.ingest-progress-loader')).toBeInTheDocument();
    expect(container.querySelectorAll('.ingest-progress-loader')).toHaveLength(2);
  });

  it('publica a extração do aparelho e abre o identificador central', async () => {
    apiMocks.ingestExam.mockResolvedValueOnce({ exam_id: 42, title: 'Prova', status: 'Processando', progress: 5,
      message: 'Extraindo', reused: false, already_in_library: false, processing_location: 'device' } as any);
    apiMocks.getLocalExamProgress.mockResolvedValueOnce({ status: 'Aprovada', progress: 100 });
    const onReady = vi.fn();
    const user = userEvent.setup();
    render(<MemoryRouter><UIProvider><DirectIngestModal isOpen onClose={vi.fn()} onExamReady={onReady} initialExamUrl="https://example.com/prova.pdf" /></UIProvider></MemoryRouter>);
    await user.click(screen.getByRole('button', { name: 'Processar prova' }));
    await waitFor(() => expect(apiMocks.syncLocalExam).toHaveBeenCalledWith(42));
    await user.click(await screen.findByRole('button', { name: 'Iniciar simulado' }));
    expect(onReady).toHaveBeenCalledWith(99);
    expect(apiMocks.getExamProgress).not.toHaveBeenCalled();
  });

  it('reutiliza a prova central sem tratar seu identificador como extração local', async () => {
    apiMocks.ingestExam.mockResolvedValueOnce({ exam_id: 77, title: 'Prova', status: 'Aprovada', progress: 100,
      message: 'Prova já disponível', reused: true, already_in_library: true, processing_location: 'cloud' } as any);
    const onReady = vi.fn();
    const user = userEvent.setup();
    render(<MemoryRouter><UIProvider><DirectIngestModal isOpen onClose={vi.fn()} onExamReady={onReady} initialExamUrl="https://example.com/prova.pdf" /></UIProvider></MemoryRouter>);
    await user.click(screen.getByRole('button', { name: 'Processar prova' }));
    await user.click(await screen.findByRole('button', { name: 'Iniciar simulado' }));
    expect(onReady).toHaveBeenCalledWith(77);
    expect(apiMocks.syncLocalExam).not.toHaveBeenCalled();
    expect(apiMocks.getLocalExamProgress).not.toHaveBeenCalled();
  });
});
