# -*- coding: utf-8 -*-
"""
文献智能处理工具 v24.0 (UI微调与自定义代理版)

作者: Python Professional (由 Gemini 最终实现)
创建日期: 2025年9月24日
"""

# ==============================================================================
# 导入标准库与第三方库
# ==============================================================================
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import pandas as pd
import openai
import os
import re
import json
from typing import Dict, List
import pypdf
import threading
import queue
import time
import httpx
import webbrowser

# ==============================================================================
# 1. 全局配置
# ==============================================================================
CONFIG_FILE = os.path.join(os.getcwd(), "config.json")
LITERATURE_JSON_FILE = os.path.join(os.getcwd(), "literature_data_for_ai.json")
ai_client = None
stop_event = threading.Event()

# ==============================================================================
# 2. 提示词与指令模板
# ==============================================================================
PROMPT_TEMPLATES = {
    # Part 1: 文献信息提取
    "metadata_system": """
        你是一名顶级的、严谨的科研助理。你的核心任务是快速、准确地从学术论文文本中提取指定信息，并以纯净的JSON格式输出。
        **行为准则:**
        1. **精确提取**: 严格按照用户指令进行信息提取。
        2. **JSON输出**: 最终输出**必须**是单一、无任何修饰的、格式正确的JSON对象。
        3. **结构遵循**: JSON对象必须且仅包含以下键: {keys}。
        4. **无额外内容**: 绝不在JSON对象前后添加任何解释、注释或Markdown标记。
        5. **严谨性**: 若信息在文本中明确未找到，对应的值应为"信息未找到"，禁止猜测或创造。""",
            "metadata_user": """**任务**: 从下方提供的论文文本中，提取以下信息，并返回JSON对象。
        **提取指令**:
        {instructions}
        --- 论文文本开始 ---
        {text}
        --- 论文文本结束 ---""",
    "extraction_details_metadata": """- `journal_name`: 论文发表的期刊或会议名称。\n- `title`: 论文的原始标题。\n- `authors`: 论文的所有作者，用 ", " 分隔。\n- `publication_year`: 论文的发表年份 (4位数字)。\n- `abstract`: 论文的原始英文摘要。\n- `doi`: 文章的DOI链接号。""",
    "extraction_details_translate": """- `title_translated`: 将原始标题翻译成中文。\n- `abstract_translated`: 将原始摘要翻译成通俗易懂、简明扼要的中文。""",
    "extraction_details_summarize_pdf": """- `article_summary`: 用一句话（中文）总结文章的核心发现。\n- `conclusion_opinion`: 用逻辑清晰、条理清楚的中文，分点阐述本文的详细结论和主要结果。""",
    "extraction_details_summarize_txt": """- `article_summary`: 用一句话（中文）总结文章的核心发现。\n- `conclusion_opinion`: 简要总结其中观点。""",

    # Part 2: AI生成综述大纲
    "generate_outline_system": """
    - Role: 顶级学术期刊综述专家
    - Background: 用户需要撰写一篇可以发表在顶级学术期刊论文，用户将提供研究主题以及相关的文献数据。你需要严格按照用户的需求写出论文相应的部分。
    - Profile: 你是一位在顶级学术期刊发表过多篇高质量文献综述部分的专家，对学术研究的前沿动态有着敏锐的洞察力，能够精准把握文献的核心观点和研究趋势，擅长运用严谨的逻辑结构呈现文献综述部分。
    - Skills: 你具备对文献数据进行深度分析和整合的能力，能够运用批判性思维评估文献的价值，掌握顶级学术期刊文献综述部分的撰写规范和格式，善于从大量文献中提炼出关键信息，并将其逻辑清晰地呈现出来。
    - Goals: 根据用户提供的研究主题和文献数据，按照用户要求撰写内容，确保其符合顶级学术期刊的标准，能够为后续的实验和数据研究提供坚实的理论基础。
    - Constrains: 
         1. 文献综述部分应简洁明了，突出重点，避免冗余，确保逻辑连贯，符合顶级学术期刊的撰写规范，同时要精准反映研究主题的核心内容。
         2. 最终输出必须是且只能是纯文本大纲部分，不能有其他任何输出。
    - OutputFormat: 
        - 仅撰写用户指定的论文片段，不涉及其他内容；
        - 必须根据用户提供的文献内容，并使用APA格式进行引用；确保内容的专业性和规范性。
        - 最终输出必须是且只能是纯文本大纲部分，不能有其他任何内容。
    - Workflow:
      1. 解析用户提供的研究主题（【topic】）和文献数据（【json_data】），提取关键信息和核心观点。
      2. 按照逻辑顺序对文献进行分类和整理，构建用户要求进行撰写论文片段。
            """,
            
    "generate_outline_user": """
    **主题**: "{topic}"
    **任务**: 
        - 请基于我提供的以下JSON格式的文献数据，告诉我这个topic的文章的引言部分应该怎么写，给出具体详细的指导大纲。
        - 注意：你只需要给出相应的论文大纲即可，不要写出完整的内容！
    --- 文献数据开始 ---
    {json_data}
    --- 文献数据结束 ---""",

    # Part 3: AI生成完整综述
    "review_system": """
    - Role: 你是一个顶级的学术写作专家和前端开发工程师。
    - Background: 用户需要撰写一篇关于“{topic}”的心理学方向的学术论文片段，且必须基于数十篇文献的总结内容进行撰写。用户期望片段内容专业、规范，并且严格遵循APA格式进行引用和参考文献的标注。
    - Profile: 你是一位在心理学领域有着深厚学术写作经验的专家，熟悉学术论文的结构和撰写规范，尤其擅长将文献内容整合并转化为高质量的学术文本。
    - Goals:
      1. 内容目标: 根据JSON中相关文献数据，撰写一篇关于“{topic}”的专业学术论文片段。
      2. 格式目标: 将内容封装成一个格式简单、独立的HTML文档。
      3. 参考文献目标: 在HTML末尾，生成一个严格遵循APA第7版格式的“参考文献”(References)列表。列表包含本次综述使用的文献
    - Skills: 你具备文献综述、学术写作、APA格式引用等关键能力，能够精准地提取文献中的核心观点，并将其融入到指定的学术论文片段中。
    - OutputFormat: 一份学术论文综述HTML文档，包含APA格式的引用和参考文献列表。
    - Constrains:
      - 数据理解: 你必须智能地解析用户提供的JSON数据。根据每个键(key)的名称来判断其对应的文献信息。
      - 内容约束: 仅使用用户提供的JSON数据，不得引入外部信息。
      - 结构约束: **必须严格遵循**用户提供的【大纲与要求】来组织文章结构。
      - 格式约束: 最终输出必须是且只能是完整的HTML代码，以`<!DOCTYPE html>`开头，以`</html>`结尾。
    - Workflow:
      1. 分析JSON，理解每列代表什么信息。
      2. 严格按照【大纲与要求】构建文章框架。
      3. 撰写正文，从JSON中提取观点填充到大纲相应部分，并进行APA文中引用。
      4. 生成APA第7版格式的参考文献列表。
      5. 将所有内容封装到包含基础CSS的HTML文档中。""",
      
      "review_user": """
      这是本次任务需要处理的数据和必须遵循的大纲：
    ---
    【大纲与要求】: 该部分为用户指定的文章片段大纲和具体要求
    {outline}
    ---
    ---
    【文献数据 (JSON格式)】
    {json_data}
    ---
    现在，请严格遵循你在系统指令中被设定的所有规则，开始执行任务。"""
}

