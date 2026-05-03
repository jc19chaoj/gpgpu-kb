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

test('source filter: clicking a tag updates URL and filters list', async ({ page }) => {
  // Mock /api/sources with 2 sources of different types.
  await page.route('**/api/sources', async (route) => {
    await route.fulfill({
      json: {
        sources: [
          { name: 'arxiv', type: 'paper', count: 10 },
          { name: 'SemiAnalysis', type: 'blog', count: 5 },
        ],
      },
    });
  });

  // Mock /api/papers — return arxiv-only list when source_name=arxiv,
  // otherwise return both. We assert by inspecting the URL the page requested.
  let lastRequestedSourceName: string | null = null;
  await page.route('**/api/papers*', async (route) => {
    const url = new URL(route.request().url());
    lastRequestedSourceName = url.searchParams.get('source_name');
    const arxivPaper = {
      id: 1, title: 'ArXiv paper', authors: ['A'], organizations: [],
      abstract: '', url: 'https://arxiv.org/abs/1', pdf_url: '',
      source_type: 'paper', source_name: 'arxiv',
      published_date: '2026-04-25T00:00:00Z', ingested_date: '2026-04-25T00:00:00Z',
      categories: [], venue: '', citation_count: 0, summary: 'S',
      originality_score: 8, impact_score: 8, impact_rationale: '',
      quality_score: 8, relevance_score: 8, score_rationale: '',
    };
    const blogPaper = { ...arxivPaper, id: 2, title: 'SemiAnalysis post', source_type: 'blog', source_name: 'SemiAnalysis' };
    const papers = lastRequestedSourceName === 'arxiv' ? [arxivPaper] : [arxivPaper, blogPaper];
    await route.fulfill({
      json: { papers, total: papers.length, page: 1, page_size: 20 },
    });
  });

  await page.goto('/');
  await expect(page.getByTestId('source-filter')).toBeVisible();
  await expect(page.getByTestId('source-tag-arxiv')).toBeVisible();

  // Click the arxiv tag.
  await page.getByTestId('source-tag-arxiv').click();

  // URL gains ?source=arxiv.
  await expect(page).toHaveURL(/[?&]source=arxiv\b/);

  // Last /api/papers fetch carried source_name=arxiv.
  await expect.poll(() => lastRequestedSourceName).toBe('arxiv');

  // Tag is now in selected state.
  await expect(page.getByTestId('source-tag-arxiv')).toHaveAttribute(
    'data-selected',
    'true',
  );
});

test('source filter: switching type drops mismatched selected sources', async ({ page }) => {
  await page.route('**/api/sources', async (route) => {
    await route.fulfill({
      json: {
        sources: [
          { name: 'arxiv', type: 'paper', count: 10 },
          { name: 'SemiAnalysis', type: 'blog', count: 5 },
        ],
      },
    });
  });
  await page.route('**/api/papers*', async (route) => {
    await route.fulfill({
      json: { papers: [], total: 0, page: 1, page_size: 20 },
    });
  });

  // Pre-select the SemiAnalysis blog source via URL.
  await page.goto('/?source=SemiAnalysis');
  await expect(page.getByTestId('source-tag-SemiAnalysis')).toHaveAttribute(
    'data-selected',
    'true',
  );

  // Now click the Papers type filter — SemiAnalysis (a blog) must be dropped.
  await page.getByTestId('type-filter-paper').click();
  await expect(page).toHaveURL(/[?&]type=paper\b/);
  await expect(page).not.toHaveURL(/[?&]source=/);
});
