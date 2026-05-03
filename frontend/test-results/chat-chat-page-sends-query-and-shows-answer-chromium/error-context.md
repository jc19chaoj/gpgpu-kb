# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: chat.spec.ts >> chat page sends query and shows answer
- Location: tests/e2e/chat.spec.ts:3:5

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: getByText('Test answer')
Expected: visible
Timeout: 10000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" with timeout 10000ms
  - waiting for getByText('Test answer')

```

# Page snapshot

```yaml
- generic [active] [ref=e1]:
  - generic [ref=e2]:
    - complementary "Primary navigation" [ref=e3]:
      - generic [ref=e5]:
        - img [ref=e6]
        - generic [ref=e9]: GPGPU KB
      - navigation [ref=e10]:
        - link "Browse" [ref=e11] [cursor=pointer]:
          - /url: /
          - img [ref=e12]
          - text: Browse
        - link "Chat (RAG)" [ref=e14] [cursor=pointer]:
          - /url: /chat
          - img [ref=e15]
          - text: Chat (RAG)
        - link "Daily Reports" [ref=e17] [cursor=pointer]:
          - /url: /reports
          - img [ref=e18]
          - text: Daily Reports
        - link "Stats" [ref=e21] [cursor=pointer]:
          - /url: /stats
          - img [ref=e22]
          - text: Stats
    - generic [ref=e24]:
      - banner [ref=e25]:
        - generic [ref=e26]: v0.1.0
      - main [ref=e27]:
        - generic [ref=e28]:
          - generic [ref=e30]:
            - generic [ref=e32]:
              - generic [ref=e33]:
                - img [ref=e35]
                - generic [ref=e38]:
                  - generic [ref=e39]: Assistant
                  - paragraph [ref=e41]: I'm your GPGPU research assistant. Ask me anything about papers, architectures, optimizations, or trends in the knowledge base. Pin a source on the right to chat with a single paper or blog (arXiv PDFs are loaded in full).
              - generic [ref=e42]:
                - img [ref=e44]
                - generic [ref=e47]:
                  - generic [ref=e48]: You
                  - paragraph [ref=e50]: test query
              - generic [ref=e51]:
                - img [ref=e53]
                - generic [ref=e56]:
                  - generic [ref=e57]: Assistant
                  - generic [ref=e58]:
                    - paragraph [ref=e59]: 您好，您的问题“test query”似乎是一个测试消息，没有具体询问内容。基于您提供的研究资料，我可以为您总结其中的核心信息，供您参考：
                    - list [ref=e60]:
                      - listitem [ref=e61]:
                        - paragraph [ref=e62]:
                          - strong [ref=e63]: 《Test Design and Review Argumentation in AI-Assisted Test Generation》
                          - text: 提出了测试用例论证结构的四元组模板（目标、声明、理由、证据），使AI生成测试可追溯，评审效率提升约30%，逻辑漏洞识别时间缩短40%。
                      - listitem [ref=e64]:
                        - paragraph [ref=e65]:
                          - strong [ref=e66]: 《Generalizing Test Cases for Comprehensive Test Scenario Coverage》
                          - text: 提出了TestGeneralizer框架，通过泛化初始测试用例实现需求级场景覆盖，在变异杀灭率上提升31.66%，场景覆盖率提升23.08%。
                      - listitem [ref=e67]:
                        - paragraph [ref=e68]:
                          - strong [ref=e69]: 《How Hard is it to Decide if a Fact is Relevant to a Query?》
                          - text: 研究了布尔合取查询中事实相关性判定的复杂度，指出自连接是复杂度升高的根本原因，并给出了可处理性边界的理论分类。
                      - listitem [ref=e70]:
                        - paragraph [ref=e71]:
                          - strong [ref=e72]: "《EviMem: Evidence-Gap-Driven Iterative Retrieval for Long-Term Conversational Memory》"
                          - text: 提出了证据间隙驱动的迭代检索框架，在长期对话记忆中减少检索次数并提升时间/多跳问题准确率，延迟降低至原来的约1/4.5。
                      - listitem [ref=e73]:
                        - paragraph [ref=e74]:
                          - strong [ref=e75]: "《PrismaDV: Automated Task-Aware Data Unit Test Generation》"
                          - text: 实现了任务感知的数据单元测试生成，通过结合代码分析与数据轮廓推断隐含假设，F1分数比基线高15-25%。
                    - paragraph [ref=e76]: 如果您有更具体的问题（例如某篇论文的技术细节、对比分析或实际应用），请进一步说明，我将基于资料和通用知识为您详细解答。
            - generic [ref=e77]:
              - generic [ref=e78]:
                - textbox "Ask about GPU architectures, attention, LLMs..." [ref=e79]
                - button "Send" [disabled]:
                  - img
              - paragraph [ref=e80]: Answers are based on papers in the knowledge base. Results may vary by processing state.
          - complementary [ref=e81]:
            - generic [ref=e82]:
              - tablist [ref=e84]:
                - tab "History" [selected] [ref=e85]:
                  - img
                  - text: History
                - tab "Source" [ref=e86]:
                  - img
                  - text: Source
              - tabpanel "History" [ref=e87]:
                - button "New chat" [ref=e89]:
                  - img
                  - text: New chat
                - generic [ref=e91] [cursor=pointer]:
                  - generic [ref=e92]:
                    - generic [ref=e93]: test query
                    - generic [ref=e95]: just now
                  - button "Delete conversation" [ref=e96]:
                    - img [ref=e97]
  - alert [ref=e100]
```

# Test source

```ts
  1  | import { test, expect } from '@playwright/test';
  2  | 
  3  | test('chat page sends query and shows answer', async ({ page }) => {
  4  |   await page.route('**/api/chat', (route) => {
  5  |     route.fulfill({
  6  |       status: 200,
  7  |       contentType: 'application/json',
  8  |       body: JSON.stringify({ answer: 'Test answer', sources: [] }),
  9  |     });
  10 |   });
  11 | 
  12 |   await page.goto('/chat');
  13 | 
  14 |   const input = page.getByPlaceholder(/Ask about GPU/i);
  15 |   await input.fill('test query');
  16 |   await input.press('Enter');
  17 | 
> 18 |   await expect(page.getByText('Test answer')).toBeVisible({ timeout: 10000 });
     |                                               ^ Error: expect(locator).toBeVisible() failed
  19 | });
  20 | 
```