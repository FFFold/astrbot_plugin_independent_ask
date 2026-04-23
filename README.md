# 独立LLM请求 (astrbot_plugin_independent_ask)

本插件修改自 [piexian/astrbot_plugin_grok_web_search](https://github.com/piexian/astrbot_plugin_grok_web_search)。

用于在当前上下文之外发起一次独立的额外 LLM 请求，支持多模态图片输入、联网检索、网页内容抓取。

> 注意：本插件使用新的插件名 `astrbot_plugin_independent_ask`，按新插件安装处理，不提供对原 `astrbot_plugin_grok_web_search` 的配置自动迁移。若你同时安装原插件和本插件，两者会分别维护各自的配置和数据目录。

## 环境要求

| 依赖 | 版本要求 | 说明 |
|------|----------|------|
| Python | >= 3.10 | |
| AstrBot | >= v4.9.2 | 基础功能（指令） |

**平台支持**: 全平台（无限制）

## 功能

- `/ask` 指令 - 直接发起一次独立请求，支持附带图片进行多模态处理
- 模型路由 - 通过 `/ask <模型路由> <请求内容>` 为不同模型或供应商分别发起请求
- 搜索结果图片卡片 - 基于 Pillow 纯本地渲染，面板式布局，支持日/夜自动主题

## 安装

### 俩种方式

1. 在 AstrBot 插件市场搜索 `独立LLM请求` 点击安装
2. 在插件界面右下角点击加号选择从链接安装输入 ` https://github.com/FFFold/astrbot_plugin_independent_ask  `

## 配置

### 供应商设置

| 配置项 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `use_builtin_provider` | bool | 否 | 是否使用 AstrBot 自带供应商（默认: false） |
| `provider` | string | 条件 | 选择已配置的 LLM 供应商（启用自带供应商时必填） |
| `model` | string | 否 | 模型名称（默认留空，启用自带供应商或留空时由服务端决定） |

### 连接设置

| 配置项 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `base_url` | string | 条件 | API 端点 URL（使用自定义供应商时必填） |
| `api_key` | string | 条件 | API 密钥（使用自定义供应商时必填） |
| `timeout_seconds` | int | 否 | 超时时间（默认: 60 秒） |
| `reuse_session` | bool | 否 | 是否复用 HTTP 会话（高频调用场景可开启，默认: false） |

### 行为设置

| 配置项 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `enable_thinking` | bool | 否 | 是否开启思考模式（默认: true） |
| `thinking_budget` | int | 否 | 思考 token 预算（默认: 32000） |
| `max_retries` | int | 否 | 最大重试次数（默认: 3） |
| `retry_delay` | float | 否 | 重试间隔时间（默认: 1 秒），429 时优先使用 Retry-After 头 |
| `retryable_status_codes` | list | 否 | 可重试的 HTTP 状态码（默认: [429, 500, 502, 503, 504]） |

### 模型路由

`model_routes` 用于为 `/ask` 增加按首个参数切换模型的能力。命中路由后，插件会使用该路由的配置覆盖默认请求配置。

适用场景：

- `/ask gemma 如何学习日语？`
- `/ask deepseek 番茄炒蛋怎么做？`
- `/ask gpt5.4 美国总统是谁？`

每个路由项支持这些字段：

| 配置项 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `enabled` | bool | 否 | 是否启用该路由（默认: true） |
| `route_name` | string | 是 | 路由名称，例如 `gemma` |
| `aliases` | list | 否 | 路由别名列表，例如 `gpt54` |
| `use_builtin_provider` | bool | 否 | 是否对该路由使用 AstrBot 自带供应商 |
| `provider` | string | 条件 | 该路由使用内置供应商时必填 |
| `model` | string | 否 | 该路由的模型名称 |
| `use_responses_api` | bool | 否 | 该路由是否使用 `/v1/responses` |
| `base_url` | string | 条件 | 该路由使用自定义 HTTP 时必填 |
| `api_key` | string | 条件 | 该路由使用自定义 HTTP 时必填 |
| `timeout_seconds` | int | 否 | 该路由的超时时间 |
| `enable_thinking` | bool | 否 | 该路由是否启用 thinking |
| `thinking_budget` | int | 否 | 该路由的 thinking token 预算 |
| `custom_system_prompt` | text | 否 | 该路由的自定义系统提示词 |
| `extra_body` | JSON | 否 | 该路由的额外请求体参数 |
| `extra_headers` | JSON | 否 | 该路由的额外请求头 |
| `proxy` | string | 否 | 该路由的 HTTP 代理 |

说明：

- `show_sources`、`render_as_image`、`max_sources` 等输出表现目前仍沿用全局配置
- 路由名称和别名按不区分大小写匹配
- `/ask help` 仍显示帮助；只有首个参数命中路由时，才会切换到对应模型
- 路由后可使用空格、换行或制表符分隔请求内容
- 路由配置采用“按字段覆盖”的继承方式：未填写时默认继承全局配置
- `provider`、`model`、`base_url`、`api_key` 留空时会继续继承全局值，适合多个路由共用同一套供应商连接信息
- `custom_system_prompt` 留空时不会继承全局提示词，而是回退到插件内置提示词
- `proxy`、`extra_body`、`extra_headers` 可显式填写为空值，用于清空对应的全局设置
- `text` 类型表示 AstrBot WebUI 中的多行文本输入字段，与普通 `string` 单行输入相对应

示例配置：

```json
[
  {
    "enabled": true,
    "route_name": "gemma",
    "use_builtin_provider": true,
    "provider": "gemma_provider"
  },
  {
    "enabled": true,
    "route_name": "deepseek",
    "model": "deepseek-chat",
    "base_url": "https://api.example.com",
    "api_key": "sk-xxxx"
  },
  {
    "enabled": true,
    "route_name": "gpt5.4",
    "aliases": ["gpt54"],
    "model": "gpt-5.4",
    "base_url": "https://api.openai-compatible.example",
    "api_key": "sk-yyyy"
  }
]
```

### 输出设置

| 配置项 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `show_sources` | bool | 否 | 是否显示来源 URL（默认: false） |
| `render_as_image` | bool | 否 | 是否将搜索结果渲染为图片卡片（默认: false） |
| `card_theme` | string | 否 | 卡片主题：auto（按时间自动）/ dark / light（默认: auto） |
| `max_sources` | int | 否 | 最大返回来源数量，0 表示不限制（默认: 5） |
| `custom_system_prompt` | text | 否 | 自定义系统提示词（留空使用默认提示词） |

### API 模式

| 配置项 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `use_responses_api` | bool | 否 | 使用 `/v1/responses` 接口，是否可用取决于目标服务端实现 |

> 修改配置后插件会自动重载并应用新设置。

### 图片卡片渲染

启用 `render_as_image` 后，`/ask` 指令的结果将渲染为精美的图片卡片发送：

- **面板式布局**：每个标题自动分割为独立面板，圆角矩形 + 科技青竖条装饰
- **日/夜自动主题**：`card_theme` 为 `auto` 时根据系统时间自动切换（7:00-18:00 浅色）
- **Markdown 支持**：标题、列表、代码块、引用、**粗体**、`行内代码`
- **来源链接**：以单独文本消息发送（可点击/复制）

#### 效果展示

| 深色主题 | 浅色主题 |
|:---:|:---:|
| ![深色主题](https://github.com/FFFold/astrbot_plugin_independent_ask/blob/master/image/dark.png) | ![浅色主题](https://github.com/FFFold/astrbot_plugin_independent_ask/blob/master/image/light.png) |

**字体说明**：首次启用时自动从清华镜像下载 Sarasa Term Slab SC 字体。也可在 `data/plugin_data/astrbot_plugin_independent_ask/font/` 目录放入自定义 `.ttf` 字体文件。

### HTTP 扩展

| 配置项 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `extra_body` | JSON | 否 | 额外请求体参数 |
| `extra_headers` | JSON | 否 | 额外请求头 |

## 使用

### 指令

```
/ask Python 3.12 有什么新特性
/ask 帮我总结今天的 AI 新闻
/ask gemma 如何学习日语
/ask deepseek	番茄炒蛋怎么做
/ask gpt5.4
美国总统是谁？
/ask help               # 显示帮助和当前配置状态
```

发送图片时附带 `/ask` 指令，可进行多模态请求，例如翻译图片文字：

```
[图片] /ask 翻译这张图片里的文字
```

> `/ask help` 会显示当前供应商来源、模型、系统提示词类型等配置信息。

### 重试机制

- `/ask` 指令启用自动重试，429 时优先使用服务端 `Retry-After` 头指定的等待时间，其他错误使用线性退避
- 重试仅对自定义 HTTP 客户端通过 `retryable_status_codes` 匹配状态码
- 使用 AstrBot 自带供应商时，采用异常重试机制（不受 `retryable_status_codes` 限制）

## 输出示例

```
Python 3.12 的主要新特性包括:

1. 更好的错误消息 - 改进了语法错误提示
2. 类型参数语法 - 支持泛型类型参数
3. 性能提升 - 解释器启动更快

来源:
  1. Python 3.12 Release Notes
     https://docs.python.org/3/whatsnew/3.12.html
  2. ...

(耗时: 2345ms)
```

## 项目结构

```
astrbot_plugin_independent_ask/
├── main.py              # 插件主入口
├── api/                 # API 客户端
│   ├── grok_chat.py     # Chat Completions API 客户端
│   └── grok_responses.py# Responses API 客户端
├── tool/                # 工具模块
│   ├── tool.py          # 共享工具（常量、工具函数、重试逻辑）
│   └── card_render.py   # 搜索结果图片卡片渲染器
├── image/               # 示例图片
├── metadata.yaml        # 插件元数据
├── _conf_schema.json    # 配置项 Schema
├── README.md
```

## 致谢

- [GrokSearch](https://github.com/GuDaStudio/GrokSearch) — 网页内容抓取功能参考了该项目的实现，感谢 [GuDa Studio](https://github.com/GuDaStudio) 的开源贡献。
- [@Stonesan233](https://github.com/Stonesan233) — PR [#5](https://github.com/FFFold/astrbot_plugin_independent_ask/pull/5) 贡献了 Responses API 支持和代理配置。

## 更新日志

查看 [CHANGELOG.md](https://github.com/FFFold/astrbot_plugin_independent_ask/blob/master/CHANGELOG.md) 了解版本更新历史。

## 支持

- [AstrBot 插件开发文档](https://docs.astrbot.app/dev/star/plugin-new.html)
- [Issues](https://github.com/FFFold/astrbot_plugin_independent_ask/issues)

## 🔗 相关链接
- [AstrBot](https://docs.astrbot.app/)
- [grok2api](https://github.com/chenyme/grok2api)

## 许可

AGPL-3.0 License
