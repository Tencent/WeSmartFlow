---
name: python_repl
description: 通过 exec 工具执行 Python 代码，用于计算、数据处理和分析。
requires: {"bins": ["python3"]}
---

# Python REPL

当需要精确计算、数据处理或算法验证时，通过 `exec` 工具执行 Python 代码。

## 何时使用

- 数学计算（尤其是估算不够准确的复杂计算）
- 数据处理与统计分析
- 算法验证与原型开发
- 文本/数据格式转换
- 生成结构化输出

## 示例

简单计算：
```
exec(command="python3 -c \"print(2 ** 100)\"")
```

多行代码（写入临时文件再执行）：
```
exec(command="python3 << 'EOF'\ndata = [85, 92, 78, 96, 88, 73, 91]\navg = sum(data) / len(data)\nprint(f'均值: {avg:.1f}, 最高: {max(data)}, 最低: {min(data)}')\nEOF")
```

斐波那契数列：
```
exec(command="python3 -c \"\ndef fib(n):\n    a, b = 0, 1\n    for _ in range(n):\n        a, b = b, a + b\n    return a\nprint(fib(50))\n\"")
```

执行已有的 Python 脚本：
```
exec(command="python3 scripts/analysis.py")
```

安装依赖后执行：
```
exec(command="pip install pandas && python3 -c \"import pandas; print(pandas.__version__)\"")
```

## 提示

- **务必用 `print()` 输出结果** — 只有 stdout 会被捕获。
- **复杂代码建议先写入文件**，再用 `exec(command="python3 script.py")` 执行，避免转义问题。
- **可以用 heredoc 语法**（`python3 << 'EOF' ... EOF`）执行多行代码。
- **复杂任务拆分为多次调用**，逐步验证每一步。
- **需要第三方库时**，先用 `exec(command="pip install xxx")` 安装。
