# paper_processor
A collection of Python scripts for streamlined academic PDF processing. 

## pdf_process_final

### 简介

基于 Python Tkinter 的 GUI 应用，用于批量处理学术论文 PDF，通过 AI 提取元数据、翻译内容并生成总结，结果导出为 Excel。

### 功能

- 提取论文元数据（期刊名、标题、作者等）
- 翻译标题和摘要为中文
- 总结文章核心发现和结论
- 批量处理 PDF 文件
- 结果导出为 Excel

### 依赖安装
```bash
pip install pandas openai pypdf tkinter
```

## 使用步骤
- 运行脚本：python pdf_process_final.py
- 基础配置：
  - 输入 API 密钥和服务地址
  - 点击 "刷新列表" 获取模型，选择合适模型
- 设置文件路径：
  - 选择包含 PDF 的输入文件夹
  - 设置输出 Excel 文件路径
- 选择任务选项：翻译和 / 或总结
- 点击 "开始处理" 运行，可点击 "停止" 终止

### 注意事项
- 需文本型 PDF，扫描版无法处理
- 确保 API 密钥和服务地址正确
- 处理过程需保持网络连接
- 大量文件建议分批处理
- 配置自动保存至 config.json
