# Changelog

本项目遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [1.2.0] - 2026-03-17

### Fixed
- **重大修复**：使用 xAI Responses API (`/v1/responses`) 替代 Chat Completions API (`/v1/chat/completions`)
  - 之前的 API 端点不支持真正的联网搜索，导致模型返回幻觉内容
  - Responses API 是 xAI 官方支持 `web_search` 工具的正确端点
  - 现在会进行真正的联网搜索，返回准确的实时信息和引用来源
- 修复 `num_sources_used: 0` 问题，现在可以看到真实的搜索调用 (`web_search_call`)

### Added
- 新增 `proxy` 配置项：支持 HTTP 代理配置（如 `http://127.0.0.1:7890`）
  - 代理同时应用于连通性检查和搜索请求
- 新增 `citations` 返回字段：包含 API 返回的引用来源列表

### Changed
- 移除 `reasoning_effort` 和 `reasoning_budget_tokens` 参数（Grok 4.20+ 不支持）
- 更新响应解析逻辑以适配 Responses API 的 `output` 数组格式
- 从 `annotations` 中提取 `url_citation` 作为引用来源

### Technical Details
- Responses API 请求格式：
  ```json
  {
    "model": "grok-4.20-beta-0309-non-reasoning",
    "input": [...],
    "tools": [{"type": "web_search"}]
  }
  ```
- 推荐使用 `grok-4.20-beta-0309-non-reasoning` 模型以获得最佳联网搜索效果

## [1.1.0] - 2026-03-13

### Added
- **图片搜索**：`/grok` 指令、`grok_web_search` LLM Tool、Skill 脚本均支持图片输入
- `/grok` 指令：自动提取用户消息中的图片，支持直接发送图片、回复带图片的消息、QQ 转发消息（嵌套）
- `/grok` 指令：自动提取回复消息和转发消息中的文本内容作为查询上下文
- `grok_web_search` LLM Tool：新增 `image_urls` 参数，支持传入图片 URL 或 base64 链接
- `grok_web_search` LLM Tool：自动提取用户消息中的图片和文本上下文
- Skill 脚本：新增 `--image-files` 参数，支持传入本地图片文件路径
- `grok_client.py`：`grok_search()` 支持 `images` 参数，构建 OpenAI 接口的`image_url` 消息

### Changed
- CI 工作流改为自动修复模式：`ruff format` + `ruff check --fix`，格式变更自动提交


<details>
<summary>历史版本</summary>

## [1.0.9] - 2026-03-11

### Fixed
- 修复 `/grok` 指令关键词含空格时只取第一个词的问题（如 `/grok 1 2 3` 只搜索 `1`）
- 使用 AstrBot 框架的 `GreedyStr` 类型捕获命令后的完整文本

## [1.0.8] - 2026-03-08

### Changed
- Skill 安装改用 `SkillManager.install_skill_from_zip()` 官方接口，正式注册到 `skills.json` 配置
- Skill 卸载改用 `SkillManager.delete_skill()` 官方接口，同步清理目录和配置
- Skill 首次迁移从移动改为复制，插件源目录始终保留原始副本
- 移除手动路径管理回退逻辑，统一依赖 SkillManager API

## [1.0.7] - 2026-03-04

### Added
- 新增 JSON 响应降级处理：当内置供应商返回非 JSON 格式时，自动提取纯文本和 URL 作为来源，不再直接报错
- 新增 `_try_parse_json_response()` 方法：支持解析多种格式（纯 JSON、Markdown 代码块、混合文本中的嵌套 JSON）
- 新增 `_extract_sources_from_text()` 方法：从非 JSON 文本中提取 URL 作为来源

### Changed
- `/grok` 指令提示词改为英文指令 + JSON 格式 + 中文回复要求（专有名词保留原文）
- LLM Tool 和 Skill 提示词保持英文 + JSON 格式（无语言要求）
- JSON 解析改用 `json.JSONDecoder().raw_decode` 支持嵌套结构，避免正则截断问题

### Fixed
- 修复混合文本中嵌套 JSON 解析失败的问题
- 修复内置供应商返回非 JSON 时用户看到"获取到非 JSON 文本"错误的问题

### Security
- URL 协议白名单校验：仅允许 `http`/`https`，拒绝 `javascript:`、`data:`、`file:` 等协议
- URL 长度限制：最大 2048 字符
- URL 控制字符过滤：拒绝包含 ASCII 控制字符的 URL
- 错误响应检测：识别 rate limit、unauthorized 等错误模式，避免将错误文案误判为成功

## [1.0.6] - 2026-02-21

### Added
- 新增 `astrbot_version` 元数据字段：声明最低 AstrBot 版本要求 (>=4.9.2)
- 新增 `support_platforms` 元数据字段：声明支持的平台（空数组表示全平台支持）

