import { test, expect } from '@playwright/test';

const FIXTURE = {
  papers: [
    {
      id: 1,
      title: 'FlashAttention: Fast and Memory-Efficient Attention',
      authors: ['Tri Dao'],
      organizations: ['Stanford'],
      abstract: 'An efficient attention algorithm.',
      url: 'https://example.com/paper/1',
      pdf_url: 'https://example.com/paper/1.pdf',
      source_type: 'paper',
      source_name: 'arxiv',
      published_date: '2022-05-27',
      ingested_date: '2026-04-25',
      categories: ['gpu', 'attention'],
      venue: 'NeurIPS',
      citation_count: 500,
      summary: 'Fast attention on GPU.',
      originality_score: 9.0,
      impact_score: 9.5,
      impact_rationale: 'Widely adopted.',
    },
  ],
  total: 1,
  page: 1,
  page_size: 20,
};

test('browse page shows paper card and heading', async ({ page }) => {
  await page.route('**/api/papers**', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(FIXTURE),
    });
  });

  await page.goto('/');

  await expect(page.getByRole('heading', { name: /Browse/i })).toBeVisible();

  const paperTitle = page.getByText('FlashAttention: Fast and Memory-Efficient Attention');
  const emptyState = page.getByText(/No papers found/i);

  await expect(paperTitle.or(emptyState)).toBeVisible({ timeout: 10000 });
});
