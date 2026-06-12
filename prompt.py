"""
Prompt 模板管理
统一管理所有大模型使用的 prompt，便于后续修改和维护
"""


# 新闻综合分析 prompt（领域+情绪合并）
NEWS_ANALYSIS = """
# 任务：新闻综合分析

## 角色
你是一名资深财经分析师，精通A股市场，擅长从新闻中识别所属领域和市场情绪影响。

## 输入信息

### 可选领域列表
{categories}

### 新闻标题
{title}

### 新闻内容
{content}

## 分析规则

### 领域识别规则
- **严格闭域**：只能从可选领域列表中选择
- **穿透个股看行业**：识别股票/公司背后的主营业务领域
- **核心事实优先**：依据新闻核心内容分类

### 情绪判断规则
- **利好**：业绩超预期、订单合作、政策扶持、技术突破、机构增持
- **利空**：业绩下滑、政策限制、诉讼处罚、产品问题、机构减持
- **中性**：常规公告、信息不明确、正负因素抵消

## 输出要求

- 仅输出一个 JSON 对象，格式如下：
```json
{{"categories": ["领域1", "领域2"], "sentiment": "利好/利空/中性", "reason": "原因"}}
```
- categories：从可选领域列表中选择，无相关领域输出空数组 []
- reason：控制在 30 字以内

## 示例

**输入**：
可选领域：["新能源", "汽车", "人工智能"]
新闻标题：宁德时代(300750)披露中报，净利润同比增长超预期

**输出**：{{"categories": ["新能源"], "sentiment": "利好", "reason": "业绩超预期增长"}}
"""


def get_news_analysis_prompt(categories: list, title: str, content: str) -> str:
    """
    获取新闻综合分析 prompt

    Args:
        categories: 可选领域列表
        title: 新闻标题
        content: 新闻内容

    Returns:
        格式化后的 prompt
    """
    formatted_categories = "\n".join([f"- {cat}" for cat in categories])
    return NEWS_ANALYSIS.format(
        categories=formatted_categories,
        title=title,
        content=content
    )