### Changed
- 适配 AstrBot PR #5235 插件元数据规范，支持版本兼容性检查

## [1.0.5] - 2026-02-12

### Added
- 新增 `use_builtin_provider` 配置项：支持使用 AstrBot 自带供应商
- 新增 `provider` 配置项：选择已配置的 LLM 供应商（仅当启用自带供应商时生效）
- 新增 `max_retries` 配置项：最大重试次数（默认: 3，支持滑块调节 0-10）
- 新增 `retry_delay` 配置项：重试间隔时间（默认: 1 秒，支持滑块调节 0.1-5 秒）
- 新增 `retryable_status_codes` 配置项：可重试的 HTTP 状态码列表（默认: 429, 500, 502, 503, 504）
- 新增 `custom_system_prompt` 配置项：自定义系统提示词（支持多行编辑器）
- `/grok` 指令使用独立的中文系统提示词，要求使用中文回复
- `/grok help` 显示当前配置状态（供应商来源、模型、提示词类型）
- 支持延迟初始化：启用自带供应商时，在 AstrBot 加载完成后初始化

### Changed
- 当启用自带供应商时，自动使用供应商默认模型和参数（不覆盖 model/reasoning 等字段）
- 重试功能仅对 `/grok` 指令启用，LLM Tool 不再自动重试（由 AI 自行决定是否重新调用）
- `retryable_status_codes` 仅对自定义 HTTP 客户端生效，内置供应商使用异常重试机制
- 内置供应商重试延迟改为线性退避策略（`retry_delay * attempts`），与外部客户端行为一致
- 配置项描述和提示信息拆分为 `description` + `hint`，提升可读性
- 简化 `max_retries` / `retry_delay` 配置解析逻辑，由 UI 滑块约束输入范围

### Fixed
- 修复 `/grok` 指令发送失败后 LLM 兜底重复调用 `grok_web_search` 的问题
- 修复自定义供应商模式下 `/grok help` 仍显示内置供应商名称的问题


## [1.0.4] - 2026-02-03

### Added
- 兼容 SSE 流式响应：自动检测并解析 `text/event-stream` 格式的响应，合并所有 chunk 内容后返回
- 新增 `enable_thinking` 配置项：是否开启思考模式（默认开启）
- 新增 `thinking_budget` 配置项：思考 token 预算（默认 32000）

### Changed
- 默认模型从 `grok-4-expert` 改为 `grok-4-fast`
- 开启思考模式时自动添加 `reasoning_effort: "high"` 和 `reasoning_budget_tokens` 参数

## [1.0.3] - 2026-02-02

### Added
- 新增 `reuse_session` 配置项：复用 HTTP 会话，高频调用场景可开启以减少连接开销（默认关闭）

### Changed
- `parse_json_config()` 不再直接输出到 stderr，改为返回错误信息由调用方通过 logger 记录
- `grok_search()` 支持传入外部 `aiohttp.ClientSession` 以复用连接
- 所有错误信息改为中文友好提示，包含具体原因和解决建议
- 异常处理细化：捕获具体异常类型，记录详细解析失败原因

### Fixed
- 修复 JSON 配置解析失败时日志绕过 AstrBot logger 的问题

### Security
- `extra_body` 保护关键字段（`model`、`messages`、`stream`）不被覆盖
- `extra_headers` 保护关键请求头（`Authorization`、`Content-Type`）不被覆盖

## [1.0.2] - 2026-02-02

### Changed
- 启用 Skill 时自动禁用 LLM Tool，避免 AI 重复调用

### Added
- 新增 `show_sources` 配置项：控制是否显示来源 URL（默认关闭）
- 新增 `max_sources` 配置项：控制最大返回来源数量

### Changed
- LLM Tool 返回结果改为纯文本格式（无 Markdown）
- Grok 提示词添加禁止返回 Markdown 格式的要求

## [1.0.0] - 2026-02-02

### Added
- `/grok` 指令：直接执行联网搜索
- `grok_web_search` LLM Tool：供 LLM 自动调用
- Skill 脚本支持：可安装到 skills 目录供 LLM 脚本调用
- 配置项支持：
  - `base_url`: Grok API 端点
  - `api_key`: API 密钥
  - `model`: 模型名称
  - `timeout_seconds`: 超时时间
  - `extra_body`: 额外请求体参数
  - `extra_headers`: 额外请求头
  - `enable_skill`: Skill 安装开关
- GitHub Issue 模板（Bug 报告、功能请求）
- GitHub Actions CI 配置（ruff lint + format check）

### Security
- JSON 响应解析异常处理
- API 错误和空响应检测
- Skill 安装 symlink 安全检查
- 占位符 URL/API Key 过滤

</details>
