# -*- coding: utf-8 -*-
"""
Created on Fri Aug 23 10:00:00 2025
@author: Python Professional for User Task (Finalized by Gemini)
"""
# 导入所有需要的库
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import pandas as pd
import openai
import os
import json
from typing import Dict, Optional, List
import pypdf
import threading
import queue

# ==============================================================================
# 1. 全局配置 (无函数)
# ==============================================================================
CONFIG_FILE = "config.json"
stop_event = threading.Event()
ai_client = None

# --- AI 指令和列定义 (保持原样) ---
INSTRUCTIONS = {
    "metadata": """- `journal_name`: 论文发表的期刊或会议名称。 
                    - `title`: 论文的原始标题。 
                    - `authors`: 论文的所有作者，用英文逗号加空格 ", " 分隔。 
                    - `publication_year`: 论文的发表年份 (4位数字)。 
                    - `abstract`: 论文的原始英文摘要。 
                    - `doi`: 文章的DOI链接号。""",
    "translate": """- `title_translated`: 将原始标题翻译成中文。 
                    - `abstract_translated`: 将原始摘要翻译成通俗易懂、简明扼要的中文。""",
    "summarize": """- `article_summary`: 用一句话（中文）总结文章的核心发现。 
                    - `conclusion_opinion`: 用逻辑清晰、条理清楚的中文，分点或分段阐述本文的详细结论和主要结果。"""
}
COLUMN_SETS = {
    "base": ["file_path"],
    "metadata": ["journal_name", "title", "authors", "publication_year", "abstract", "doi"],
    "translate": ["title_translated", "abstract_translated"],
    "summarize": ["article_summary", "conclusion_opinion"]
}
PLACEHOLDER = "AI处理失败或信息未找到"

# ==============================================================================
# 2. 核心任务函数 (大幅简化)
# ==============================================================================
def run_main_task(config, msg_queue, stop_flag):
    """
    在独立线程中运行的核心任务，通过队列与主UI通信。
    将所有逻辑内联，减少函数调用。
    """
    global ai_client
    # 1. 初始化AI客户端
    try:
        ai_client = openai.OpenAI(api_key=config['api_key'], base_url=config['base_url'])
        ai_client.models.list() # 验证连接
    except Exception as e:
        msg_queue.put(('log', f"❌ 初始化或连接AI失败: {e}"))
        msg_queue.put(('task_done', None)) # 确保任务结束，按钮恢复
        return

    msg_queue.put(('log', "--- 开始执行批量处理任务 ---"))
    
    # 2. 获取文件列表
    input_path_str = config['input_path']
    files_to_process = [os.path.join(input_path_str, f) for f in os.listdir(input_path_str) if f.lower().endswith('.pdf')]
    if not files_to_process:
        msg_queue.put(('log', "❌ 在指定文件夹中未找到任何PDF文件。"))
        msg_queue.put(('task_done', None))
        return
    
    msg_queue.put(('log', f"➡️ 本次任务共需处理 {len(files_to_process)} 个PDF文件。"))

    # 3. 准备AI指令
    final_columns, final_instructions_list, ai_requested_columns = COLUMN_SETS['base'].copy(), [], []
    final_instructions_list.append(INSTRUCTIONS['metadata']); final_columns.extend(COLUMN_SETS['metadata']); ai_requested_columns.extend(COLUMN_SETS['metadata'])
    if config['do_translate']: final_columns.extend(COLUMN_SETS['translate']); ai_requested_columns.extend(COLUMN_SETS['translate']); final_instructions_list.append(INSTRUCTIONS['translate'])
    if config['do_summarize']: final_columns.extend(COLUMN_SETS['summarize']); ai_requested_columns.extend(COLUMN_SETS['summarize']); final_instructions_list.append(INSTRUCTIONS['summarize'])
    final_instruction_text = "\n\n".join(final_instructions_list)

    all_results = []
    # 4. 循环处理文件
    for i, file_path in enumerate(files_to_process):
        if stop_flag.is_set(): break
        
        msg_queue.put(('log', f"\n--- 正在处理: {os.path.basename(file_path)} ({i+1}/{len(files_to_process)}) ---"))
        
        # 提取PDF文本
        text = None
        try:
            with open(file_path, 'rb') as pdf_file:
                reader = pypdf.PdfReader(pdf_file)
                text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
        except Exception as e:
            msg_queue.put(('log', f"   ❌ 错误: 读取PDF文件失败: {e}"))

        # 调用AI
        ai_result = None
        if text:
            system_prompt = f"""你你是一名顶级的、严谨的科研助理。你的任务是快速高效地分析用户提供的学术论文文本，并严格按照指令提取信息
                        **你的行为必须遵循以下铁律:**
                        1.  **核心使命**: 准确理解并执行用户提出的具体任务。
                        2.  **输出格式**: 你的最终输出 **必须** 是一个单独的、不包含任何其他文字的、格式完全正确的JSON对象。
                        3.  **JSON结构**: 这个JSON对象必须包含，且仅包含以下这些键(keys): {json.dumps(ai_requested_columns, ensure_ascii=False)}。
                        4.  **禁止额外内容**: 绝对不要在JSON对象之外添加任何解释、注释、或Markdown标记。你的回答直接以 `{{` 开始，以 `}}` 结束。
                        5.  **严谨性**: 对于期刊名称、年份和DOI，如果文本中明确找不到，请准确地填入“信息未找到”，不要猜测或编造。
                        另外，你必须注意效率，快速、高效完成任务。"""
            user_prompt = f"""**任务指令:**\n请从我提供的论文文本中，提取以下信息：
                            {final_instruction_text}，并返回JSON对象:\n--- TEXT START ---\n{text[:200000]}\n--- TEXT END ---"""
            try:
                msg_queue.put(('log', "   - 正在发送至AI进行分析..."))
                response = ai_client.chat.completions.create(model=config['model_name'], messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}], max_tokens=4096, temperature=0.1, response_format={"type": "json_object"})
                content = response.choices[0].message.content.strip()
                if content.startswith("```"): content = content.strip("```json\n").strip("```")
                ai_result = json.loads(content)
                msg_queue.put(('log', "   ✅ AI成功返回结构化数据。"))
                msg_queue.put(('ai_result', json.dumps(ai_result, indent=2, ensure_ascii=False)))
            except Exception as e:
                msg_queue.put(('log', f"   ❌ 调用AI时发生错误: {e}"))
        else:
            msg_queue.put(('log', "   - PDF文本为空，跳过AI分析。"))

        # 收集结果
        entry = {'file_path': file_path}
        for col in ai_requested_columns:
            entry[col] = ai_result.get(col, PLACEHOLDER) if ai_result else "PDF文本提取失败"
        all_results.append(entry)

    # 5. 保存结果
    if all_results:
        df_final = pd.DataFrame(all_results)
        try:
            df_final.reindex(columns=final_columns).to_excel(config['output_excel'], index=False)
            msg_queue.put(('log', f"\n💾 处理完成，结果已保存到: {os.path.basename(config['output_excel'])}"))
        except Exception as e:
            msg_queue.put(('log', f"❌ 保存Excel时发生严重错误: {e}."))
    
    if stop_flag.is_set(): msg_queue.put(('log', "\n--- 任务已停止 ---"))
    else: msg_queue.put(('log', "\n\n🎉🎉🎉 全部任务完成！"))
    
    # 通知主线程任务结束
    msg_queue.put(('task_done', None))

