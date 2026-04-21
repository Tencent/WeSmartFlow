---
name: quiz
description: 出题与测验，评估用户对知识节点的掌握情况。
---

# 出题与测验

用 `create_quiz` 保存题目到数据库。

## 题目类型

| 类型 | quiz_type | 适用场景 |
|------|-----------|---------|
| 单选题 | `multiple_choice` | 概念辨析、易混淆点 |
| 填空题 | `fill_in` | 公式、定义、关键词 |
| 判断题 | `true_false` | 常见误解、边界条件 |
| 开放题 | `open_ended` | 理解深度、应用能力 |

## 原则

- **先出题，再保存**：先在回复中展示题目让用户作答，用户回答后再调用 `create_quiz` 保存
- 优先针对掌握度低（< 0.5）的节点出题
- 一次一题，等用户回答后再决定是否继续
- `explanation` 要解释"为什么"，不只是重复答案

## 流程

1. 构思题目 → 在回复中展示给用户
2. 用户作答 → `create_quiz` 保存（含正确答案和解析）
3. 根据作答情况 → `update_mastery` 更新掌握度

## 示例

保存一道选择题：
```
create_quiz(
  node_id="node_abc123",
  quiz_type="multiple_choice",
  question="快速排序的平均时间复杂度是？",
  options=["A. O(n)", "B. O(n log n)", "C. O(n²)", "D. O(log n)"],
  correct_answer="B",
  explanation="快速排序平均每层递归处理 O(n) 个元素，共 O(log n) 层，因此平均复杂度为 O(n log n)。最坏情况（已排序数组）退化为 O(n²)。"
)
```
