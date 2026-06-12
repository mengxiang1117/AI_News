# AI News - 智能新闻推送系统

基于大模型的财经新闻精准推送系统，从同花顺爬取新闻，通过 AI 识别领域，按用户兴趣推送到飞书。

## 功能特点

- **6大新闻源**：7×24小时要闻、原创情报、涨停解密、快评、公司互动、公告解读
- **并行爬取**：多线程同时抓取多个新闻源，提升效率
- **AI 智能分析**：大模型自动识别新闻所属领域标签
- **精准推送**：根据用户兴趣匹配，只推送相关新闻
- **多人支持**：不同用户可关注不同领域，互不干扰
- **飞书机器人**：通过 Webhook 推送到飞书群
- **定时任务**：支持定时自动运行

## 项目结构

```
AI_News/
├── fetch_all_news.py    # 新闻爬虫（6个源并行抓取）
├── news_push.py         # 推送主程序（AI分析+飞书推送）
├── prompt.py            # 大模型 Prompt 模板，可自定义
├── config.yaml          # 配置文件（必须）
├── requirements.txt     # Python 依赖
├── cleanup_files.py     # 文件清理工具
├── news/                # 所有新闻汇总
├── 24hours_news/        # 7×24小时要闻
├── yuanchuang_news/     # 原创情报
├── mrnxgg_news/         # 涨停解密
├── djkuaiping_news/     # 快评
├── djgshd_news/         # 公司互动
└── djggjd_news/         # 公告解读
```

## 安装

### 1. 克隆项目

```bash
git clone https://github.com/mengxiang1117/AI_News.git
cd AI_News
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

## 配置

复制示例配置文件并编辑：

```bash
cp config.example.yaml config.yaml
```

编辑 `config.yaml` 文件：

### OpenAI API 配置

### 用户配置

```yaml
openai:
  api_key: "your-api-key"
  base_url: "https://api.openai.com/v1"  # 或其他兼容openai接口
  models:
    - "gpt-3.5-turbo"
    - "gpt-4"
```

```yaml
users:
  - name: "张三"
    interests:
      - 人工智能
      - 算力
    feishu:
      webhook_url: "https://open.feishu.cn/open-apis/bot/v2/hook/xxxxx"
      secret: ""  # 签名密钥，可选
  - name: "李四"
    interests:
      - 黄金
      - 有色金属
    feishu:
      webhook_url: "https://open.feishu.cn/open-apis/bot/v2/hook/yyyyy"
```

### 领域列表

```yaml
# 所有可能的领域列表（大模型从中选择）
all_categories:
  - 人工智能
  - 算力
  - 战争
  - 国际新闻
  - 氢能源
  - 可控核聚变
  - 液冷
  - 黄金
  - 有色金属
```

> **注意**：用户配置中的 `interests`（兴趣领域）必须在此列表中选择，否则无法匹配到相关新闻。

### 飞书机器人创建 （飞书电脑端创建，手机版不支持）

1. 打开飞书，进入目标群聊
2. 点击群设置 → 群机器人 → 添加机器人
3. 选择「自定义机器人」
4. 复制 Webhook 地址填入配置

## 使用方法

### 完整流程（推荐）

运行推送主程序，自动完成爬取 + AI分析 + 推送：

```bash
# 单次运行
python news_push.py

# 定时运行（按 Ctrl+C 停止）
python news_push.py --schedule

# 后台运行（推荐，无输出日志）
nohup python news_push.py --schedule  > /dev/null 2>&1 &
```

### 仅爬取新闻

如果只想爬取新闻而不推送：

```bash
python fetch_all_news.py
```

### 试运行模式

在 `config.yaml` 中设置 `dry_run: true`，将不发送实际消息，仅打印日志。

## 文件清理

新闻文件会不断积累，使用清理脚本定期删除旧文件，只保留最新的一批。


```bash
# 单次清理
python cleanup_files.py

# 定时清理
python cleanup_files.py --schedule

# 后台清理（推荐，无输出日志）
nohup python cleanup_files.py --schedule  > /dev/null 2>&1 &
```

### 清理配置

在 `config.yaml` 中配置：

```yaml
cleanup:
  enabled: true           # 是否启用清理
  interval_minutes: 60    # 清理间隔（分钟）
  folders:
    - path: "24hours_news"
      keep_count: 50     # 保留最新 50 个文件
      file_pattern: "*.md"
    - path: "yuanchuang_news"
      keep_count: 50
      file_pattern: "*.md"
```

## 项目流程

```
爬取新闻 → AI分析领域 → 匹配用户兴趣 → 推送飞书
    ↓           ↓              ↓
  并行抓取    并发调用API    按用户配置过滤
```

## 常见问题

### Q: 如何修改推送的领域标签？

编辑 `config.yaml` 中的 `all_categories` 列表即可。

### Q: API 调用失败怎么办？

程序会自动尝试配置的多个模型，全部失败时跳过该条新闻，不影响其他新闻处理。

### Q: 爬取网页失败怎么办？

程序内置重试机制，爬取网页失败时会自动重试（默认最多3次）。可在 `config.yaml` 中调整重试次数和间隔：

```yaml
crawler:
  max_retries: 3    # 最大重试次数
  retry_delay: 1    # 重试间隔（秒）
```

### Q: 如何查看已推送记录？

每个用户的推送记录保存在 `pushed_news_用户名.md` 文件中。

### Q: 每日使用的Tokens是多少？

粗略统计24小时，使用200WTokens。

## License

MIT
