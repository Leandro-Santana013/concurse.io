import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { BrandIcon } from '../components/ui/BrandIcon';
import { UIProvider, useUI, type ThemeMode } from '../context/UIContext';

vi.mock('../services/api', () => ({ api: { getActiveDownloads: vi.fn(async () => []) } }));

const themes: ThemeMode[] = [
  'light', 'dark', 'oled', 'sepia', 'emerald', 'dracula',
  'nord', 'tokyo-night', 'catppuccin', 'gruvbox', 'monokai', 'solarized',
];

const ThemeControls = () => {
  const { setTheme } = useUI();
  return <>{themes.map(theme => <button key={theme} onClick={() => setTheme(theme)}>{theme}</button>)}</>;
};

describe('ícone da marca acompanha o tema', () => {
  it('troca automaticamente a versão do C com check em todos os doze temas, sem remontar a página', async () => {
    const user = userEvent.setup();
    render(<MemoryRouter><UIProvider>
      <BrandIcon alt="Marca concurse.io" width={28} height={28} />
      <ThemeControls />
    </UIProvider></MemoryRouter>);
    const image = screen.getByRole('img', { name: 'Marca concurse.io' });
    for (const theme of themes) {
      await user.click(screen.getByRole('button', { name: theme }));
      expect(image).toHaveAttribute('src', theme === 'light' || theme === 'sepia'
        ? '/concurse-icon-light-64.png' : '/concurse-icon-64.png');
      expect(document.documentElement).toHaveAttribute('data-theme', theme);
    }
  });

  it('usa a preferência clara persistida já na primeira renderização', () => {
    localStorage.setItem('concurse_ui_preferences_v2', JSON.stringify({
      version: 2, theme: 'sepia', fontSize: 'base', enableEliminationMode: true,
    }));
    render(<MemoryRouter><UIProvider><BrandIcon alt="Marca concurse.io" /></UIProvider></MemoryRouter>);
    expect(screen.getByRole('img')).toHaveAttribute('src', '/concurse-icon-light-64.png');
  });
});
