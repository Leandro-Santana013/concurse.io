import { expect, test, type Page } from '@playwright/test';

const exam = {
  id: 99,
  title: 'Prova de demonstração',
  status: 'Sessão',
  has_official_answers: true,
  gabarito_coverage: 100,
  questions: [
    {
      id: 1,
      numero_questao: '1',
      context_text: 'Leia o texto de apoio.',
      statement: 'Qual alternativa está correta?',
      options: { A: 'Alternativa A', B: 'Alternativa B' },
      correct_answer: 'B',
      subject: 'Português',
      images: null,
      has_official_answer: true,
      latex_support: false,
    },
  ],
};

const prepareApi = async (page: Page) => {
  await page.route('**/api/v1/downloads/active', (route) => route.fulfill({ json: [] }));
  await page.route('**/api/v1/folders', (route) => route.fulfill({ json: [] }));
  await page.route('**/api/v1/notebook/stats', (route) => route.fulfill({ json: [] }));
  await page.route('**/api/v1/exams/99', (route) => route.fulfill({ json: exam }));
  await page.route('**/api/v1/exams/attempt', (route) => route.fulfill({
    json: {
      attempt_id: 1,
      exam_id: 99,
      score: 1,
      total: 1,
      percentage: 100,
      elapsed_seconds: 8,
      detailed_answers: {
        '1': {
          question_id: 1,
          user_answer: 'B',
          correct_answer: 'B',
          is_correct: true,
          subject: 'Português',
        },
      },
      feedback_per_subject: {
        Português: { total: 1, correct: 1, percentage: 100 },
      },
    },
  }));
};

for (const viewport of [
  { width: 375, height: 812 },
  { width: 768, height: 900 },
  { width: 1024, height: 900 },
  { width: 1440, height: 900 },
]) {
  test(`início permanece legível em ${viewport.width}px`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await prepareApi(page);
    await page.goto('/');

    await expect(page.getByRole('heading', { name: 'Continue de onde parou.' })).toBeVisible();
    await expect(page.getByRole('link', { name: /Buscar provas/ })).toBeVisible();
    const dimensions = await page.evaluate(() => ({
      clientWidth: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
    }));
    expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth);
  });
}

test('responde, entrega, revisa e refaz um simulado', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await prepareApi(page);
  await page.goto('/prova/99');

  const answer = page.getByRole('radio', { name: /Alternativa B/ });
  await answer.check();
  await answer.check();
  await expect(answer).toBeChecked();

  await page.getByRole('button', { name: 'Entregar simulado' }).click();
  await expect(page.getByRole('dialog', { name: 'Entregar simulado?' })).toBeVisible();
  await page.getByRole('button', { name: 'Confirmar entrega' }).click();

  await expect(page).toHaveURL(/\/prova\/99\/resultado$/);
  await expect(page.getByText('Resultado do simulado')).toBeVisible();
  await page.getByText('Questão 1').click();
  await expect(page.getByText('Leia o texto de apoio.')).toBeVisible();
  await page.getByRole('button', { name: 'Refazer simulado' }).click();
  await expect(page).toHaveURL(/\/prova\/99$/);
  await expect(page.getByRole('heading', { name: 'Questão 1' })).toBeVisible();
});
