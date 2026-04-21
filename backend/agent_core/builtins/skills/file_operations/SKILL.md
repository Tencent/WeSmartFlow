---
name: file_operations
description: 读写文件、管理工作区文件。
---

# 文件操作

用于在工作区内读取、写入和检查文件的工具集。

## 工具

- `read_file` — 按路径读取文件内容。
- `write_file` — 写入或覆盖文件。
- `list_directory` — 列出目录内容。
- `file_exists` — 检查文件或目录是否存在。

## 示例

读取文件：
```
read_file(path="src/main.py")
```

写入文件：
```
write_file(path="output/report.md", content="# 报告\n\n内容...")
```

列出目录内容：
```
list_directory(path="src/")
```

读取前先检查是否存在：
```
file_exists(path="config.yaml")
```

## 提示

- **始终使用相对路径**，基于工作区根目录。
- **先检查再读取**：对不确定是否存在的文件，先用 `file_exists` 检查。
- **不要读取二进制文件**（图片、PDF 等），它们无法以文本形式呈现。
- **写入时务必确认路径**，避免误覆盖重要文件。
