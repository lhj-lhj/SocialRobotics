# 项目结构说明

## 模块化架构

项目已重新组织为模块化结构，遵循工程化最佳实践：

```
SocialRobotics/
├── main.py                 # 主入口：控制要不要 plan
├── config.json             # 配置文件
├── plan/                   # 计划模块
│   ├── __init__.py
│   ├── controller.py       # 1. 判断信任程度
│   ├── behavior_generator.py  # 2. 组织成机器人API的行为
│   ├── orchestrator.py     # 3. 表现机器人的思考状态
│   └── prompts.py          # Prompt 定义
├── connection/             # 连接模块：用于和机器人连接做调试
│   ├── __init__.py
│   └── furhat_bridge.py    # Furhat 连接桥接器
└── utils/                  # 工具模块
    ├── __init__.py
    ├── config.py           # 配置加载
    ├── streamer.py         # 流式处理
    └── print_utils.py      # 打印工具
```

## 模块职责

### 1. `main.py` - 主入口
- 控制是否使用 plan 模块
- 简单的启动逻辑
- 命令行参数解析

### 2. `plan/` - 计划模块
**controller.py**: 
- 判断信任程度（confidence）
- 决定是否需要思考（need_thinking）
- 生成思考提示和推理提示

**behavior_generator.py**:
- 将动作描述转换为 Furhat API 调用
- 管理信心等级对应的语言前缀和动作
- 执行具体的机器人动作（点头、摇头等）

**orchestrator.py**:
- 组织整个思考和回答流程
- 协调思考模型和回答模型
- 控制可见的状态切换

**prompts.py**:
- 所有 Prompt 定义
- Prompt 构建函数

### 3. `connection/` - 连接模块
**furhat_bridge.py**:
- 管理 Furhat 机器人连接
- 处理事件（听、说等）
- 调用 plan 模块处理用户输入
- 调试和连接管理

### 4. `utils/` - 工具模块
**config.py**: 
- 加载配置（优先 config.json）
- API 密钥管理

**streamer.py**:
- 流式获取句子级片段
- OpenAI API 流式调用

**print_utils.py**:
- 支持中文输出的打印工具

## 使用方式

### 运行主程序
```bash
python main.py --host 192.168.1.114 --auth_key YOUR_KEY
```

### 不使用 plan 模块（仅调试连接）
```bash
python main.py --no-plan --host 192.168.1.114
```

## 工作流程

1. **用户说话** → `connection/furhat_bridge.py` 接收事件
2. **处理输入** → 调用 `plan/orchestrator.py`
3. **判断信任** → `plan/controller.py` 判断是否需要思考和信心等级
4. **生成行为** → `plan/behavior_generator.py` 将描述转换为 API 调用
5. **执行动作** → 通过 Furhat API 执行动作和说话
6. **思考状态** → `plan/orchestrator.py` 控制思考过程的可见表现

## 配置

配置文件 `config.json` 包含：
- `api_key`: OpenAI API 密钥
- `base_url`: API 基础 URL
- `controller_model`: 控制模型
- `reasoning_model`: 回答模型
- `thinking_model`: 思考模型
- 各种模型的 temperature 设置

