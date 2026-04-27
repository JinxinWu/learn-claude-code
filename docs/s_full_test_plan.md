# s_full 全功能测试方案

## 1. 目标

验证 [agents/s_full.py](agents/s_full.py) 中所有机制在 OpenAI 兼容改造后行为正确、边界可控、可回归。

覆盖范围包含：

1. 基础工具层（bash/read/write/edit/path guard）
2. Todo 管理（校验、渲染、提醒）
3. 子代理循环
4. Skill 加载
5. 上下文压缩（microcompact/auto_compact）
6. 文件任务系统
7. 后台任务系统
8. 消息总线
9. 关机与计划审批协议
10. 队友生命周期与自动认领
11. 主 agent_loop 管线与 REPL 命令

## 2. 测试分层策略

1. 单元测试
   覆盖纯函数与局部状态机，不依赖真实模型调用。
2. 组件测试
   覆盖类之间交互，如 TaskManager + TeammateManager。
3. 集成测试
   覆盖主循环 agent_loop，在 Mock 模型下验证工具调用链。
4. 端到端冒烟
   通过 CLI 输入验证关键命令路径和退出路径。

## 3. 测试环境

1. Python 版本：与仓库当前版本一致
2. 框架：pytest
3. Mock：monkeypatch 或 unittest.mock
4. 文件隔离：tmp_path
5. 外部依赖策略：
   1. 禁止真实网络请求
   2. 所有 client.chat.completions.create 统一 mock

## 4. 覆盖矩阵

| 模块 | 功能点 | 测试类型 | 重点断言 |
|---|---|---|---|
| base_tools | safe_path 防越界 | 单元 | 越界路径抛异常 |
| base_tools | run_bash 风险命令拦截 | 单元 | 返回危险命令 blocked |
| base_tools | run_read/run_write/run_edit | 单元 | 文件内容读写改正确 |
| TodoManager | update 校验 | 单元 | 状态枚举、in_progress 数量限制 |
| TodoManager | render/has_open_items | 单元 | 展示格式与状态统计正确 |
| run_subagent | Explore/general-purpose 两条路径 | 组件 | tools 集合和回路退出行为正确 |
| SkillLoader | frontmatter 解析与 load | 单元 | 能解析 name/description，unknown 返回错误 |
| compression | estimate_tokens/microcompact | 单元 | 仅压缩旧 tool 消息，不破坏最近消息 |
| compression | auto_compact | 组件 | 写入 transcript，返回压缩后的单条消息 |
| TaskManager | create/get/update/list/claim/delete | 单元 | blockedBy 传播与删除逻辑正确 |
| BackgroundManager | run/check/drain | 组件 | 任务状态变化与通知出队正确 |
| MessageBus | send/read_inbox/broadcast | 单元 | 文件落盘、读取后清空、广播计数正确 |
| protocol | handle_shutdown_request/handle_plan_review | 单元 | request_id 记录、消息格式正确 |
| TeammateManager | spawn/list/status | 组件 | 状态机 working->idle->shutdown |
| TeammateManager | auto-claim + identity reinjection | 集成 | 可自动认领并写入消息轨迹 |
| agent_loop | 调用前预处理链 | 集成 | microcompact/bg/inbox 注入顺序正确 |
| agent_loop | tool_calls 执行与 role=tool 回注 | 集成 | tool_call_id 对齐，输出可见 |
| agent_loop | Todo nag 和 manual compress | 集成 | 满足阈值后注入 reminder，compress 后返回 |
| REPL | /compact /tasks /team /inbox/q | 端到端 | 命令行为与退出行为正确 |

## 5. 关键场景用例清单

## 5.1 单元用例

1. UT-BASE-001 safe_path 输入工作区内路径
   期望：返回 resolve 后路径。
2. UT-BASE-002 safe_path 输入 ../ 越界路径
   期望：抛 ValueError。
3. UT-BASE-003 run_bash 输入 sudo 命令
   期望：返回危险命令拦截文案。
