import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CustomSimulationModal } from '../components/dashboard/CustomSimulationModal';

const apiMocks = vi.hoisted(() => ({
  getCustomSimulationOptions: vi.fn(),
}));

vi.mock('../services/api', () => ({ api: apiMocks }));

describe('modal de simulado personalizado', () => {
  beforeEach(() => {
    apiMocks.getCustomSimulationOptions.mockResolvedValue({
      available_questions: 42,
      subjects: [
        { name: 'Português', count: 18 },
        { name: 'Direito', count: 24 },
      ],
      sources: [{ id: 7, title: 'FGV 2025 — Auditor', count: 12 }],
    });
  });

  it('envia quantidade, disciplina e origem escolhidas', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn(async () => undefined);

    render(
      <CustomSimulationModal
        isOpen
        onClose={vi.fn()}
        onSubmit={onSubmit}
      />,
    );

    expect(await screen.findByRole('heading', { name: 'Montar simulado personalizado' })).toBeVisible();
    const countInput = screen.getByRole('spinbutton');
    await user.clear(countInput);
    await user.type(countInput, '10');
    await user.click(screen.getByRole('button', { name: /Português/ }));
    await user.selectOptions(screen.getByRole('combobox'), '7');
    await user.click(screen.getByRole('button', { name: 'Gerar simulado' }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith({
      count: 10,
      subjects: ['Português'],
      sourceExamId: 7,
    }));
  });
});
