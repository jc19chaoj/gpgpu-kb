import { test, expect } from '@playwright/test';

test('chat page sends query and shows answer', async ({ page }) => {
  await page.route('**/api/chat', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ answer: 'Test answer', sources: [] }),
    });
  });

  await page.goto('/chat');

  const input = page.getByPlaceholder(/Ask about GPU/i);
  await input.fill('test query');
  await input.press('Enter');

  await expect(page.getByText('Test answer')).toBeVisible({ timeout: 10000 });
});