4. UT-TODO-001 update 空 content
   期望：抛 ValueError。
5. UT-TODO-002 同时两个 in_progress
   期望：抛 ValueError。
6. UT-TODO-003 render 汇总
   期望：含已完成数量统计。
7. UT-TASK-001 completed 任务自动解除其他任务 blockedBy
   期望：相关任务 blockedBy 被移除。
8. UT-TASK-002 deleted 任务
   期望：对应 task 文件不存在。
9. UT-BUS-001 read_inbox 后再次读取
   期望：第二次为空列表。
10. UT-COMP-001 microcompact 仅清旧 tool 消息
    期望：最后三条 tool 消息不变。

## 5.2 集成用例（Mock LLM）

1. IT-LOOP-001 无 tool_calls
   输入：Mock 响应只有文本。
   期望：agent_loop 返回最终文本。
2. IT-LOOP-002 单工具调用
   输入：Mock 一个 bash tool_call。
   期望：执行 handler，并追加 role=tool 消息。
3. IT-LOOP-003 多工具调用
   输入：同轮多个 tool_call。
   期望：按顺序全部执行并回注。
4. IT-LOOP-004 非法 arguments JSON
   输入：tool_call.arguments 为非法字符串。
   期望：返回 Invalid tool arguments 错误而非崩溃。
5. IT-LOOP-005 compress 工具触发
   输入：返回 compress tool_call。
   期望：触发 auto_compact 并结束本轮。
6. IT-LOOP-006 Todo 提醒
   前置：TODO 存在 open items，连续 3 轮未调用 TodoWrite。
   期望：注入 reminder 消息。
7. IT-BG-001 背景任务通知注入
   前置：BG.drain 返回通知。
   期望：追加 background-results 用户消息。
8. IT-INBOX-001 inbox 注入
   前置：BUS.read_inbox 返回消息。
   期望：追加 inbox 用户消息。

## 5.3 队友与协议用例

1. IT-TEAM-001 spawn 已存在且非 idle/shutdown 成员
   期望：返回错误状态。
2. IT-TEAM-002 队友收到 shutdown_request
   期望：状态转为 shutdown。
3. IT-TEAM-003 队友 idle 期间自动认领未阻塞任务
   期望：任务 owner 更新为队友名。
4. IT-PLAN-001 handle_plan_review approve=true
   期望：plan_requests 状态为 approved，消息发送成功。
5. IT-PLAN-002 无效 request_id
   期望：返回错误提示。

## 5.4 REPL 冒烟

1. E2E-REPL-001 输入 /tasks
   期望：打印任务列表，不崩溃。
2. E2E-REPL-002 输入 /team
   期望：打印团队状态。
3. E2E-REPL-003 输入 /inbox
   期望：打印并清空 lead inbox。
4. E2E-REPL-004 输入 /compact
   前置：history 非空。
   期望：触发 manual compact 文案并压缩。
5. E2E-REPL-005 输入 q
   期望：进程正常退出。

## 6. Mock 设计建议

统一构造假的 completions 响应对象，最少字段：

1. choices[0].message.content
2. choices[0].message.tool_calls

tool_call 最少字段：

1. id
2. function.name
3. function.arguments

建议为以下模式提供工厂函数：

1. 纯文本响应
2. 单工具响应
3. 多工具响应
4. 非法 JSON 参数响应

## 7. 回归门禁（CI 建议）

1. python -m py_compile agents/s_full.py
2. pytest -q tests/test_s_full_*.py
3. 覆盖率门槛建议：
   1. 行覆盖率 >= 85%
   2. 分支覆盖率 >= 75%
4. 关键断言门禁：
   1. role=tool 回注必须覆盖
   2. 非法 tool arguments 必须覆盖
   3. compress 与 todo reminder 必须覆盖

## 8. 验收标准

1. 覆盖矩阵所有条目均有对应测试用例
2. 所有高优先级用例通过
3. 无真实网络调用
4. 回归门禁全部通过
5. 测试报告能定位失败功能点和场景编号
