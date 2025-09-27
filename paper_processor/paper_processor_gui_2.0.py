# -*- coding: utf-8 -*-
"""
Created on Sat Aug 30 14:00:00 2025
一个批量处理pdf或者pubmed文献摘要信息（.txt）文件的gui程序
"""
# 导入所有需要的库
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import pandas as pd
import openai
import os
import re
import json
from typing import Dict, Optional, List
import pypdf
import threading
import queue

# ==============================================================================
# 1. 全局配置 (无函数)
# ==============================================================================
CONFIG_FILE = os.path.join(os.getcwd(),"config.json")
stop_event = threading.Event()
ai_client = None

# --- 【核心升级】将AI指令分离，以支持动态选择 ---
INSTRUCTIONS = {
    "metadata": """- `journal_name`: 论文发表的期刊或会议名称。 
                    - `title`: 论文的原始标题。 
                    - `authors`: 论文的所有作者，用英文逗号加空格 ", " 分隔。 
                    - `publication_year`: 论文的发表年份 (4位数字)。 
                    - `abstract`: 论文的原始英文摘要。 
                    - `doi`: 文章的DOI链接号。""",
    "translate": """- `title_translated`: 将原始标题翻译成中文。 
                    - `abstract_translated`: 将原始摘要翻译成通俗易懂、简明扼要的中文。"""
}
# 为PDF定义的详细总结指令
SUMMARIZE_INSTRUCTION_PDF = """- `article_summary`: 用一句话（中文）总结文章的核心发现。 
                    - `conclusion_opinion`: 用逻辑清晰、条理清楚的中文，分点或分段阐述本文的详细结论和主要结果。"""
# 为TXT定义的简单总结指令
SUMMARIZE_INSTRUCTION_TXT = """- `article_summary`: 用一句话（中文）总结文章的核心发现。 
                    - `conclusion_opinion`: 简要总结其中观点。"""

COLUMN_SETS = {
    "base": ["file_path"],
    "metadata": ["journal_name", "title", "authors", "publication_year", "abstract", "doi"],
    "translate": ["title_translated", "abstract_translated"],
    "summarize": ["article_summary", "conclusion_opinion"]
}
PLACEHOLDER = "AI处理失败或信息未找到"

# ==============================================================================
# 2. 核心任务函数 (已整合动态指令逻辑)
# ==============================================================================

def split_text_into_articles(text: str) -> List[str]:
    articles = re.split(r'\n(?=\d+\.\s[A-Z])', text.strip())
    return [article.strip() for article in articles if article.strip()]

