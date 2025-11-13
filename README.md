# 可见思考 Furhat 原型

本项目演示了一个 **“控制模型 → 可见思考模型 → 主回答模型”** 的流水线，用于 Furhat 机器人在回答前展示人类式思考过程，同时根据模型信心输出不同的语言/动作组合。所有逻辑都在 `main.py` 中，无需额外依赖。

## 实现思路

1. **控制模型 (ControllerModel)**  
   - 先调用轻量模型，对用户输入生成严格的 JSON。  
   - JSON 中包含：是否需要进入思考状态、预估信心等级、2-4 条简短“思维链”提示、给主回答的 hint，以及当无需思考时可直接返回的答案。  
   - 这样可以把“需不需要思考”与“信心提示”交给小模型决策，避免每次都强制思考导致体验拖沓。

2. **可见思考模型 (Thinking Model)**  
   - 当控制层判定需要思考时，把“用户输入 + 思维链 JSON”拼成 prompt，要求模型仅输出 2-4 句 ≤12 字的中文短句。  
   - 这些短句通过异步流式打印，形成 Furhat 机器人“思考中”的可见行为，后续可替换成真实的语音/表情 API。

3. **主回答模型 (Reasoning Model)**  
   - 另一路 `ChatGPTSentenceStreamer` 负责最终回答，同样以流式句子推送。  
   - 第一句到达时终止思考流，依据控制层建议或字数估算映射到 `CONFIDENCE_BEHAVIORS`，输出对应的语言前缀与动作提示。

4. **输出与编码**  
   - 所有终端打印统一使用 `cprint`，自动处理 UTF‑8，让 Windows/WSL 也能稳定输出中文。  
   - 如果控制层直接给出答案（need_thinking=false），主流程会跳过思考阶段，直接走“回答+动作”。

## 运行方式

1. 确认环境：Python 3.8+，且可 `pip install requests`（Linux/Mac/WSL 自带）。  
2. 将仓库根目录下自动生成的 `config.json` 或 `api_key.txt` 填入真实密钥：  
   - 推荐编辑 `config.json`，在 `api_key` 字段写入 `sk-xxxx`；其余字段可继续沿用默认模型。  
   - 如果更喜欢存放在纯文本中，可把密钥黏贴到 `api_key.txt` 第一行；当两个文件都写了 key 时，以 `config.json` 为准。  
   - 这两个文件已在 `.gitignore` 中列出，不会被提交。  
3. 运行：
   ```bash
   python3 main.py
   ```
   输入任意中文/英文问题，即可看到控制台依次打印“思考中”提示、信心切换提示、正式回答与对应的“动作”。

## 关键配置

| 配置项 | 位置 | 说明 |
| --- | --- | --- |
| `OPENAI_SETTINGS` | `main.py:24` | 运行时会被 `config.json`/`api_key.txt` 中的值覆盖。 |
| `CONTROLLER_SYSTEM_PROMPT` | `main.py:43` | 约束控制模型仅输出合法 JSON，含需要思考与否的决策。 |
| `THINKING_SYSTEM_PROMPT` | `main.py:63` | 规范可见思考模型只能输出 2-4 句短语，语气自然。 |
| `REASONING_SYSTEM_PROMPT` | `main.py:57` | 让主回答保持 2-3 句友好口吻，并隐藏内部推理。 |
| `CONFIDENCE_BEHAVIORS` | `main.py:34` | 自定义各信心等级的语言前缀与动作描述，可直接映射到 Furhat API。 |

## 自定义与扩展

- **接入真实 Furhat**：把 `_relay_thinking`、`_relay_answer`、`_respond_directly` 中的 `cprint` 替换成 Furhat SDK 的语音/表情/灯光控制即可。  
- **接驳不同模型**：目前三路都指向同一 `https://api.openai.com`，未来只需调 `OPENAI_SETTINGS` 中的 `*_model` 即可分流到自建/其他供应商接口。  
- **控制策略**：如需更精细的思考判定，可扩展控制模型 JSON 字段（例如加入场景标签），在 `ControllerModel.decide()` 解析后映射。  
- **信心估计**：现在优先采用控制模型给出的 `confidence`，若缺失则根据回答字数兜底；也可以改成读取真实模型 logprobs 或外部评估器。

## 故障排查

- 运行即报 “配置错误：请在 OPENAI_SETTINGS['api_key'] 中填入合法的 API Key。”  
  → 未填 API Key 或填错；请确认密钥有效。  
- 控制模型返回非 JSON 导致异常  
  → 通常是 prompt 被修改或模型回复超出要求，可暂时把 `CONTROLLER_SYSTEM_PROMPT` 调得更严格，或在 `_parse_json` 中添加额外清洗逻辑。  
- 思考阶段不触发 / 一直触发  
  → 调整控制模型温度、或在 prompt 中加入 heuristics（例如“餐饮/寒暄 → 不思考”）。  
- Windows 控制台出现乱码  
  → 脚本已尽量处理编码问题，如仍异常，可改用 PowerShell/WSL 或在终端手动运行 `chcp 65001`。

## 项目结构

```
Social Robotics/
├── main.py          # 核心逻辑：控制模型 + 思考模型 + 主回答模型
├── realtime-api-examples/  # OpenAI 官方示例（未修改）
└── README.md
```

欢迎按自己的研究需要继续拓展。若在实验环境中需要记录交互数据，可在 `Orchestrator` 中加入日志埋点，把控制层 JSON、思考提示、最终回答写入数据库或文件。祝项目顺利！
