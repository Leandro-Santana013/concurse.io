import { expect, test, type Page } from '@playwright/test';

test.describe.configure({ mode: 'default' });

const prepareNavigation = async (page: Page) => {
  // Isolate navigation from login and study data; the real native dialog and
  // responsive styles still run in Chromium, unlike the jsdom unit tests.
  await page.route('**/api/v1/**', (route) => route.fulfill({
    json: route.request().url().endsWith('/auth/me')
      ? { id: 1, name: 'Pessoa de teste', email: 'navigation@example.com' }
      : route.request().url().endsWith('/downloads/active')
        ? [{ id: 101 }, { id: 102 }, { id: 103 }]
        : [],
  }));
  await page.addInitScript(() => localStorage.setItem('concurse-active-exam-storage', JSON.stringify({
    version: 4,
    state: {
      ownerUserId: 1,
      activeExam: { id: 41, title: 'Prova em andamento', status: 'Aprovada', questions: [], has_official_answers: true, gabarito_coverage: 100 },
      isFinished: false,
      isTimerRunning: false,
    },
  })));
};

for (const viewport of [
  { width: 320, height: 800 },
  { width: 375, height: 812 },
  { width: 812, height: 375 },
]) {
  test(`cinco destinos ficam em uma linha em ${viewport.width} × ${viewport.height}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await prepareNavigation(page);
    await page.goto('/');
    const bottom = page.getByRole('navigation', { name: 'Navegação principal' });
    await expect(bottom).toBeVisible();
    const links = bottom.getByRole('link');
    await expect(links).toHaveCount(5);
    const bounds = await links.evaluateAll((items) => items.map((item) => {
      const { x, y, width, height } = item.getBoundingClientRect();
      return { x, y, width, height };
    }));
    expect(new Set(bounds.map((item) => item.y)).size).toBe(1);
    expect(bounds.every((item) => item.width >= 48 && item.height >= 48)).toBe(true);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
    expect(overflow).toBe(false);
    const header = page.locator('.app-navbar');
    const controls = header.getByRole('button');
    await expect(controls).toHaveCount(3);
    const headerBounds = await controls.evaluateAll(items => items.map(item => {
      const { x, y, width, height } = item.getBoundingClientRect();
      return { x, y, width, height };
    }));
    expect(new Set(headerBounds.map(item => item.y)).size).toBe(1);
    expect(headerBounds.every(item => item.width === 48 && item.height === 48)).toBe(true);
    expect(headerBounds.every((item, index) => index === 0 || item.x >= headerBounds[index - 1].x + 48)).toBe(true);
    await expect(page.locator('.account-control')).not.toBeVisible();
    await expect(page.locator('.download-status')).not.toBeVisible();
    await expect(header.getByRole('button', { name: 'Importar prova por link' })).toHaveAccessibleDescription('3 arquivos em processamento');
    await expect(page.locator('.navbar-download-badge')).toHaveText('3');
    // A long title must surrender width instead of pushing the two actions out.
    await page.goto('/progresso/erros');
    await expect(page.locator('.navbar-title-group p')).toHaveText('Caderno de erros');
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
    const titleAndActions = await page.evaluate(() => ({
      titleRight: document.querySelector('.navbar-title-group p')!.getBoundingClientRect().right,
      actionsLeft: document.querySelector('.navbar-actions')!.getBoundingClientRect().left,
    }));
    expect(titleAndActions.titleRight).toBeLessThanOrEqual(titleAndActions.actionsLeft);
  });
}

test('menu complementar mantém foco no painel e fecha com Escape', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.emulateMedia({ reducedMotion: 'reduce', colorScheme: 'dark' });
  await page.addInitScript(() => localStorage.setItem('concurse_ui_preferences_v2', JSON.stringify({
    version: 2, theme: 'dark', fontSize: 'xl', enableEliminationMode: true,
  })));
  await prepareNavigation(page);
  await page.goto('/');
  const trigger = page.getByRole('button', { name: 'Abrir mais opções' });
  await trigger.click();
  const dialog = page.getByRole('dialog', { name: 'Mais opções' });
  await expect(dialog).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  const close = dialog.getByRole('button', { name: 'Fechar menu' });
  await expect(close).toBeFocused();
  await expect(dialog.getByRole('link')).toHaveCount(2);
  await page.keyboard.press('Shift+Tab');
  await expect(dialog.getByRole('button', { name: 'Importar prova' })).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(close).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(dialog).not.toBeVisible();
  await expect(trigger).toBeFocused();
  await expect(trigger).toHaveAttribute('aria-expanded', 'false');
});

test('atalho de ranking fecha o menu e seleciona Progresso na barra', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await prepareNavigation(page);
  await page.goto('/');
  await page.getByRole('button', { name: 'Abrir mais opções' }).click();
  const dialog = page.getByRole('dialog', { name: 'Mais opções' });
  await dialog.getByRole('link', { name: 'Ranking' }).click();
  await expect(page).toHaveURL(/\/progresso\/ranking$/);
  await expect(dialog).not.toBeVisible();
  const bottom = page.getByRole('navigation', { name: 'Navegação principal' });
  await expect(bottom.getByRole('link', { name: 'Progresso' })).toHaveAttribute('aria-current', 'page');
});

test('desktop preserva identidade, ações com texto e status de processamento', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await prepareNavigation(page);
  await page.goto('/');
  await expect(page.locator('.app-sidebar')).toBeVisible();
  await expect(page.locator('.mobile-bottom-nav')).not.toBeVisible();
  await expect(page.locator('.mobile-menu-trigger')).not.toBeVisible();
  await expect(page.locator('.account-control')).toBeVisible();
  await expect(page.locator('.download-status')).toBeVisible();
  await expect(page.locator('.navbar-import-button .desktop-only')).toBeVisible();
  await expect(page.locator('.navbar-download-badge')).not.toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
});