COLUMN_SETS = {
    "base": ["file_path"],
    "metadata": ["journal_name", "title", "authors", "publication_year", "abstract", "doi"],
    "translate": ["title_translated", "abstract_translated"],
    "summarize": ["article_summary", "conclusion_opinion"]
}
PLACEHOLDER = "AI处理失败或信息未找到"


# ==============================================================================
# 3. 核心后台任务函数
# ==============================================================================

def get_openai_client(config: Dict):
    """
    根据配置动态创建OpenAI客户端。

    Args:
        config (Dict): 从GUI收集的配置，包含API密钥、URL、代理和超时设置。
    """
    http_client = None
    proxy_url = config.get("proxy_address", "").strip()
    if config.get('use_proxy') and proxy_url:
        proxies = { "http://": proxy_url, "https://": proxy_url }
        http_client = httpx.Client(proxies=proxies, verify=False)

    return openai.OpenAI(
        api_key=config['api_key'],
        base_url=config['base_url'],
        timeout=float(config.get('timeout', 300.0)),
        http_client=http_client
    )

def _split_text_into_articles(text: str) -> List[str]:
    """从TXT文件中按编号规则分割出多篇文章。"""
    articles = re.split(r'\n(?=\d+\.\s[A-Z])', text.strip())
    return [article.strip() for article in articles if article.strip()]

def run_main_task(config, msg_queue):
    """
    【后台任务】批量处理PDF或TXT文件，提取信息并存入Excel。

    Args:
        config (Dict): UI配置。
        msg_queue (queue.Queue): 与UI通信的队列。
    """
    start_time = time.time()
    global ai_client
    try:
        ai_client = get_openai_client(config)
        ai_client.models.list()
    except Exception as e:
        msg_queue.put(('log', f"❌ 初始化或连接AI失败: {e}"))
        msg_queue.put(('task_done', None)); return

    msg_queue.put(('log', "--- 开始执行批量处理任务 ---"))
    
    input_path = config['input_path']
    items_to_process, processing_mode = [], None

    if os.path.isdir(input_path):
        processing_mode = 'pdf'
        items_to_process = [os.path.join(input_path, f) for f in os.listdir(input_path) if f.lower().endswith('.pdf')]
    elif os.path.isfile(input_path):
        processing_mode = 'txt'
        try:
            with open(input_path, 'r', encoding='utf-8') as f: content = f.read()
            items_to_process = _split_text_into_articles(content)
        except Exception as e:
            msg_queue.put(('log', f"❌ 读取或解析TXT文件失败: {e}"))
            msg_queue.put(('task_done', None)); return
    
    if not items_to_process:
        msg_queue.put(('log', f"❌ 在路径 '{input_path}' 中未找到可处理的项目。"))
        msg_queue.put(('task_done', None)); return

    msg_queue.put(('log', f"➡️ 模式: '{processing_mode.upper()}'。本次任务共需处理 {len(items_to_process)} 个项目。"))
    
    instruction_fragments = [PROMPT_TEMPLATES['extraction_details_metadata']]
    ai_requested_columns = COLUMN_SETS['metadata'][:]
    
    if config['do_translate']:
        instruction_fragments.append(PROMPT_TEMPLATES['extraction_details_translate'])
        ai_requested_columns.extend(COLUMN_SETS['translate'])

    if processing_mode == 'pdf':
        instruction_fragments.append(PROMPT_TEMPLATES['extraction_details_summarize_pdf'])
    else:
        instruction_fragments.append(PROMPT_TEMPLATES['extraction_details_summarize_txt'])
    ai_requested_columns.extend(COLUMN_SETS['summarize'])
    
    final_instruction_text = "\n".join(instruction_fragments)
    final_columns = COLUMN_SETS['base'] + ai_requested_columns

    all_results = []
    for i, item in enumerate(items_to_process):
        text, current_file_path, log_header = "", "", ""

        if processing_mode == 'pdf':
            current_file_path = item
            log_header = f"--- 正在处理PDF: {os.path.basename(current_file_path)} ({i+1}/{len(items_to_process)}) ---"
            try:
                with open(current_file_path, 'rb') as pdf_file:
                    reader = pypdf.PdfReader(pdf_file)
                    text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
            except Exception as e: 
                msg_queue.put(('log', f"   ❌ 读取PDF文件失败: {e}"))
        else: # TXT Mode
            text = item
            current_file_path = input_path 
            log_header = f"--- 正在处理文章 {i+1}/{len(items_to_process)} ---"

        msg_queue.put(('log', f"\n{log_header}"))

        ai_result = None
        if text:
            system_prompt = PROMPT_TEMPLATES["metadata_system"].format(keys=json.dumps(ai_requested_columns, ensure_ascii=False))
            user_prompt = PROMPT_TEMPLATES["metadata_user"].format(instructions=final_instruction_text, text=text[:20000])
            try:
                msg_queue.put(('log', "   - 正在发送至AI进行分析..."))
                response = ai_client.chat.completions.create(model=config['model_name'], messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}], max_tokens=config['max_tokens'], temperature=0.1, response_format={"type": "json_object"})
                content = response.choices[0].message.content.strip()
                if content.startswith("```"): content = content.strip("```json\n").strip("```")
                ai_result = json.loads(content)
                msg_queue.put(('log', "   ✅ AI成功返回结构化数据。"))
            except Exception as e: 
                msg_queue.put(('log', f"   ❌ 调用AI时发生错误: {e}"))
        else:
            msg_queue.put(('log', "   - 文本内容为空，跳过AI分析。"))

        entry = {'file_path': current_file_path}
        for col in ai_requested_columns:
            entry[col] = ai_result.get(col, PLACEHOLDER) if ai_result else "文本提取失败"
        all_results.append(entry)

    if all_results:
        try:
            pd.DataFrame(all_results).reindex(columns=final_columns).to_excel(config['output_excel'], index=False)
            msg_queue.put(('log', f"\n💾 处理完成，结果已保存到: {os.path.basename(config['output_excel'])}"))
        except Exception as e: 
            msg_queue.put(('log', f"❌ 保存Excel时发生严重错误: {e}."))
    
    duration = time.time() - start_time
    msg_queue.put(('log', f"\n\n🎉🎉🎉 文献处理任务完成！总耗时: {duration:.2f} 秒。"))
    msg_queue.put(('task_done', None))