def run_main_task(config, msg_queue, stop_flag):
    global ai_client
    try:
        ai_client = openai.OpenAI(api_key=config['api_key'], 
                                  base_url=config['base_url'])
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
        if not items_to_process:
            msg_queue.put(('log', "❌ 在指定文件夹中未找到任何PDF文件。"))
            msg_queue.put(('task_done', None)); return
    elif os.path.isfile(input_path) and input_path.lower().endswith('.txt'):
        processing_mode = 'txt'
        try:
            with open(input_path, 'r', encoding='utf-8') as f: content = f.read()
            items_to_process = split_text_into_articles(content)
            if not items_to_process:
                msg_queue.put(('log', "❌ TXT文件为空或未能解析出任何文章。"))
                msg_queue.put(('task_done', None)); return
        except Exception as e:
            msg_queue.put(('log', f"❌ 读取或解析TXT文件失败: {e}"))
            msg_queue.put(('task_done', None)); return
    else:
        msg_queue.put(('log', f"❌ 无效的输入路径: 请选择一个PDF文件夹或一个TXT文件。"))
        msg_queue.put(('task_done', None)); return

    msg_queue.put(('log', f"➡️ 模式: '{processing_mode.upper()}'。本次任务共需处理 {len(items_to_process)} 个项目。"))

    # --- 【核心升级】根据模式动态准备AI指令 ---
    final_columns, final_instructions_list, ai_requested_columns = COLUMN_SETS['base'].copy(), [], []
    
    # 添加基础和翻译指令
    final_instructions_list.append(INSTRUCTIONS['metadata']); final_columns.extend(COLUMN_SETS['metadata']); ai_requested_columns.extend(COLUMN_SETS['metadata'])
    if config['do_translate']: final_instructions_list.append(INSTRUCTIONS['translate']); final_columns.extend(COLUMN_SETS['translate']); ai_requested_columns.extend(COLUMN_SETS['translate'])
    
    # 根据模式选择并添加总结指令
    if processing_mode == 'pdf':
        msg_queue.put(('log', "   - 启用PDF模式: 提取详细结论。"))
        final_instructions_list.append(SUMMARIZE_INSTRUCTION_PDF)
    else: # 'txt' mode
        msg_queue.put(('log', "   - 启用TXT模式: 结论固定为'Na'。"))
        final_instructions_list.append(SUMMARIZE_INSTRUCTION_TXT)
        
    final_columns.extend(COLUMN_SETS['summarize']); ai_requested_columns.extend(COLUMN_SETS['summarize'])
    final_instruction_text = "\n\n".join(final_instructions_list)

    all_results = []
    # 循环处理项目
    for i, item in enumerate(items_to_process):
        if stop_flag.is_set(): break
        
        text, current_file_path, log_header = None, "", ""

        if processing_mode == 'pdf':
            current_file_path = item
            log_header = f"--- 正在处理PDF: {os.path.basename(current_file_path)} ({i+1}/{len(items_to_process)}) ---"
            try:
                with open(current_file_path, 'rb') as pdf_file:
                    reader = pypdf.PdfReader(pdf_file)
                    text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
            except Exception as e:
                msg_queue.put(('log', f"   ❌ 错误: 读取PDF文件失败: {e}"))
        elif processing_mode == 'txt':
            text = item
            current_file_path = input_path 
            log_header = f"--- 正在处理文章 {i+1}/{len(items_to_process)} (源文件: {os.path.basename(input_path)}) ---"

        msg_queue.put(('log', f"\n{log_header}"))

        # 调用AI
        ai_result = None
        if text:
            system_prompt = f"""你是一名顶级的、严谨的科研助理。你的任务是快速高效地分析用户提供的学术论文文本，并严格按照指令提取信息。
**你的行为必须遵循以下铁律:**
1.  **核心使命**: 准确理解并执行用户提出的具体任务。
2.  **输出格式**: 你的最终输出 **必须** 是一个单独的、不包含任何其他文字的、格式完全正确的JSON对象。
3.  **JSON结构**: 这个JSON对象必须包含，且仅包含以下这些键(keys): {json.dumps(ai_requested_columns, ensure_ascii=False)}。
4.  **禁止额外内容**: 绝对不要在JSON对象之外添加任何解释、注释、或Markdown标记。你的回答直接以 `{{` 开始，以 `}}` 结束。
5.  **严谨性**: 对于期刊名称、年份和DOI，如果文本中明确找不到，请准确地填入“信息未找到”，不要猜测或编造。"""
            user_prompt = f"""**任务指令:**\n请从我提供的论文文本中，提取以下信息：
                            {final_instruction_text}，并返回JSON对象:\n--- TEXT START ---\n{text[:20000]}\n--- TEXT END ---"""
            try:
                msg_queue.put(('log', "   - 正在发送至AI进行分析..."))
                response = ai_client.chat.completions.create(model=config['model_name'], 
                                                             messages=[{"role": "system", "content": system_prompt}, 
                                                                       {"role": "user", "content": user_prompt}], 
                                                             max_tokens=config['max_tokens'], 
                                                             temperature=0.1, 
                                                             response_format={"type": "json_object"})
                content = response.choices[0].message.content.strip()
                if content.startswith("```"): content = content.strip("```json\n").strip("```")
                ai_result = json.loads(content)
                msg_queue.put(('log', "   ✅ AI成功返回结构化数据。"))
                msg_queue.put(('ai_result', json.dumps(ai_result, indent=2, ensure_ascii=False)))
            except Exception as e:
                msg_queue.put(('log', f"   ❌ 调用AI时发生错误: {e}"))
        else:
            msg_queue.put(('log', "   - 文本内容为空，跳过AI分析。"))

        entry = {'file_path': current_file_path}
        for col in ai_requested_columns:
            entry[col] = ai_result.get(col, PLACEHOLDER) if ai_result else "文本提取失败"
        all_results.append(entry)

    # 保存结果
    if all_results:
        df_final = pd.DataFrame(all_results)
        try:
            df_final.reindex(columns=final_columns).to_excel(config['output_excel'], index=False)
            msg_queue.put(('log', f"\n💾 处理完成，结果已保存到: {os.path.basename(config['output_excel'])}"))
        except Exception as e:
            msg_queue.put(('log', f"❌ 保存Excel时发生严重错误: {e}."))
    
    if stop_flag.is_set(): msg_queue.put(('log', "\n--- 任务已停止 ---"))
    else: msg_queue.put(('log', "\n\n🎉🎉🎉 全部任务完成！"))
    
    msg_queue.put(('task_done', None))

