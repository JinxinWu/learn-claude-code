# 项目结构文档

## 测试状态
✅ **全部测试通过**: 80/80 测试成功

## 目录结构

```
learn-claude-code/
├── agents/                 # AI代理实现模块
│   ├── __init__.py
│   ├── s01_agent_loop.py          # 基础代理循环
│   ├── s02_tool_use.py            # 工具使用
│   ├── s03_todo_write.py          # 待办事项写入
│   ├── s04_subagent.py            # 子代理系统
│   ├── s05_skill_loading.py       # 技能加载
│   ├── s06_context_compact.py     # 上下文压缩
│   ├── s07_permission_system.py   # 权限系统
│   ├── s08_hook_system.py         # 钩子系统
│   ├── s09_memory_system.py       # 记忆系统
│   ├── s10_system_prompt.py       # 系统提示
│   ├── s11_error_recovery.py      # 错误恢复
│   ├── s12_task_system.py         # 任务系统
│   ├── s13_background_tasks.py    # 后台任务
│   ├── s15_agent_teams.py         # 代理团队
│   ├── s16_team_protocols.py      # 团队协议
│   ├── s17_autonomous_agents.py   # 自主代理
│   ├── s18_worktree_task_isolation.py  # 工作树任务隔离
│   └── s_full.py                  # 完整参考实现
│
├── calculator/             # 计算器模块
│   ├── __init__.py               # 包导出
│   ├── __main__.py              # 模块入口
│   ├── cli.py                   # 命令行接口
│   └── operations.py            # 运算操作
│
├── tests/                  # 测试套件
│   ├── __init__.py
│   ├── test_agents_smoke.py      # 代理烟雾测试 (19个测试)
│   ├── test_calculator.py        # 计算器测试 (12个测试)
│   ├── test_cli.py              # CLI测试 (17个测试)
│   ├── test_operations.py       # 操作测试 (31个测试)
│   └── test_s_full_background.py # 后台任务测试 (1个测试)
│
├── skills/                 # 技能模块
│   ├── agent-builder/           # 代理构建器
│   ├── code-review/             # 代码审查
│   ├── mcp-builder/             # MCP构建器
│   └── pdf/                     # PDF处理
│
├── docs/                   # 文档
│   ├── en/                      # 英文文档
│   ├── ja/                      # 日文文档
│   ├── zh/                      # 中文文档
│   └── payment_refactor_plan.md
│
├── web/                    # Web应用
│   ├── public/                   # 静态资源
│   ├── scripts/                  # 脚本
│   ├── src/                      # 源代码
│   ├── next.config.ts           # Next.js配置
│   ├── package.json             # 依赖配置
│   └── vercel.json              # Vercel部署配置
│
├── .claude/                # Claude配置
├── .memory/                # 记忆存储
├── .tasks/                 # 任务存储
├── .runtime-tasks/         # 运行时任务
│
├── AI_Paper.md            # AI论文笔记
├── README.md              # 英文说明
├── README-zh.md           # 中文说明
├── README-ja.md           # 日文说明
├── calculator.py          # 计算器主程序
├── hello.py               # 示例程序
├── requirements.txt       # Python依赖
└── LICENSE                # MIT许可证
```

## 核心模块说明

### 1. agents/ - AI代理模块
包含19个自包含的代理实现文件，每个都可以独立运行：
```bash
python agents/s01_agent_loop.py
```

**编号序列**：
- **s01-s13**: 基础功能模块（循环、工具、待办、子代理、技能、上下文、权限、钩子、记忆、提示、错误、任务、后台）
- **s15-s18**: 高级功能模块（团队、协议、自主代理、工作树隔离）
- **s_full**: 完整参考实现

**注意**：缺少s14编号

### 2. calculator/ - 计算器模块
提供基础运算功能：
- **operations.py**: 加减乘除运算
- **cli.py**: 命令行接口
- **__init__.py**: 包导出和版本管理

### 3. tests/ - 测试套件
完整覆盖所有核心功能：
- **test_agents_smoke.py**: 验证所有代理脚本可编译
- **test_calculator.py**: 包导出和向后兼容性
- **test_cli.py**: 命令行参数解析和输出
- **test_operations.py**: 数学运算正确性
- **test_s_full_background.py**: 后台任务管理

### 4. skills/ - 技能系统
可插拔的技能模块：
- agent-builder: 代理构建工具
- code-review: 代码审查工具
- mcp-builder: MCP协议构建器
- pdf: PDF处理工具

## 测试详情

### 测试统计
```
tests/test_agents_smoke.py: 19个测试 ✅
tests/test_calculator.py: 12个测试 ✅
tests/test_cli.py: 17个测试 ✅
tests/test_operations.py: 31个测试 ✅
tests/test_s_full_background.py: 1个测试 ✅
总计: 80个测试，全部通过
```

### 测试覆盖范围
- ✅ 所有代理脚本的Python语法正确性
- ✅ 计算器包的API导出
- ✅ CLI参数解析和错误处理
- ✅ 数学运算的边界情况（零、负数、浮点数）
- ✅ 后台任务管理机制

## 配置文件

### .claude/
Claude Code相关配置文件

### .memory/
持久化记忆存储目录

### .tasks/
任务状态存储目录

### .runtime-tasks/
运行时任务日志和状态

## 开发建议

1. **添加新代理**: 在agents/目录创建sXX_xxx.py文件，并在test_agents_smoke.py中添加测试
2. **扩展计算器**: 在calculator/模块添加新功能，确保向后兼容
3. **新增技能**: 在skills/目录创建新的技能模块
4. **文档更新**: 相应更新docs/目录下的多语言文档

## 运行测试

```bash
# 运行所有测试
python -m pytest tests/ -v

# 运行特定测试文件
python -m pytest tests/test_calculator.py -v

# 运行特定测试
python -m pytest tests/test_operations.py::TestAdd::test_add_positive_numbers -v
```