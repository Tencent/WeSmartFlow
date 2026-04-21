---
name: web_search
description: 网络搜索与页面抓取。
---

# 网络搜索

提供三个网络信息检索工具：通用搜索、学术搜索、页面抓取。

## 工具

- `tavily_search` — AI 驱动的网络搜索，返回经过提炼的高质量结果，可附带答案摘要。需要 `TAVILY_API_KEY`。
- `arxiv_search` — 搜索 arXiv 论文，返回标题、作者、摘要和链接。使用英文关键词效果最佳。
- `web_fetch` — 抓取指定 URL 的页面内容，提取为 Markdown 或纯文本。

## 示例

通用网络搜索：
```
tavily_search(query="2024年诺贝尔物理学奖")
```

深度搜索，返回更多结果：
```
tavily_search(query="transformer architecture explained", num_results=8, search_depth="advanced")
```

搜索学术论文：
```
arxiv_search(query="large language model reasoning", max_results=5)
```

搜索后抓取具体页面：
```
web_fetch(url="https://arxiv.org/abs/2301.00001")
```

抓取为纯文本并限制字符数：
```
web_fetch(url="https://example.com/article", extract_mode="text", max_chars=10000)
```

## 提示

- **先搜后抓**：先用 `tavily_search` 搜索，再用 `web_fetch` 深入阅读感兴趣的结果页面。
- **学术问题优先 arxiv**：涉及论文、前沿研究时，直接用 `arxiv_search`，比通用搜索更精准。
- **优化关键词**：如果结果不理想，尝试换用不同或更具体的关键词。
- **注明来源**：回答中始终附上信息来源的 URL。