# ==============================================================================
# 3. GUI界面代码 (Tkinter) - 无需修改
# ==============================================================================
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("文献智能处理工具 v12.4 (动态指令版)")
        self.geometry("900x650")

        self.msg_queue = queue.Queue()
        self.control_widgets = []
        self._create_widgets()
        self.load_config()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.after(100, self.process_queue)

    def _create_widgets(self):
        paned_window = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned_window.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.controls_frame = ttk.Frame(paned_window)
        paned_window.add(self.controls_frame, weight=2)
        
        ai_frame = ttk.LabelFrame(self.controls_frame, text="基础配置", padding="10")
        ai_frame.pack(fill=tk.X, pady=5, padx=5)
        io_frame = ttk.LabelFrame(self.controls_frame, text="文件路径", padding="10")
        io_frame.pack(fill=tk.X, pady=5, padx=5)
        task_frame = ttk.LabelFrame(self.controls_frame, text="任务选项", padding="10")
        task_frame.pack(fill=tk.X, pady=5, padx=5)
        action_frame = ttk.LabelFrame(self.controls_frame, text="运行控制", padding="10")
        action_frame.pack(fill=tk.X, pady=5, padx=5)

        ttk.Label(ai_frame, text="API密钥:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=3)
        self.api_key_var = tk.StringVar(); api_entry = ttk.Entry(ai_frame, textvariable=self.api_key_var, width=40)
        api_entry.grid(row=0, column=1, sticky=tk.EW, padx=5)
        ttk.Label(ai_frame, text="服务地址:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=3)
        self.base_url_var = tk.StringVar(); url_entry = ttk.Entry(ai_frame, textvariable=self.base_url_var, width=40)
        url_entry.grid(row=1, column=1, sticky=tk.EW, padx=5)
        ttk.Label(ai_frame, text="模型名称:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=3)
        self.model_name_var = tk.StringVar(); self.model_combo = ttk.Combobox(ai_frame, textvariable=self.model_name_var, width=38)
        self.model_combo.grid(row=2, column=1, sticky=tk.EW, padx=5)
        refresh_btn = ttk.Button(ai_frame, text="刷新", command=self.fetch_models_thread)
        refresh_btn.grid(row=2, column=2, padx=5)
        ttk.Label(ai_frame, text="Max Tokens:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=3)
        self.max_tokens_var = tk.IntVar(value=8000); tokens_entry = ttk.Entry(ai_frame, textvariable=self.max_tokens_var, width=10)
        tokens_entry.grid(row=3, column=1, sticky=tk.W, padx=5)
        ai_frame.columnconfigure(1, weight=1)

        ttk.Label(io_frame, text="输入路径:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=3)
        self.input_path_var = tk.StringVar(); in_entry = ttk.Entry(io_frame, textvariable=self.input_path_var, state='readonly')
        in_entry.grid(row=0, column=1, sticky=tk.EW, columnspan=2)
        browse_buttons_frame = ttk.Frame(io_frame)
        browse_buttons_frame.grid(row=0, column=3, padx=5)
        pdf_btn = ttk.Button(browse_buttons_frame, text="PDF文件夹...", command=self.select_pdf_folder)
        pdf_btn.pack(side=tk.LEFT, padx=(0, 2))
        txt_btn = ttk.Button(browse_buttons_frame, text="TXT文件...", command=self.select_txt_file)
        txt_btn.pack(side=tk.LEFT)
        ttk.Label(io_frame, text="输出文件:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=3)
        self.output_excel_var = tk.StringVar(); out_entry = ttk.Entry(io_frame, textvariable=self.output_excel_var)
        out_entry.grid(row=1, column=1, sticky=tk.EW, columnspan=2)
        saveas_btn = ttk.Button(io_frame, text="另存为...", command=self.browse_output_excel)
        saveas_btn.grid(row=1, column=3, padx=5)
        io_frame.columnconfigure(1, weight=1)
        
        self.translate_var = tk.BooleanVar(value=True)
        trans_check = ttk.Checkbutton(task_frame, text="翻译标题和摘要", variable=self.translate_var)
        trans_check.pack(anchor=tk.W, padx=5)
        
        button_container = ttk.Frame(action_frame)
        button_container.pack()
        self.start_button = ttk.Button(button_container, text="开始处理", command=self.start_processing_thread, width=15)
        self.start_button.pack(side=tk.LEFT, padx=10, pady=5)
        self.stop_button = ttk.Button(button_container, text="停止", command=self.stop_processing, state="disabled", width=15)
        self.stop_button.pack(side=tk.LEFT, padx=10, pady=5)

        self.control_widgets.extend([api_entry, url_entry, self.model_combo, refresh_btn, tokens_entry, in_entry, pdf_btn, txt_btn, out_entry, saveas_btn, trans_check])

        output_pane = ttk.PanedWindow(paned_window, orient=tk.VERTICAL)
        paned_window.add(output_pane, weight=3)
        ai_result_frame = ttk.LabelFrame(output_pane, text="AI实时返回 (JSON)")
        output_pane.add(ai_result_frame, weight=2)
        self.ai_result_text = scrolledtext.ScrolledText(ai_result_frame, wrap=tk.WORD); self.ai_result_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5); self.ai_result_text.config(state='disabled')
        log_frame = ttk.LabelFrame(output_pane, text="运行日志")
        output_pane.add(log_frame, weight=3)
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD); self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5); self.log_text.config(state='disabled')
            
    def select_pdf_folder(self):
        path = filedialog.askdirectory(title="请选择包含PDF文献的文件夹")
        if path:
            self.input_path_var.set(path)
            self.output_excel_var.set(os.path.join(path, f'summary_output_{pd.Timestamp.now():%Y%m%d}.xlsx'))

    def select_txt_file(self):
        path = filedialog.askopenfilename(title="请选择包含多篇文献的TXT文件", filetypes=[("Text files", "*.txt")])
        if path:
            self.input_path_var.set(path)
            output_dir = os.path.dirname(path)
            self.output_excel_var.set(os.path.join(output_dir, f'summary_output_{pd.Timestamp.now():%Y%m%d}.xlsx'))

    def browse_output_excel(self):
        path = filedialog.asksaveasfilename(title="选择或输入输出Excel文件名", filetypes=[("Excel 文件", "*.xlsx")], defaultextension=".xlsx")
        if path: self.output_excel_var.set(path)

    def fetch_models_thread(self):
        def fetch():
            try:
                client = openai.OpenAI(api_key=self.api_key_var.get(), base_url=self.base_url_var.get())
                models = sorted([model.id for model in client.models.list()])
                self.msg_queue.put(('models', models))
            except Exception as e:
                self.msg_queue.put(('log', f"❌ 获取模型列表失败: {e}"))
        self.msg_queue.put(('log', "正在获取模型列表..."))
        threading.Thread(target=fetch, daemon=True).start()

    def start_processing_thread(self):
        config = {
            'api_key': self.api_key_var.get(), 'base_url': self.base_url_var.get(), 
            'model_name': self.model_name_var.get(), 'max_tokens': self.max_tokens_var.get(),
            'input_path': self.input_path_var.get(), 'output_excel': self.output_excel_var.get(),
            'do_translate': self.translate_var.get()
        }
        if not all([config['api_key'], config['base_url'], config['model_name'], config['input_path'], config['output_excel']]):
            messagebox.showwarning("配置不完整", "请检查API、模型和文件路径等所有配置项！")
            return
        
        self.log_text.config(state='normal'); self.log_text.delete(1.0, tk.END); self.log_text.config(state='disabled')
        self.ai_result_text.config(state='normal'); self.ai_result_text.delete(1.0, tk.END); self.ai_result_text.config(state='disabled')
        
        stop_event.clear()
        self.update_ui_states(processing=True)
        threading.Thread(target=run_main_task, args=(config, self.msg_queue, stop_event), daemon=True).start()
    
    def stop_processing(self):
        self.msg_queue.put(('log', "正在请求停止任务..."))
        stop_event.set()
        self.stop_button.config(state="disabled")

    def update_ui_states(self, processing: bool):
        state = "disabled" if processing else "normal"
        self.start_button.config(state=state)
        self.stop_button.config(state="normal" if processing else "disabled")
        for widget in self.control_widgets:
            widget.config(state=state)

    def process_queue(self):
        try:
            while True:
                msg_type, content = self.msg_queue.get_nowait()
                if msg_type == 'log':
                    self.log_text.config(state='normal'); self.log_text.insert(tk.END, content + '\n'); self.log_text.see(tk.END); self.log_text.config(state='disabled')
                elif msg_type == 'ai_result':
                    self.ai_result_text.config(state='normal'); self.ai_result_text.insert(tk.END, content + '\n\n' + '-'*50 + '\n\n'); self.ai_result_text.see(tk.END); self.ai_result_text.config(state='disabled')
                elif msg_type == 'models':
                    current_selection = self.model_name_var.get()
                    self.model_combo.config(values=content)
                    if current_selection and current_selection in content: self.model_name_var.set(current_selection)
                    elif content: self.model_name_var.set(content)
                    else: self.model_name_var.set('')
                    self.msg_queue.put(('log', "✅ 模型列表已刷新。"))
                elif msg_type == 'task_done':
                    self.update_ui_states(processing=False)
        except queue.Empty: pass
        finally:
            if self.winfo_exists(): self.after(100, self.process_queue)

    def load_config(self):
        if not os.path.exists(CONFIG_FILE): return
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
            self.api_key_var.set(config.get("api_key", ""))
            self.base_url_var.set(config.get("base_url", ""))
            self.model_name_var.set(config.get("model_name", ""))
            self.max_tokens_var.set(config.get("max_tokens", 8000))

    def save_config(self):
        config_data = {
            "api_key": self.api_key_var.get(), 
            "base_url": self.base_url_var.get(), 
            "model_name": self.model_name_var.get(),
            "max_tokens": self.max_tokens_var.get()
        }
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=4)

    def on_closing(self): self.save_config(); self.destroy()

if __name__ == "__main__":
    app = App()
    app.mainloop()
