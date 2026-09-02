import React from 'react';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { axe } from 'vitest-axe';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../App';
import { AuthProvider } from '../context/AuthContext';
import { ExamProvider } from '../context/ExamContext';
import { UIProvider } from '../context/UIContext';

const apiMocks = vi.hoisted(() => ({
  getActiveDownloads: vi.fn(async () => []),
  getAuthConfig: vi.fn(async () => ({ google_enabled: true })),
  getCurrentUser: vi.fn(async () => null),
  getGoogleLoginUrl: vi.fn((nextPath: string) => `/api/v1/auth/google/login?next=${encodeURIComponent(nextPath)}`),
  logout: vi.fn(async () => undefined),
}));

vi.mock('../services/api', () => ({ api: apiMocks }));

const LocationProbe = () => {
  const location = useLocation();
  return <output data-testid="current-location">{location.pathname}{location.search}</output>;
};

const renderApp = (path: string) => render(
  <MemoryRouter initialEntries={[path]}>
    <AuthProvider>
      <UIProvider>
        <ExamProvider>
          <App />
          <LocationProbe />
        </ExamProvider>
      </UIProvider>
    </AuthProvider>
  </MemoryRouter>,
);

describe('login com Google', () => {
  beforeEach(() => {
    apiMocks.getActiveDownloads.mockResolvedValue([]);
    apiMocks.getAuthConfig.mockResolvedValue({ google_enabled: true });
    apiMocks.getCurrentUser.mockResolvedValue(null);
  });

  it('protege a biblioteca e preserva o destino no login', async () => {
    const { container } = renderApp('/biblioteca');

    expect(await screen.findByRole('heading', { name: 'Seu estudo continua daqui.' })).toBeVisible();
    expect(screen.getByTestId('current-location')).toHaveTextContent('/login?next=%2Fbiblioteca');

    const googleLink = await screen.findByRole('link', { name: 'Continuar com Google' });
    expect(googleLink).toHaveAttribute('href', '/api/v1/auth/google/login?next=%2Fbiblioteca');
    expect(googleLink).toHaveAttribute('aria-disabled', 'false');

    const audit = await axe(container, {
      rules: { 'color-contrast': { enabled: false } },
    });
    expect(audit.violations).toEqual([]);
  });

  it('explica um retorno OAuth inválido junto ao botão de nova tentativa', async () => {
    renderApp('/login?error=invalid_state&next=%2Fbuscar');

    expect(await screen.findByRole('alert')).toHaveTextContent('A tentativa de login expirou por segurança');
    expect(await screen.findByRole('link', { name: 'Continuar com Google' }))
      .toHaveAttribute('href', '/api/v1/auth/google/login?next=%2Fbuscar');
  });
});
