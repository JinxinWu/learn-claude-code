# s_full.py 全流程教学文档

本文目标：让你从零到一读懂 [agents/s_full.py](agents/s_full.py) 的完整运行机制，并能自己调试和扩展。

## 1. 先理解它在做什么

[agents/s_full.py](agents/s_full.py) 是一个“总装版”代理程序，把前面章节的关键机制都合并到一个文件里：

1. 工具调用与分发
2. Todo 管理
3. 子代理委派
4. 技能加载
5. 上下文压缩
6. 文件任务系统
7. 后台任务
8. 多智能体消息总线
9. 关机与计划审批协议
10. REPL 交互入口

你可以把它理解为一个“可扩展的编程代理内核”。

## 2. 启动阶段：程序一启动做了什么

入口在文件底部的 main 循环，核心初始化在全局区域完成。

### 2.1 环境与模型客户端

在 [agents/s_full.py](agents/s_full.py#L47) 到 [agents/s_full.py](agents/s_full.py#L58)：

1. 读取环境变量
2. 创建 OpenAI 兼容客户端
3. 读取模型名 MODEL_ID

这一步决定了后续所有 LLM 调用都走同一个 client。

### 2.2 运行目录与状态目录

在 [agents/s_full.py](agents/s_full.py#L60) 到 [agents/s_full.py](agents/s_full.py#L71) 定义了几个关键目录：

1. .team：队友配置和收件箱
2. .tasks：任务文件
3. skills：技能目录
4. .transcripts：压缩前的对话快照

这些目录就是代理的“外部记忆与协作存储层”。

## 3. 基础能力层：所有上层功能的地基

### 3.1 make_tool：统一工具 schema 生成器

定义在 [agents/s_full.py](agents/s_full.py#L75)。

作用：把工具统一生成成 OpenAI function tools 结构，避免每个工具重复写样板。

收益：

1. 一处改动全局生效
2. schema 风格统一
3. 更不容易漏字段

### 3.2 安全文件与命令工具

在 [agents/s_full.py](agents/s_full.py#L87) 开始：

1. safe_path：防止路径逃逸工作区
2. run_bash：执行命令并做危险命令拦截
3. run_read/run_write/run_edit：文件读写改

这是后续 ToolHandlers 的基础执行层。

## 4. 业务子系统：把“能力”组织成“机制”

### 4.1 TodoManager

位置：[agents/s_full.py](agents/s_full.py#L129)

关键点：

1. update 会严格校验 status 和 activeForm
2. 最多 20 条
3. 同时只允许 1 条 in_progress
4. has_open_items 用于主循环提醒

### 4.2 run_subagent：子代理循环

位置：[agents/s_full.py](agents/s_full.py#L170)

流程：

1. 根据 agent_type 组装工具集
2. 发起 chat.completions 请求
3. 读取 message.tool_calls
4. 解析 arguments JSON
5. 调本地 handler
6. 以 role=tool 回注
7. 无 tool_calls 时返回最终总结

这部分是“主代理把局部问题外包给子代理”的核心。

### 4.3 SkillLoader

位置：[agents/s_full.py](agents/s_full.py#L288)

它会扫描 skills 下的 SKILL.md，解析 frontmatter，支持：

1. descriptions：生成技能列表摘要
2. load(name)：按名字加载技能正文

### 4.4 压缩系统

位置：[agents/s_full.py](agents/s_full.py#L318)

1. estimate_tokens：粗略估算上下文长度
2. microcompact：清理旧 tool 消息，保留最近 3 条
3. auto_compact：先落盘 transcript，再请求模型做连续性摘要

这让长会话不会无限膨胀。

### 4.5 TaskManager

位置：[agents/s_full.py](agents/s_full.py#L354)

它是持久化任务板，支持 create/get/update/list/claim。

重点：

1. 任务存成 .tasks/task_x.json
2. 完成一个任务会自动解除别人 blockedBy 依赖

### 4.6 BackgroundManager

位置：[agents/s_full.py](agents/s_full.py#L415)

流程：

1. run 启动后台线程
2. _exec 执行命令并更新状态
3. notifications 队列把结果推回主循环

这让模型可以“边做别的边等耗时任务”。

### 4.7 MessageBus

位置：[agents/s_full.py](agents/s_full.py#L447)

1. send：写入目标收件箱 jsonl
2. read_inbox：读取并清空
3. broadcast：批量发送

这构成了 lead 与 teammates 的通信层。

### 4.8 TeammateManager

位置：[agents/s_full.py](agents/s_full.py#L482)

它管理队友生命周期与队友自己的 agent loop。

内部两阶段：

1. Work Phase：持续调用模型 + 执行工具
2. Idle Phase：轮询 inbox + 自动认领未分配任务

自动认领逻辑里还包含 identity re-injection，避免压缩后队友“忘记自己是谁”。

## 5. 工具注册与分发：主代理如何把意图落地

### 5.1 TOOL_HANDLERS

位置：[agents/s_full.py](agents/s_full.py#L678)

这是工具名到 Python 函数的映射表，例如：

1. bash -> run_bash
2. task -> run_subagent
3. background_run -> BG.run
4. task_create -> TASK_MGR.create
5. spawn_teammate -> TEAM.spawn

### 5.2 TOOLS

位置：[agents/s_full.py](agents/s_full.py#L703)

这是发给模型的工具 schema 列表。模型只能调用这里声明过的函数。

一句话：

1. TOOL_HANDLERS 决定“怎么执行”
2. TOOLS 决定“模型能调用什么”

## 6. 主循环 agent_loop：全文件最重要的流程

位置：[agents/s_full.py](agents/s_full.py#L936)

每一轮的执行顺序非常关键：

1. microcompact
2. token 超阈值则 auto_compact
3. drain 后台通知并注入用户消息
4. 读取 lead inbox 并注入用户消息
5. 调用 chat.completions.create
6. 保存 assistant 消息
7. 如无 tool_calls，返回最终文本
8. 如有 tool_calls，逐个执行
9. 逐个追加 role=tool 回注
10. Todo 规则满足时注入 reminder
11. 若调用了 compress 工具，执行手动压缩并返回

这里最核心的一点是第 9 步：

必须把工具输出按 role=tool 和 tool_call_id 回注，模型才能在下一轮“看懂刚才工具执行了什么”。

## 7. REPL 层：你在终端里看到的行为从哪里来

位置：[agents/s_full.py](agents/s_full.py#L1014)

命令分支：

1. /compact：手动压缩 history
2. /tasks：打印任务板
3. /team：打印队友状态
4. /inbox：读取 lead 收件箱
5. 普通文本：送入 agent_loop

这部分只是“输入输出外壳”，真正智能流程都在 agent_loop。

## 8. 一次完整请求的时序脑图

你输入一句话后，程序大致这么走：

1. REPL 把你的文本 append 到 history
2. agent_loop 先做压缩和通知注入
3. LLM 产生普通回复或 tool_calls
4. 如果是 tool_calls：本地执行工具
5. 工具结果 role=tool 回注
6. 再次调用 LLM，直到没有 tool_calls
7. 返回最终文本并打印

## 9. 读代码建议顺序

建议你按这个顺序读，最容易形成系统认知：

1. 先读 main REPL：[agents/s_full.py](agents/s_full.py#L1014)
2. 再读主循环：[agents/s_full.py](agents/s_full.py#L936)
3. 再看工具注册：[agents/s_full.py](agents/s_full.py#L678)
4. 再看各个子系统类
5. 最后看队友循环与子代理循环

## 10. 常见问题与排查

1. 模型不调用工具
   先检查 TOOLS 是否声明正确，描述是否清晰。
2. 工具调用后模型像“失忆”
   检查是否正确追加了 role=tool + tool_call_id。
3. 长会话越来越慢
   看 TOKEN_THRESHOLD 是否触发 auto_compact，确认 transcript 写入正常。
4. 队友不工作
   看 TEAM 配置、inbox 文件是否写入、状态是否卡在 idle/shutdown。
5. 任务板依赖异常
   检查 TaskManager.update 中 completed 分支是否触发。

## 11. 你可以怎么扩展

1. 新增工具
   1. 写执行函数
   2. 注册到 TOOL_HANDLERS
   3. 注册到 TOOLS（用 make_tool）
2. 新增协议消息类型
   1. 扩展 VALID_MSG_TYPES
   2. 在 MessageBus 与 TeammateManager 中补处理逻辑
3. 增强压缩策略
   1. 在 microcompact 增加更多启发式规则
   2. 在 auto_compact 增加结构化摘要模板

---

如果你准备继续深入，下一步最推荐的是只盯住 agent_loop 做一次手工跟踪：

1. 人工构造一条会触发工具的请求
2. 打印 messages 每轮变化
3. 对照本文第 6 节逐步核对

这个练习做完，你就真正掌握了这个文件的主干。