def run_generate_outline_task(config, excel_path, topic, msg_queue):
    """【后台任务】为指定主题和文献数据生成一份综述大纲。"""
    start_time = time.time()
    global ai_client
    msg_queue.put(('log', "\n--- 开始执行“AI生成综述大纲”任务 ---"))
    
    try:
        ai_client = get_openai_client(config)
        ai_client.models.list()
        msg_queue.put(('log', f"✅ AI客户端初始化成功。"))
    except Exception as e:
        msg_queue.put(('log', f"❌ 初始化或连接AI失败: {e}"))
        msg_queue.put(('task_done', None)); return

    try:
        msg_queue.put(('log', f"   - 正在读取文献文件: {os.path.basename(excel_path)}"))
        df = pd.read_excel(excel_path, engine='openpyxl')
        json_content = df.to_json(orient='records', indent=2, force_ascii=False)
        msg_queue.put(('log', f"   - 成功加载 {len(df)} 篇文献。"))
    except Exception as e:
        msg_queue.put(('log', f"❌ 读取Excel或转换JSON时出错: {e}"))
        msg_queue.put(('task_done', None)); return

    system_prompt = PROMPT_TEMPLATES["generate_outline_system"]
    user_prompt = PROMPT_TEMPLATES["generate_outline_user"].format(topic=topic, json_data=json_content)
    
    try:
        msg_queue.put(('log', "   - 正在请求AI生成大纲..."))
        response = ai_client.chat.completions.create(model=config['model_name'], messages=[ {"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt} ], max_tokens=config['max_tokens'], temperature=0.3, stream=False)
        outline_content = response.choices[0].message.content.strip()
        msg_queue.put(('outline_result', outline_content))
        msg_queue.put(('log', "   ✅ AI成功返回大纲，已更新到文本框。"))
    except Exception as e:
        msg_queue.put(('log', f"❌ AI生成大纲时发生错误: {e}"))
    finally:
        duration = time.time() - start_time
        msg_queue.put(('log', f"🎉 大纲生成任务完成！耗时: {duration:.2f} 秒。"))
        msg_queue.put(('task_done', None))

def run_review_from_excel_task(config, excel_path, topic, output_html_path, review_outline, msg_queue):
    """【后台任务】生成最终的HTML格式文献综述。"""
    start_time = time.time()
    global ai_client
    msg_queue.put(('log', "\n--- 开始执行“生成主题综述HTML”任务 ---"))
    
    try:
        ai_client = get_openai_client(config)
        ai_client.models.list()
        msg_queue.put(('log', f"✅ AI客户端初始化成功。"))
    except Exception as e:
        msg_queue.put(('log', f"❌ 初始化或连接AI失败: {e}"))
        msg_queue.put(('task_done', None)); return
    
    try:
        msg_queue.put(('log', f"   - 正在读取文献文件: {os.path.basename(excel_path)}"))
        df = pd.read_excel(excel_path, engine='openpyxl')
        json_content_for_file = df.to_json(orient='records', indent=2, force_ascii=False)
        with open(LITERATURE_JSON_FILE, 'w', encoding='utf-8') as f: f.write(json_content_for_file)
        msg_queue.put(('log', f"   - 成功加载 {len(df)} 篇文献。"))
    except Exception as e:
        msg_queue.put(('log', f"❌ 读取Excel或转换JSON时出错: {e}"))
        msg_queue.put(('task_done', None)); return
    
    system_prompt = PROMPT_TEMPLATES["review_system"].format(topic=topic)
    user_prompt = PROMPT_TEMPLATES["review_user"].format(outline=review_outline, json_data=json_content_for_file)
    
    try:
        msg_queue.put(('log', "   - 正在请求AI撰写完整综述..."))
        response = ai_client.chat.completions.create(model=config['model_name'], messages=[ {"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt} ], max_tokens=config['max_tokens'], temperature=0.3, stream=False)
        html_content = response.choices[0].message.content.strip()
        html_start_index = html_content.find('<!DOCTYPE html>')
        if html_start_index > 0: html_content = html_content[html_start_index:]
        
        with open(output_html_path, 'w', encoding='utf-8') as f: f.write(html_content)
        msg_queue.put(('log', f"✅ 综述已成功保存为HTML文件: {os.path.basename(output_html_path)}"))
    except Exception as e:
        msg_queue.put(('log', f"❌ AI生成综述时发生错误: {e}"))
    finally:
        duration = time.time() - start_time
        msg_queue.put(('log', f"\n\n🎉🎉🎉 生成综述任务完成！总耗时: {duration:.2f} 秒。"))
        msg_queue.put(('task_done', None))


def run_generate_interactive_html_task(excel_path, msg_queue):
    """【后台任务】生成一个内嵌数据的交互式HTML报告。"""
    start_time = time.time()
    msg_queue.put(('log', "\n--- 开始执行“生成交互式HTML报告”任务 ---"))

    if not os.path.exists(excel_path):
        msg_queue.put(('log', f"❌ 错误：Excel文件不存在于路径 '{excel_path}'"))
        msg_queue.put(('task_done', None))
        return

    try:
        msg_queue.put(('log', f"  - 正在读取数据文件: {os.path.basename(excel_path)}"))
        df = pd.read_excel(excel_path, engine='openpyxl')
        # 将 NaN 值转换为空字符串，避免在JSON中出现 null
        df = df.fillna('')
        json_data = df.to_json(orient='records', force_ascii=False)
        msg_queue.put(('log', f"  - 成功加载 {len(df)} 条记录。"))
    except Exception as e:
        msg_queue.put(('log', f"❌ 读取Excel或转换为JSON时出错: {e}"))
        msg_queue.put(('task_done', None))
        return

    # HTML 模板，注意其中的 {embedded_data_json} 是我们注入数据的占位符
    html_template = """
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>文献编辑器</title>
        <script src="https://cdn.sheetjs.com/xlsx-latest/package/dist/xlsx.full.min.js"></script>
        <style>
            :root {
                --primary-color: #007bff; --border-color: #dee2e6; --background-light: #f8f9fa;
                --text-color: #212529; --white-color: #fff; --danger-color: #dc3545; --success-color: #28a745;
            }
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; margin: 0; padding: 20px; background-color: var(--background-light); color: var(--text-color); }
            .app-container { display: flex; gap: 20px; width: 100%; max-width: 1800px; margin: 0 auto; }
            #file-input { display: none; }
            .controls { flex: 0 0 100px; padding: 10px; background-color: var(--white-color); border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); height: fit-content; }
            .controls h3 { margin-top: 0; margin-bottom: 10px; font-size: 16px; border-bottom: 1px solid var(--border-color); padding-bottom: 8px; }
            .control-group label { display: block; margin-bottom: 8px; cursor: pointer; user-select: none; font-size: 16px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
            .file-select-btn, .export-btn { display: block; width: 100%; padding: 8px 10px; border: none; border-radius: 5px; color: var(--white-color); font-size: 16px; text-align: center; cursor: pointer; box-sizing: border-box; }
            .file-select-btn { margin-bottom: 15px; background-color: var(--primary-color); }
            .export-btn { margin-top: 15px; background-color: var(--success-color); }
            .table-container { flex-grow: 1; overflow-x: auto; }
            table { width: 100%; border-collapse: collapse; }
            th, td { padding: 10px 12px; border: 1px solid var(--border-color); text-align: left; vertical-align: top; font-size: 14px; }
            thead { background-color: var(--primary-color); color: var(--white-color); position: sticky; top: 0; z-index: 10; }
            tbody tr:nth-of-type(even) { background-color: #f8f9fa; }
            tbody tr:hover { background-color: #e9ecef; }
            a { color: #0056b3; text-decoration: none; font-weight: 500; }
            .notes-cell { border: none; padding: 0; vertical-align: top; }
            textarea.note-input { width: 100%; border: none; border-left: 1px solid var(--border-color); border-top: 1px solid var(--border-color); box-sizing: border-box; padding: 10px; font-family: inherit; font-size: 14px; background-color: transparent; border-radius: 0; outline: none; resize: none; overflow: hidden; }
            tr:last-child .notes-cell textarea.note-input{ border-bottom: 1px solid var(--border-color); }
            .delete-btn { padding: 5px 10px; border: none; border-radius: 4px; background-color: var(--danger-color); color: white; cursor: pointer; }
        </style>
    </head>
    <body>
        <input type="file" id="file-input" accept=".xlsx, .xls, .csv">
        <div class="app-container" id="app-container">
            <aside class="controls">
                <label for="file-input" class="file-select-btn">选择文件</label>
                <div id="controls-content" style="display: none;">
                    <h3>显示列</h3>
                    <div id="column-toggles" class="control-group"></div>
                    <button id="export-button" class="export-btn">导出</button>
                </div>
            </aside>
            <main class="table-container">
                <table id="dataTable">
                    <thead></thead>
                    <tbody>
                        <tr id="initial-placeholder">
                            <td colspan="100%" style="text-align: center; padding: 40px; font-size: 16px;">
                                正在加载预设数据...
                            </td>
                        </tr>
                    </tbody>
                </table>
            </main>
        </div>
        <script>
            // 这是我们从Python注入的数据
            const embeddedData = {embedded_data_json};
        </script>
        <script>
        document.addEventListener('DOMContentLoaded', () => {
            let literatureData = [];
            let allColumns = [];
            const defaultVisibleColumns = ['title_translated', 'authors', 'article_summary', 'abstract_translated'];

            const fileInput = document.getElementById('file-input');
            const controlsContent = document.getElementById('controls-content');
            const table = document.getElementById('dataTable');
            const tableHead = table.querySelector('thead');
            const tableBody = table.querySelector('tbody');
            const togglesContainer = document.getElementById('column-toggles');
            const exportButton = document.getElementById('export-button');

            function autoGrow(element) {
                element.style.height = "auto";
                element.style.height = (element.scrollHeight) + "px";
            }
            
            function processData(jsonData) {
                try {
                    literatureData = jsonData.map(row => ({...row, notes: row.notes || ''}));
                    if (literatureData.length > 0) {
                        allColumns = Object.keys(literatureData[0]);
                        controlsContent.style.display = 'block';
                        renderToggles();
                        renderTable();
                    } else { 
                        tableBody.innerHTML = '<tr><td colspan="100%" style="text-align:center;padding:40px;">数据文件为空或格式不正确。</td></tr>';
                    }
                } catch(error) {
                    alert("数据处理失败: " + error.message);
                }
            }

            function handleFile(event) {
                const file = event.target.files[0];
                if (!file) return;
                const reader = new FileReader();
                reader.onload = function(e) {
                    const data = new Uint8Array(e.target.result);
                    const workbook = XLSX.read(data, { type: 'array' });
                    const firstSheetName = workbook.SheetNames[0];
                    const worksheet = workbook.Sheets[firstSheetName];
                    processData(XLSX.utils.sheet_to_json(worksheet));
                };
                reader.readAsArrayBuffer(file);
            }

            fileInput.addEventListener('change', handleFile);

            function renderToggles() {
                togglesContainer.innerHTML = '';
                const columnsToToggle = allColumns.filter(col => col !== 'notes');
                columnsToToggle.forEach(col => {
                    const isChecked = defaultVisibleColumns.includes(col);
                    const label = document.createElement('label');
                    label.innerHTML = `<input type="checkbox" value="${col}" ${isChecked ? 'checked' : ''}> ${col}`;
                    label.title = col;
                    togglesContainer.appendChild(label);
                });
                updateColumnVisibility();
            }

            function renderTable() {
                tableHead.innerHTML = '';
                tableBody.innerHTML = '';

                if (literatureData.length === 0) {
                    tableBody.innerHTML = '<tr><td colspan="100%" style="text-align: center; padding: 20px;">没有数据或所有数据已被删除。</td></tr>';
                    return;
                }
                
                const headerRow = document.createElement('tr');
                const columnsToRender = allColumns.filter(col => col !== 'notes');
                
                columnsToRender.forEach(key => {
                    const th = document.createElement('th');
                    th.textContent = key;
                    th.className = `col-${key}`;
                    headerRow.appendChild(th);
                });
                headerRow.innerHTML += '<th>笔记</th><th>操作</th>';
                tableHead.appendChild(headerRow);

                literatureData.forEach((item, index) => {
                    const row = document.createElement('tr');
                    row.dataset.rowIndex = index;
                    columnsToRender.forEach(key => {
                        const cell = document.createElement('td');
                        cell.className = `col-${key}`;
                        const cellValue = item[key] !== null && item[key] !== undefined ? item[key] : '';
                        
                        if (key === 'title' && item.doi) {
                            cell.innerHTML = `<a href="${item.doi}" target="_blank" rel="noopener noreferrer">${cellValue}</a>`;
                        } else {
                            cell.textContent = cellValue;
                        }
                        row.appendChild(cell);
                    });
                    
                    const notesCell = document.createElement('td');
                    notesCell.className = 'notes-cell';
                    notesCell.innerHTML = `<textarea class="note-input">${item.notes || ''}</textarea>`;
                    
                    const actionsCell = document.createElement('td');
                    actionsCell.innerHTML = `<button class="delete-btn">删除</button>`;
                    
                    row.appendChild(notesCell);
                    row.appendChild(actionsCell);
                    
                    tableBody.appendChild(row);
                });
                
                updateColumnVisibility();
                document.querySelectorAll('.note-input').forEach(textarea => autoGrow(textarea));
            }

            function updateColumnVisibility() {
                const visibleColumns = new Set();
                togglesContainer.querySelectorAll('input[type="checkbox"]').forEach(cb => {
                    if (cb.checked) visibleColumns.add(cb.value);
                });
                allColumns.forEach(col => {
                    table.querySelectorAll(`.col-${col}`).forEach(el => {
                        el.style.display = visibleColumns.has(col) ? '' : 'none';
                    });
                });
            }

            togglesContainer.addEventListener('change', updateColumnVisibility);
            tableBody.addEventListener('input', e => {
                if (e.target.classList.contains('note-input')) {
                    const rowIndex = e.target.closest('tr').dataset.rowIndex;
                    literatureData[rowIndex].notes = e.target.value;
                    autoGrow(e.target);
                }
            });
            tableBody.addEventListener('click', e => {
                if (e.target.classList.contains('delete-btn')) {
                    const rowIndex = parseInt(e.target.closest('tr').dataset.rowIndex, 10);
                    literatureData.splice(rowIndex, 1);
                    renderTable();
                }
            });
            exportButton.addEventListener('click', () => {
                if (literatureData.length === 0) return alert("没有数据可导出！");
                const worksheet = XLSX.utils.json_to_sheet(literatureData);
                const workbook = XLSX.utils.book_new();
                XLSX.utils.book_append_sheet(workbook, worksheet, "文献笔记");
                XLSX.writeFile(workbook, `summary_output_edited_${new Date().toISOString().slice(0,10)}.xlsx`);
            });

            // 自动加载嵌入的数据
            if (typeof embeddedData !== 'undefined' && Array.isArray(embeddedData)) {
                processData(embeddedData);
            } else {
                const placeholder = document.getElementById('initial-placeholder');
                if(placeholder) placeholder.querySelector('td').textContent = "请点击左侧“选择文件”加载您的Excel数据。";
            }
        });
        </script>
    </body>
    </html>
    """
    
    # 将JSON数据安全地注入HTML模板
    final_html = html_template.replace('{embedded_data_json}', json_data)
    
    # 定义输出文件名
    base_name = os.path.splitext(excel_path)[0]
    output_html_path = f"{base_name}_interactive.html"
    
    try:
        with open(output_html_path, 'w', encoding='utf-8') as f:
            f.write(final_html)
        msg_queue.put(('log', f"✅ 交互式报告已成功保存为: {os.path.basename(output_html_path)}"))

        # 自动打开HTML文件
        url = 'file://' + os.path.abspath(output_html_path)
        webbrowser.open(url, new=2)
    except Exception as e:
        msg_queue.put(('log', f"❌ 保存或打开HTML文件时发生错误: {e}"))
    finally:
        duration = time.time() - start_time
        msg_queue.put(('log', f"🎉 交互式报告生成任务完成！耗时: {duration:.2f} 秒。"))
        msg_queue.put(('task_done', None))

# ==============================================================================
# 4. GUI界面代码 (Tkinter)
# ==============================================================================
class App(tk.Tk):
    def __init__(self):
        """初始化应用程序主窗口。"""
        super().__init__()
        self.title("文献智能处理工具 v24.0 (UI微调与自定义代理版)")
        self.geometry("1000x650") # 恢复窗口尺寸

        self.msg_queue = queue.Queue()
        self.control_widgets = []
        self._queue_job = None
        
        self._create_widgets()
        self.load_config()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.process_queue()

    def _create_widgets(self):
        """创建并布局所有GUI控件。"""
        main_paned_window = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        main_paned_window.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        controls_frame = ttk.Frame(main_paned_window, width=450)
        main_paned_window.add(controls_frame, weight=2)
        
        right_pane = ttk.PanedWindow(main_paned_window, orient=tk.VERTICAL)
        main_paned_window.add(right_pane, weight=3)
        
        # --- 1. 基础配置 ---
        ai_frame = ttk.LabelFrame(controls_frame, text="1. 基础配置", padding="10")
        ai_frame.pack(fill=tk.X, pady=5, padx=5)

        ttk.Label(ai_frame, text="API密钥:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=3)
        self.api_key_var = tk.StringVar(); api_entry = ttk.Entry(ai_frame, textvariable=self.api_key_var)
        api_entry.grid(row=0, column=1, sticky=tk.EW, columnspan=3)
        
        ttk.Label(ai_frame, text="服务地址:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=3)
        self.base_url_var = tk.StringVar(); url_entry = ttk.Entry(ai_frame, textvariable=self.base_url_var)
        url_entry.grid(row=1, column=1, sticky=tk.EW, columnspan=3)
        
        ttk.Label(ai_frame, text="模型名称:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=3)
        self.model_name_var = tk.StringVar(); self.model_combo = ttk.Combobox(ai_frame, textvariable=self.model_name_var)
        self.model_combo.grid(row=2, column=1, sticky=tk.EW, columnspan=2)
        refresh_btn = ttk.Button(ai_frame, text="刷新", command=self.fetch_models_thread, width=6)
        refresh_btn.grid(row=2, column=3, padx=5, sticky=tk.W)

        # Max Tokens 和 Timeout 放在同一行
        tokens_timeout_frame = ttk.Frame(ai_frame)
        tokens_timeout_frame.grid(row=3, column=1, columnspan=3, sticky=tk.W, padx=0, pady=0)
        
        ttk.Label(tokens_timeout_frame, text="Max Tokens:").pack(side=tk.LEFT, padx=(5,0))
        self.max_tokens_var = tk.IntVar(value=8000)
        tokens_entry = ttk.Entry(tokens_timeout_frame, textvariable=self.max_tokens_var, width=8)
        tokens_entry.pack(side=tk.LEFT, padx=(5,10))
        
        ttk.Label(tokens_timeout_frame, text="超时(秒):").pack(side=tk.LEFT)
        self.timeout_var = tk.IntVar(value=300)
        timeout_entry = ttk.Entry(tokens_timeout_frame, textvariable=self.timeout_var, width=8)
        timeout_entry.pack(side=tk.LEFT, padx=5)
        
        # 代理控件
        proxy_frame = ttk.Frame(ai_frame)
        proxy_frame.grid(row=4, column=0, columnspan=4, sticky=tk.W, padx=0, pady=3)
        self.use_proxy_var = tk.BooleanVar(value=False)
        proxy_check = ttk.Checkbutton(proxy_frame, text="使用网络代理:", variable=self.use_proxy_var)
        proxy_check.pack(side=tk.LEFT, anchor=tk.W)
        self.proxy_address_var = tk.StringVar(value="http://127.0.0.1:7890") 
        proxy_entry = ttk.Entry(proxy_frame, textvariable=self.proxy_address_var, width=50)
        proxy_entry.pack(side=tk.LEFT, anchor=tk.W, padx=5)

        ai_frame.columnconfigure(1, weight=1)

        # --- 2. 文献处理 ---
        pdf_io_frame = ttk.LabelFrame(controls_frame, text="2. 文献处理 (生成Excel)", padding="10")
        pdf_io_frame.pack(fill=tk.X, pady=5, padx=5)

        ttk.Label(pdf_io_frame, text="输入路径:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=3)
        self.input_path_var = tk.StringVar(); in_entry = ttk.Entry(pdf_io_frame, textvariable=self.input_path_var, state='readonly')
        in_entry.grid(row=0, column=1, sticky=tk.EW)
        browse_buttons_frame = ttk.Frame(pdf_io_frame)
        browse_buttons_frame.grid(row=0, column=2, padx=5)
        pdf_btn = ttk.Button(browse_buttons_frame, text="PDF文件夹", command=self.select_pdf_folder, width=12)
        pdf_btn.pack(side=tk.LEFT, padx=(0, 2))
        txt_btn = ttk.Button(browse_buttons_frame, text="TXT文件", command=self.select_txt_file, width=10)
        txt_btn.pack(side=tk.LEFT)
        
        ttk.Label(pdf_io_frame, text="输出文件:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=3)
        self.output_excel_var = tk.StringVar(); out_entry = ttk.Entry(pdf_io_frame, textvariable=self.output_excel_var)
        out_entry.grid(row=1, column=1, sticky=tk.EW)
        saveas_btn = ttk.Button(pdf_io_frame, text="另存为", command=self.browse_output_excel, width=12)
        saveas_btn.grid(row=1, column=2, padx=5, sticky=tk.W) # 左对齐
        
        # “翻译”和“开始”按钮放在同一行
        proc_action_frame = ttk.Frame(pdf_io_frame)
        proc_action_frame.grid(row=2, column=1, columnspan=2, sticky=tk.W, pady=5)
        self.translate_var = tk.BooleanVar(value=True)
        trans_check = ttk.Checkbutton(proc_action_frame, text="翻译标题和摘要", variable=self.translate_var)
        trans_check.pack(side=tk.LEFT, padx=5)
        self.start_button = ttk.Button(proc_action_frame, text="开始文献处理", command=self.start_processing_thread)
        self.start_button.pack(side=tk.LEFT, padx=5)
        
        # html处理
        self.interactive_html_button = ttk.Button(proc_action_frame, text="生成交互式报告", command=self.start_generate_interactive_html_thread)
        self.interactive_html_button.pack(side=tk.LEFT, padx=5)
        
        pdf_io_frame.columnconfigure(1, weight=1)

        # --- 3. 主题综述 ---
        review_io_frame = ttk.LabelFrame(controls_frame, text="3. 主题综述 (生成HTML)", padding="10")
        review_io_frame.pack(fill=tk.X, pady=5, padx=5)
        
        ttk.Label(review_io_frame, text="综述主题:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=3)
        self.review_topic_var = tk.StringVar(); topic_entry = ttk.Entry(review_io_frame, textvariable=self.review_topic_var)
        topic_entry.grid(row=0, column=1, sticky=tk.EW, columnspan=2)
        
        ttk.Label(review_io_frame, text="文献源文件:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=3)
        self.review_input_excel_var = tk.StringVar(); review_in_entry = ttk.Entry(review_io_frame, textvariable=self.review_input_excel_var, state='readonly')
        review_in_entry.grid(row=1, column=1, sticky=tk.EW)
        review_in_btn = ttk.Button(review_io_frame, text="浏览...", command=self.select_review_input_excel, width=10)
        review_in_btn.grid(row=1, column=2, padx=5)
        
        ttk.Label(review_io_frame, text="综述输出路径:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=3)
        self.review_output_html_var = tk.StringVar(); review_out_entry = ttk.Entry(review_io_frame, textvariable=self.review_output_html_var)
        review_out_entry.grid(row=2, column=1, sticky=tk.EW)
        review_out_btn = ttk.Button(review_io_frame, text="另存为...", command=self.browse_review_output_html, width=10)
        review_out_btn.grid(row=2, column=2, padx=5)
        
        review_action_frame = ttk.Frame(review_io_frame)
        review_action_frame.grid(row=3, column=1, columnspan=2, sticky=tk.W, pady=5)
        self.generate_outline_button = ttk.Button(review_action_frame, text="AI生成大纲", command=self.start_generate_outline_thread)
        self.generate_outline_button.pack(side=tk.LEFT, padx=5)
        self.review_button = ttk.Button(review_action_frame, text="开始生成综述", command=self.start_review_from_excel_thread)
        self.review_button.pack(side=tk.LEFT, padx=5)
        review_io_frame.columnconfigure(1, weight=1)

        # --- 右侧面板 ---
        review_outline_frame = ttk.LabelFrame(right_pane, text="综述大纲")
        right_pane.add(review_outline_frame, weight=2)
        self.review_outline_text = scrolledtext.ScrolledText(review_outline_frame, wrap=tk.WORD, height=10)
        self.review_outline_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.review_outline_text.insert(tk.END, "请在此处输入您期望的综述文章结构，例如：\n\n1. 引言：简要介绍研究背景和问题。\n2. 核心概念：阐述...理论/模型。\n3. 主要发现：总结各文献的关键结果...\n4. 讨论与展望：...")
        
        log_frame = ttk.LabelFrame(right_pane, text="运行日志")
        right_pane.add(log_frame, weight=3)
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.log_text.config(state='disabled')

        self.control_widgets.extend([
            api_entry, url_entry, self.model_combo, refresh_btn, tokens_entry, timeout_entry, proxy_check, proxy_entry,
            in_entry, pdf_btn, txt_btn, out_entry, saveas_btn, trans_check, self.start_button,
            self.interactive_html_button, # <--- 在这里添加新按钮变量
            topic_entry, review_in_entry, review_in_btn, review_out_entry, review_out_btn,
            self.generate_outline_button, self.review_button
        ])
    
    def process_queue(self):
        """定时从队列中获取消息并安全地更新UI。"""
        try:
            while not self.msg_queue.empty():
                msg_type, content = self.msg_queue.get_nowait()
                if msg_type == 'log':
                    self.log_text.config(state='normal'); self.log_text.insert(tk.END, content + '\n'); self.log_text.see(tk.END); self.log_text.config(state='disabled')
                elif msg_type == 'models':
                    current_selection = self.model_name_var.get()
                    self.model_combo.config(values=content)
                    if current_selection and current_selection in content: self.model_name_var.set(current_selection)
                    elif content: self.model_name_var.set(content[0])
                    else: self.model_name_var.set('')
                    self.msg_queue.put(('log', "✅ 模型列表已刷新。"))
                elif msg_type == 'outline_result':
                    self.review_outline_text.delete('1.0', tk.END)
                    self.review_outline_text.insert('1.0', content)
                elif msg_type == 'task_done':
                    self.update_ui_states(processing=False)
        except queue.Empty: pass
        finally:
            self._queue_job = self.after(100, self.process_queue)

    def start_generate_outline_thread(self):
        """启动“AI生成大纲”后台任务。"""
        config = self.get_config()
        topic = self.review_topic_var.get().strip()
        excel_path = self.review_input_excel_var.get()
        if not all([config['api_key'], config['base_url'], config['model_name'], topic, excel_path]):
            messagebox.showwarning("信息不完整", "请检查API配置、综述主题和文献源文件是否都已填写！")
            return
        self.update_ui_states(processing=True)
        threading.Thread(target=run_generate_outline_task, args=(config, excel_path, topic, self.msg_queue), daemon=True).start()
    
    def start_processing_thread(self):
        """启动“文献处理”后台任务。"""
        config = self.get_config()
        if not all([config['api_key'], config['base_url'], config['model_name'], config['input_path'], config['output_excel']]):
            messagebox.showwarning("配置不完整", "请检查所有API配置和文件输入输出路径！")
            return
        self.msg_queue.put(('log', "\n========================================"))
        self.update_ui_states(processing=True)
        threading.Thread(target=run_main_task, args=(config, self.msg_queue), daemon=True).start()
    
    def start_review_from_excel_thread(self):
        """启动“生成综述”后台任务。"""
        config = self.get_config()
        topic = self.review_topic_var.get().strip()
        excel_path = self.review_input_excel_var.get()
        html_path = self.review_output_html_var.get()
        review_outline = self.review_outline_text.get("1.0", tk.END).strip()
        if not all([config['api_key'], config['base_url'], config['model_name'], topic, excel_path, html_path, review_outline]):
            messagebox.showwarning("综述信息不完整", "请确保综述主题、所有文件路径和综述大纲均不为空！")
            return
        self.msg_queue.put(('log', "\n========================================"))
        self.update_ui_states(processing=True)
        threading.Thread(target=run_review_from_excel_task, args=(config, excel_path, topic, html_path, review_outline, self.msg_queue), daemon=True).start()
    def start_generate_interactive_html_thread(self):
        """启动“生成交互式HTML报告”后台任务。"""
        excel_path = self.output_excel_var.get()
        if not excel_path:
            messagebox.showwarning("路径缺失", "请先在“输出文件”框中指定一个有效的Excel文件路径！")
            return
    
        # 为了更好的用户体验，我们检查文件是否存在
        if not os.path.exists(excel_path):
            messagebox.showwarning("文件未找到", f"指定的Excel文件不存在：\n{excel_path}\n\n请先运行“开始文献处理”来生成该文件。")
            return
    
        self.update_ui_states(processing=True)
        threading.Thread(target=run_generate_interactive_html_task, args=(excel_path, self.msg_queue), daemon=True).start()

    def fetch_models_thread(self):
        """启动后台线程获取模型列表。"""
        self.msg_queue.put(('log', "\n========================================"))
        self.msg_queue.put(('log', "正在获取模型列表..."))
        config = self.get_config()
        threading.Thread(target=lambda: self._fetch_models_task(config, self.msg_queue), daemon=True).start()

    def _fetch_models_task(self, config, msg_queue):
        """获取模型列表的实际后台工作。"""
        try:
            client = get_openai_client(config)
            models = sorted([model.id for model in client.models.list()])
            msg_queue.put(('models', models))
        except Exception as e:
            msg_queue.put(('log', f"❌ 获取模型列表失败: {e}"))
    
    def on_closing(self):
        """在关闭窗口时安全地保存配置并退出。"""
        self.save_config()
        if self._queue_job: self.after_cancel(self._queue_job)
        self.destroy()
    
    def select_pdf_folder(self):
        """打开文件夹选择对话框以选择PDF输入目录。"""
        path = filedialog.askdirectory(title="请选择包含PDF文献的文件夹")
        if path:
            self.input_path_var.set(path)
            self.output_excel_var.set(os.path.join(path, f'summary_output_{pd.Timestamp.now().strftime("%Y%m%d%H%M")}.xlsx'))
            
    def select_txt_file(self):
        """打开文件选择对话框以选择TXT输入文件。"""
        path = filedialog.askopenfilename(title="请选择包含多篇文献的TXT文件", filetypes=[("Text files", "*.txt")])
        if path:
            self.input_path_var.set(path)
            self.output_excel_var.set(os.path.join(os.path.dirname(path), f'summary_output_{pd.Timestamp.now().strftime("%Y%m%d%H%M")}.xlsx'))

    def browse_output_excel(self):
        """打开文件保存对话框以指定Excel输出路径。"""
        path = filedialog.asksaveasfilename(title="选择或输入输出Excel文件名", filetypes=[("Excel 文件", "*.xlsx")], defaultextension=".xlsx")
        if path: self.output_excel_var.set(path)
        
    def select_review_input_excel(self):
        """打开文件选择对话框以选择综述的Excel数据源。"""
        path = filedialog.askopenfilename(title="请选择包含文献的Excel文件", filetypes=[("Excel files", "*.xlsx")])
        if path:
            self.review_input_excel_var.set(path)
            base_name = os.path.splitext(os.path.basename(path))[0]
            self.review_output_html_var.set(os.path.join(os.path.dirname(path), f'review_{base_name}_{pd.Timestamp.now().strftime("%Y%m%d%H%M")}.html'))

    def browse_review_output_html(self):
        """打开文件保存对话框以指定HTML综述的输出路径。"""
        path = filedialog.asksaveasfilename(title="选择或输入HTML输出文件名", filetypes=[("HTML 文件", "*.html")], defaultextension=".html")
        if path: self.review_output_html_var.set(path)

    def update_ui_states(self, processing: bool):
        """根据任务状态，禁用或启用所有可交互的UI控件。"""
        state = "disabled" if processing else "normal"
        for widget in self.control_widgets:
            try:
                if isinstance(widget, ttk.Entry) and widget.cget('state') == 'readonly': continue
                widget.config(state=state)
            except tk.TclError: pass

    def load_config(self):
        """从config.json加载配置到UI界面。"""
        if not os.path.exists(CONFIG_FILE): return
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f: config = json.load(f)
            self.api_key_var.set(config.get("api_key", ""))
            self.base_url_var.set(config.get("base_url", ""))
            self.model_name_var.set(config.get("model_name", ""))
            self.max_tokens_var.set(config.get("max_tokens", 8000))
            self.use_proxy_var.set(config.get("use_proxy", False))
            self.proxy_address_var.set(config.get("proxy_address", "[http://127.0.0.1:7890](http://127.0.0.1:7890)"))
            self.timeout_var.set(config.get("timeout", 300))
            models_from_config = config.get("model_list", [])
            if models_from_config:
                self.model_combo.config(values=models_from_config)
                if self.model_name_var.get() not in models_from_config and models_from_config:
                    self.model_name_var.set(models_from_config[0])
        except (json.JSONDecodeError, KeyError):
             messagebox.showerror("配置错误", "配置文件 config.json 格式损坏或不完整，已加载默认设置。")
    
    def save_config(self):
        """将当前UI界面的所有配置保存到config.json。"""
        config_data = {
            "api_key": self.api_key_var.get(), "base_url": self.base_url_var.get(),
            "model_name": self.model_name_var.get(), "max_tokens": self.max_tokens_var.get(),
            "model_list": list(self.model_combo.cget('values')),
            "use_proxy": self.use_proxy_var.get(),
            "proxy_address": self.proxy_address_var.get(),
            "timeout": self.timeout_var.get()
        }
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=4, ensure_ascii=False)

    def get_config(self) -> Dict:
        """从UI控件收集所有当前配置，并返回一个字典。"""
        return {
            'api_key': self.api_key_var.get(), 'base_url': self.base_url_var.get(),
            'model_name': self.model_name_var.get(), 'max_tokens': self.max_tokens_var.get(),
            'input_path': self.input_path_var.get(), 'output_excel': self.output_excel_var.get(),
            'do_translate': self.translate_var.get(),
            'use_proxy': self.use_proxy_var.get(),
            'proxy_address': self.proxy_address_var.get(),
            'timeout': self.timeout_var.get()
        }

# ==============================================================================
# 5. 程序入口
# ==============================================================================
if __name__ == "__main__":
    app = App()
    app.mainloop()
