# Grok 联网搜索 (astrbot_plugin_grok_web_search)

通过 Grok API 进行实时联网搜索，返回综合答案和来源链接。支持多模态图片搜索。

## 环境要求

| 依赖 | 版本要求 | 说明 |
|------|----------|------|
| Python | >= 3.10 | |
| AstrBot | >= v4.9.2 | 基础功能（指令 + LLM Tool） |
| AstrBot | >= v4.13.2 | 使用 Skill 功能 |

**平台支持**: 全平台（无限制）

## 功能

- `/grok` 指令 - 直接执行搜索，支持附带图片进行多模态搜索
- LLM Tool (`grok_web_search`) - 供 LLM 自动调用的函数工具，自动提取用户消息中的图片
- Skill 脚本 - 可安装到 skills 目录供 LLM 脚本调用，支持 `--image-files` 传入图片

## 安装

### 俩种方式

1. 在 AstrBot 插件市场搜索 `Grok联网搜索` 点击安装
2. 在插件界面右下角点击加号选择从链接安装输入 ` https://github.com/piexian/astrbot_plugin_grok_web_search  `

## 配置

### 供应商设置

| 配置项 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `use_builtin_provider` | bool | 否 | 是否使用 AstrBot 自带供应商（默认: false） |
| `provider` | string | 条件 | 选择已配置的 LLM 供应商（启用自带供应商时必填） |
| `model` | string | 否 | 模型名称（默认: grok-4-fast，启用自带供应商时使用供应商默认模型） |

### 连接设置

| 配置项 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `base_url` | string | 条件 | Grok API 端点 URL（使用自定义供应商时必填） |
| `api_key` | string | 条件 | API 密钥（使用自定义供应商时必填） |
| `timeout_seconds` | int | 否 | 超时时间（默认: 60 秒） |
| `reuse_session` | bool | 否 | 是否复用 HTTP 会话（高频调用场景可开启，默认: false） |

### 行为设置

| 配置项 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `enable_thinking` | bool | 否 | 是否开启思考模式（默认: true） |
| `thinking_budget` | int | 否 | 思考 token 预算（默认: 32000） |
| `max_retries` | int | 否 | 最大重试次数（默认: 3） |
| `retry_delay` | float | 否 | 重试间隔时间（默认: 1 秒，范围 0.1-5 秒） |
| `retryable_status_codes` | list | 否 | 可重试的 HTTP 状态码（默认: [429, 500, 502, 503, 504]） |

### 输出设置

| 配置项 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `show_sources` | bool | 否 | 是否显示来源 URL（默认: false） |
| `max_sources` | int | 否 | 最大返回来源数量，0 表示不限制（默认: 5） |
| `custom_system_prompt` | text | 否 | 自定义系统提示词（留空使用默认提示词） |

### Skill 设置

| 配置项 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `enable_skill` | bool | 否 | 是否安装 Skill 到 skills 目录（启用后将禁用 LLM Tool） |

### HTTP 扩展

| 配置项 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `extra_body` | JSON | 否 | 额外请求体参数 |
| `extra_headers` | JSON | 否 | 额外请求头 |

## 使用

### 指令

```
/grok Python 3.12 有什么新特性
/grok 最新的 AI 新闻
/grok help              # 显示帮助和当前配置状态
```

发送图片时附带 `/grok` 指令，可进行多模态图片搜索：

```
[图片] /grok 这张图片里有什么？
```

> `/grok help` 会显示当前供应商来源、模型、系统提示词类型等配置信息。

### 重试机制

- `/grok` 指令启用自动重试功能，使用线性退避策略（`retry_delay * 重试次数`）
- LLM Tool 不自动重试，失败立即返回，由 AI 自行决定是否重新调用
- 重试仅对自定义 HTTP 客户端通过 `retryable_status_codes` 匹配状态码
- 使用 AstrBot 自带供应商时，采用异常重试机制（不受 `retryable_status_codes` 限制）

### LLM Tool

当 LLM 需要搜索实时信息时，会自动调用 `grok_web_search` 工具。如果用户消息中包含图片，工具会自动提取图片进行多模态搜索。LLM 也可以通过 `image_urls` 参数主动传入图片链接。

### Skill

开启 `enable_skill` 后，会安装 Skill 到 `data/skills/grok-search/`，LLM 可读取 SKILL.md 后执行脚本。

Skill 脚本支持通过 `--image-files` 参数传入本地图片进行多模态搜索：

```bash
python scripts/grok_search.py --query "这张图片是什么？" --image-files "/path/to/image.jpg"
```

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
astrbot_plugin_grok_web_search/
├── main.py              # 插件主入口
├── grok_client.py       # Grok API 异步客户端
├── metadata.yaml        # 插件元数据
├── _conf_schema.json    # 配置项 Schema
├── README.md
└── skill/               # Skill 脚本（首次运行后迁移到 plugin_data）
    ├── SKILL.md         # Skill 说明文档
    └── scripts/
        └── grok_search.py  # 独立搜索脚本（仅标准库）
```

## 致谢

本插件基于 [grok-skill](https://github.com/Frankieli123/grok-skill) 项目改造，感谢原作者 [@a3180623](https://linux.do/u/a3180623/summary) 的贡献。

## 更新日志

查看 [CHANGELOG.md](CHANGELOG.md) 了解版本更新历史。

## 支持

- [AstrBot 插件开发文档](https://docs.astrbot.app/dev/star/plugin-new.html)
- [Issues](https://github.com/piexian/astrbot_plugin_grok_web_search/issues)

## 🔗 相关链接
- [AstrBot](https://docs.astrbot.app/)
- [grok2api](https://github.com/chenyme/grok2api) 

## 许可

AGPL-3.0 License

<div align="center">

**如果这个插件对你有帮助，请给个 ⭐ Star 支持一下！**

</div>
