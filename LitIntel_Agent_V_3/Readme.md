# LitIntel Agent V3.0

一款基于Python和Tkinter的批量阅读pdf文献（或PubMed摘要txt）并进行AI处理的可视化软件，在2.0版本上新增生成交互式报告（文献编辑器.html），其余功能保持不变

[详情请查看LitIntel_Agent_V_2](..//LitIntel_Agent_V_2/Readme.md)

## 使用说明

直接复制LitIntel_Agent_V_3.py中的代码到本地后直接运行，运行前需要安装所需要的Python模块。

运行前可以自行修改“2. 提示词与指令模板”中的指示词。

### 基础配置

- api秘钥：填写模型的api key
- 服务地址：填写模型服务的url链接地址，只支持**OpenAI兼容的格式**！
- 模型名称：填写具体的模型名称

<img width="552" height="217" alt="image" src="https://github.com/user-attachments/assets/e524fb54-cc7a-44ed-bcd6-3c55285a4721" />

### 文献批量处理

- pdf文件夹：选择pdf文献所在的文件夹，自动读取文件夹下所有pdf文献并进行分析
- txt文件：读取PubMed导出的txt摘要文件
- 输出文件：默认输出到同文件夹，详情可参考[LitIntel_Agent_V_2](LitIntel_Agent_V_2/Readme.md)
- 生成交互式报告：根据“输出文件夹”的excel文件生成综述html报告
<img width="552" height="165" alt="image" src="https://github.com/user-attachments/assets/c9842dcd-8ae0-4106-91d4-29bb016a2d7c" />

### 文献综述

- 文献源文件：选择第二步文献批量处理生成的excel文件
- 综述输出路径：默认保存到excel同文件夹下
- 综述大纲：可以使用ai根据综述主题生成综述大纲，或自行设置
<img width="552" height="198" alt="image" src="https://github.com/user-attachments/assets/3d63e15e-e4fa-49e5-b468-deed240d28d5" />
<img width="653" height="263" alt="image" src="https://github.com/user-attachments/assets/4a51820e-63fd-4cd3-b34f-3effdbf9b1d1" />


## 注意

- 没有自动搜索文献的功能
- 综述的质量一言难尽，和大纲的质量相关，且仅供参考。