# ==============================================================================
# 3. GUI界面代码 (Tkinter)
# ==============================================================================
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PDF文献智能处理工具 v12.1")
        self.geometry("900x600")

        self.msg_queue = queue.Queue()
        self.control_widgets = []
        self._create_widgets()
        self.load_config()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.after(100, self.process_queue)

    def _create_widgets(self):
        # 保持原始的 PanedWindow 结构
        paned_window = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned_window.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 左侧控制区
        self.controls_frame = ttk.Frame(paned_window)
        paned_window.add(self.controls_frame, weight=2) # 控制区权重
        
        # --- 严格按照原始结构创建4个LabelFrame ---
        ai_frame = ttk.LabelFrame(self.controls_frame, text="基础配置", padding="10")
        ai_frame.pack(fill=tk.X, pady=5, padx=5)
        io_frame = ttk.LabelFrame(self.controls_frame, text="文件路径", padding="10")
        io_frame.pack(fill=tk.X, pady=5, padx=5)
        task_frame = ttk.LabelFrame(self.controls_frame, text="任务选项", padding="10")
        task_frame.pack(fill=tk.X, pady=5, padx=5)
        action_frame = ttk.LabelFrame(self.controls_frame, text="运行控制", padding="10")
        action_frame.pack(fill=tk.X, pady=5, padx=5)

        # --- 填充控件 ---
        # 1. 基础配置
        ttk.Label(ai_frame, text="API密钥:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=3)
        self.api_key_var = tk.StringVar()
        api_entry = ttk.Entry(ai_frame, textvariable=self.api_key_var, width=40)
        api_entry.grid(row=0, column=1, sticky=tk.EW, padx=5)
        ttk.Label(ai_frame, text="服务地址:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=3)
        self.base_url_var = tk.StringVar()
        url_entry = ttk.Entry(ai_frame, textvariable=self.base_url_var, width=40)
        url_entry.grid(row=1, column=1, sticky=tk.EW, padx=5)
        ttk.Label(ai_frame, text="模型名称:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=3)
        self.model_name_var = tk.StringVar()
        self.model_combo = ttk.Combobox(ai_frame, textvariable=self.model_name_var, width=38, state='readonly')
        self.model_combo.grid(row=2, column=1, sticky=tk.EW, padx=5)
        refresh_btn = ttk.Button(ai_frame, text="刷新列表", command=self.fetch_models_thread)
        refresh_btn.grid(row=2, column=2, padx=5)
        ai_frame.columnconfigure(1, weight=1)

        # 2. 文件路径
        ttk.Label(io_frame, text="输入文件夹:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=3)
        self.input_path_var = tk.StringVar(); in_entry = ttk.Entry(io_frame, textvariable=self.input_path_var, state='readonly')
        in_entry.grid(row=0, column=1, sticky=tk.EW)
        browse_btn = ttk.Button(io_frame, text="浏览...", command=self.browse_folder)
        browse_btn.grid(row=0, column=2, padx=5)
        ttk.Label(io_frame, text="输出文件:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=3)
        self.output_excel_var = tk.StringVar(); out_entry = ttk.Entry(io_frame, textvariable=self.output_excel_var)
        out_entry.grid(row=1, column=1, sticky=tk.EW)
        saveas_btn = ttk.Button(io_frame, text="另存为...", command=self.browse_output_excel)
        saveas_btn.grid(row=1, column=2, padx=5)
        io_frame.columnconfigure(1, weight=1)
        
        # 3. 任务选项
        self.translate_var = tk.BooleanVar(value=True); self.summarize_var = tk.BooleanVar(value=True)
        trans_check = ttk.Checkbutton(task_frame, text="翻译标题和摘要", variable=self.translate_var)
        trans_check.pack(anchor=tk.W, padx=5)
        summ_check = ttk.Checkbutton(task_frame, text="总结要点和结论", variable=self.summarize_var)
        summ_check.pack(anchor=tk.W, padx=5)
        
        # 4. 执行控制 (按钮同行)
        button_container = ttk.Frame(action_frame)
        button_container.pack()
        self.start_button = ttk.Button(button_container, text="开始处理", command=self.start_processing_thread, width=15)
        self.start_button.pack(side=tk.LEFT, padx=10, pady=5)
        self.stop_button = ttk.Button(button_container, text="停止", command=self.stop_processing, state="disabled", width=15)
        self.stop_button.pack(side=tk.LEFT, padx=10, pady=5)

        self.control_widgets.extend([api_entry, url_entry, self.model_combo, refresh_btn, in_entry, browse_btn, out_entry, saveas_btn, trans_check, summ_check])

        # --- 右侧输出区 (使用垂直PanedWindow进行布局调整) ---
        output_pane = ttk.PanedWindow(paned_window, orient=tk.VERTICAL)
        paned_window.add(output_pane, weight=3) # 输出区权重
        
        ai_result_frame = ttk.LabelFrame(output_pane, text="输出")
        output_pane.add(ai_result_frame, weight=1) # AI结果窗口占据主要权重
        self.ai_result_text = scrolledtext.ScrolledText(ai_result_frame, wrap=tk.WORD)
        self.ai_result_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.ai_result_text.config(state='disabled')
        
        log_frame = ttk.LabelFrame(output_pane, text="日志")
        output_pane.add(log_frame, weight=4) # 日志窗口占据较小权重
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.log_text.config(state='disabled')
            
    def browse_folder(self):
        path = filedialog.askdirectory(title="请选择包含PDF文献的文件夹")
        if path:
            self.input_path_var.set(path)
            self.output_excel_var.set(os.path.join(path, f'summary_output_{pd.Timestamp.now():%Y%m%d}.xlsx'))

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
            'api_key': self.api_key_var.get(), 'base_url': self.base_url_var.get(), 'model_name': self.model_name_var.get(),
            'input_path': self.input_path_var.get(), 'output_excel': self.output_excel_var.get(),
            'do_translate': self.translate_var.get(), 'do_summarize': self.summarize_var.get()
        }
        if not all(config.values()): messagebox.showwarning("配置不完整", "请检查所有配置项！"); return
        
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
                    # [核心修复] 正确更新模型列表并保持选择
                    current_selection = self.model_name_var.get()
                    self.model_combo.config(values=content)
                    if current_selection and current_selection in content:
                        self.model_name_var.set(current_selection)
                    elif content:
                        self.model_name_var.set(content)
                    else:
                        self.model_name_var.set('')
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

    def save_config(self):
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump({"api_key": self.api_key_var.get(), "base_url": self.base_url_var.get(), "model_name": self.model_name_var.get()}, f, indent=4)

    def on_closing(self): self.save_config(); self.destroy()

if __name__ == "__main__":
    app = App()

    app.mainloop()
