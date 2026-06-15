"""
新闻精准推送系统 - 多人版（领域标签版）
大模型输出新闻相关领域标签，根据用户关心的领域匹配推送
"""
import json
import re
import os
import time
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import yaml
import requests
from openai import OpenAI
import schedule
from concurrent.futures import ThreadPoolExecutor, as_completed
from fetch_all_news import fetch_all_news_sources
from prompt import get_news_analysis_prompt

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class NewsPusher:
    """新闻推送器"""

    def __init__(self, config_path: str = "config.yaml"):
        """
        初始化新闻推送器

        Args:
            config_path: 配置文件路径
        """
        self.config = self._load_config(config_path)
        self.openai_client = self._init_openai()
        # 每个用户单独的已推送记录
        self.user_pushed_news = self._load_all_user_pushed_news()

    def _load_config(self, config_path: str) -> Dict:
        """加载配置文件"""
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"配置文件不存在: {config_path}")

        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        # 验证必要配置
        required_keys = ["openai", "users", "all_categories"]
        for key in required_keys:
            if key not in config:
                raise ValueError(f"配置文件缺少必要项: {key}")

        return config

    def _init_openai(self) -> OpenAI:
        """初始化 OpenAI 客户端"""
        openai_config = self.config["openai"]
        return OpenAI(
            api_key=openai_config["api_key"],
            base_url=openai_config.get("base_url", "https://api.openai.com/v1")
        )

    def _get_user_pushed_file(self, user_name: str) -> str:
        """获取用户的已推送记录文件名"""
        base_file = self.config["storage"].get("pushed_news_file", "pushed_news")
        safe_name = re.sub(r'[^\w\-]', '_', user_name)
        return f"{base_file}_{safe_name}.md"

    def _load_all_user_pushed_news(self) -> Dict[str, Dict[str, str]]:
        """加载所有用户的已推送新闻记录"""
        user_pushed = {}
        for user in self.config["users"]:
            user_name = user["name"]
            user_pushed[user_name] = self._load_user_pushed_news(user_name)
        return user_pushed

    def _load_user_pushed_news(self, user_name: str) -> Dict[str, str]:
        """加载单个用户的已推送新闻记录"""
        file_path = self._get_user_pushed_file(user_name)
        pushed = {}
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    matches = re.findall(r'^## .+?\n\n\*\*文件名\*\*: `([^`]+)`', content, re.MULTILINE)
                    for news_id in matches:
                        pushed[news_id] = "1"
            except Exception as e:
                logger.warning(f"加载用户 {user_name} 已推送记录失败: {e}")
        return pushed

    def _append_pushed_news(self, user_name: str, news: Dict, categories: List[str], match_categories: List[str], sentiment: Dict):
        """追加记录已推送的新闻到用户的 Markdown 文件"""
        file_path = self._get_user_pushed_file(user_name)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        sentiment_emoji = {"利好": "🔴", "利空": "🟢", "中性": "⚪"}.get(sentiment['sentiment'], "⚪")
        md_content = f"\n## {news['title']}\n\n"
        md_content += f"**推送时间**: {now}\n\n"
        md_content += f"**文件名**: `{news['id']}.md`\n\n"
        md_content += f"**发布时间**: {news['time']}\n\n"
        md_content += f"**来源**: {news['source']}\n\n"
        md_content += f"**新闻相关领域**: {', '.join(categories)}\n\n"
        md_content += f"**用户匹配领域**: {', '.join(match_categories)}\n\n"
        md_content += f"**市场情绪**: {sentiment_emoji} {sentiment['sentiment']} - {sentiment['reason']}\n\n"
        md_content += f"**原文链接**: {news['url']}\n\n"
        md_content += f"---\n\n"
        md_content += f"**内容摘要**:\n\n{news['content']}...\n\n"
        md_content += f"---\n"

        try:
            with open(file_path, "a", encoding="utf-8") as f:
                if os.path.getsize(file_path) == 0:
                    f.write(f"# 已推送新闻记录 - {user_name}\n\n")
                f.write(md_content)
        except Exception as e:
            logger.error(f"追加已推送新闻记录失败: {e}")

    def parse_news_from_folder(self, folder: str = None) -> List[Dict]:
        """
        从文件夹中读取新闻

        Args:
            folder: 新闻文件夹路径，默认使用配置中的路径

        Returns:
            新闻列表
        """
        if folder is None:
            folder = self.config["storage"].get("news_folder", "news")

        if not os.path.exists(folder):
            logger.warning(f"新闻文件夹不存在: {folder}")
            return []

        news_list = []
        for filename in os.listdir(folder):
            if not filename.endswith(".md"):
                continue

            file_path = os.path.join(folder, filename)
            try:
                news = self._parse_news_file(file_path)
                if news:
                    news_list.append(news)
            except Exception as e:
                logger.error(f"解析新闻文件失败 {filename}: {e}")

        return news_list

    def _parse_news_file(self, file_path: str) -> Optional[Dict]:
        """解析单个新闻文件"""
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 提取新闻ID（从文件名）
        news_id = os.path.splitext(os.path.basename(file_path))[0]

        # 提取标题
        title_match = re.search(r'^# (.+)$', content, re.MULTILINE)
        title = title_match.group(1) if title_match else "无标题"

        # 提取发布时间
        time_match = re.search(r'\*\*发布时间\*\*: (.+)', content)
        pub_time = time_match.group(1) if time_match else ""

        # 提取来源
        source_match = re.search(r'\*\*来源\*\*: (.+)', content)
        source = source_match.group(1) if source_match else ""

        # 提取链接
        url_match = re.search(r'\*\*原文链接\*\*: (.+)', content)
        url = url_match.group(1) if url_match else ""

        # 提取正文内容（在 --- 之后）
        content_match = re.search(r'---\s*\n\s*(.+)', content, re.DOTALL)
        news_content = content_match.group(1).strip() if content_match else ""

        return {
            "id": news_id,
            "title": title,
            "content": news_content,
            "url": url,
            "time": pub_time,
            "source": source,
            "md_content": content
        }

    def analyze_news(self, news: Dict) -> Tuple[List[str], Dict]:
        """
        综合分析新闻（领域+情绪合并为一次API调用）

        Args:
            news: 新闻数据

        Returns:
            (领域列表, 情绪分析结果)
        """
        categories = self.config["all_categories"]
        models = self.config["openai"].get("models", ["gpt-3.5-turbo"])
        prompt = get_news_analysis_prompt(categories, news['title'], news['content'])

        last_error = None
        for model in models:
            try:
                logger.debug(f"尝试使用模型 {model} 进行综合分析")
                response = self.openai_client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "你是资深财经分析师，擅长领域识别和情绪分析。"},
                        {"role": "user", "content": prompt}
                    ],
                    reasoning_effort="minimal",
                    temperature=0.3,
                    max_tokens=300
                )

                content = response.choices[0].message.content
                if not content:
                    logger.warning(f"模型 {model} 返回空内容，尝试下一个")
                    continue
                result_text = content.strip()

                # 提取 JSON 对象
                json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group())
                else:
                    result = json.loads(result_text)

                if not isinstance(result, dict):
                    logger.warning(f"模型 {model} 返回格式不正确: {result_text}")
                    continue

                # 提取领域
                news_categories = result.get("categories", [])
                valid_categories = [cat for cat in news_categories if cat in categories]

                # 提取情绪
                sentiment = result.get("sentiment", "中性")
                reason = result.get("reason", "")
                if sentiment not in ["利好", "利空", "中性"]:
                    sentiment = "中性"

                logger.debug(f"模型 {model} 综合分析成功")
                return valid_categories, {"sentiment": sentiment, "reason": reason}

            except Exception as e:
                last_error = e
                logger.warning(f"模型 {model} 综合分析失败: {e}，尝试下一个模型")
                continue

        logger.error(f"所有模型综合分析都失败，最后错误: {last_error}")
        return [], {"sentiment": "中性", "reason": "分析失败"}

    def match_user_interests(self, news_categories: List[str], user_interests: List[str]) -> List[str]:
        """
        匹配新闻领域和用户兴趣

        Args:
            news_categories: 新闻相关领域列表
            user_interests: 用户兴趣列表

        Returns:
            匹配到的领域列表
        """
        matched = []
        for cat in news_categories:
            if cat in user_interests:
                matched.append(cat)
        return matched

    def _gen_feishu_sign(self, secret: str, timestamp: int) -> str:
        """生成飞书机器人签名"""
        if not secret:
            return ""

        try:
            import hmac
            import hashlib
            import base64

            string_to_sign = f"{timestamp}\n{secret}"
            hmac_code = hmac.new(
                string_to_sign.encode("utf-8"),
                digestmod=hashlib.sha256
            ).digest()
            return base64.b64encode(hmac_code).decode("utf-8")
        except Exception as e:
            logger.error(f"生成签名失败: {e}")
            return ""

    def push_to_feishu(self, news: Dict, news_categories: List[str], match_categories: List[str], sentiment: Dict, user_config: Dict) -> bool:
        """
        推送新闻到飞书

        Args:
            news: 新闻数据
            news_categories: 新闻相关领域
            match_categories: 匹配到的用户领域
            sentiment: 情绪分析结果
            user_config: 用户配置

        Returns:
            是否推送成功
        """
        feishu_config = user_config["feishu"]
        webhook_url = feishu_config["webhook_url"]
        secret = feishu_config.get("secret", "")

        timestamp = int(time.time())
        sign = self._gen_feishu_sign(secret, timestamp)

        # 构建富文本消息
        sentiment_emoji = {"利好": "🔴", "利空": "🟢", "中性": "⚪"}.get(sentiment['sentiment'], "⚪")
        content = f"**发布时间**: {news['time']}\n"
        content += f"**来源**: {news['source']}\n"
        content += f"**新闻相关领域**: {', '.join(news_categories)}\n"
        content += f"**匹配您的领域**: {', '.join(match_categories)}\n"
        content += f"**市场情绪**: {sentiment_emoji} {sentiment['sentiment']} - {sentiment['reason']}\n\n"
        content += f"---\n\n"
        content += f"{news['content']}..."

        message = {
            "msg_type": "post",
            "content": {
                "post": {
                    "zh_cn": {
                        "title": news["title"],
                        "content": [
                            [
                                {
                                    "tag": "text",
                                    "text": content
                                }
                            ],
                            [
                                {
                                    "tag": "a",
                                    "text": "阅读原文",
                                    "href": news["url"]
                                }
                            ]
                        ]
                    }
                }
            }
        }

        if sign:
            message["timestamp"] = str(timestamp)
            message["sign"] = sign

        if self.config.get("dry_run", False):
            logger.info(
                f"[ {user_config['name']} ] DRY RUN 跳过飞书推送: "
                f"{news['title']} | 匹配领域: {', '.join(match_categories)} | 情绪: {sentiment['sentiment']}"
            )
            return True

        try:
            response = requests.post(webhook_url, json=message, timeout=10)
            data = response.json()
            if data.get("code") == 0:
                logger.info(f"[ {user_config['name']} ] 推送成功: {news['title']}")
                return True
            else:
                logger.error(f"[ {user_config['name']} ] 推送失败: {data}")
                return False
        except Exception as e:
            logger.error(f"[ {user_config['name']} ] 推送异常: {e}")
            return False

    def run(self):
        """执行一次推送任务"""
        logger.info("=" * 60)
        logger.info("开始执行新闻推送任务")
        logger.info("=" * 60)

        # 1. 获取最新新闻
        logger.info("正在获取最新新闻...")
        try:
            fetch_all_news_sources(clear_news=True)
        except Exception as e:
            logger.error(f"获取新闻失败: {e}")

        # 2. 读取新闻
        news_list = self.parse_news_from_folder()
        logger.info(f"读取到 {len(news_list)} 条新闻")

        if not news_list:
            logger.info("没有新闻可处理")
            return

        # 3. 用大模型提取每条新闻的领域标签（并发处理）
        all_categories = self.config["all_categories"]
        max_workers = self.config.get("concurrency", {}).get("max_workers", 3)
        logger.info(f"\n--- 提取新闻领域标签 (可选领域: {', '.join(all_categories)}) ---")
        logger.info(f"并发数: {max_workers}")

        news_with_categories = []

        def process_news(news):
            """单条新闻处理函数"""
            try:
                categories, sentiment = self.analyze_news(news)
                return news, categories, sentiment
            except Exception as e:
                logger.error(f"处理新闻失败 {news['title'][:30]}: {e}")
                return news, [], {"sentiment": "中性", "reason": "处理失败"}

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_news = {executor.submit(process_news, news): news for news in news_list}

            for future in as_completed(future_to_news):
                news, categories, sentiment = future.result()
                if categories:
                    logger.info(f"[分析完成] {news['title'][:40]} -> 相关领域: {', '.join(categories)} | 情绪: {sentiment['sentiment']}")
                    news_with_categories.append((news, categories, sentiment))
                else:
                    logger.info(f"[分析完成] {news['title'][:40]} -> 无相关领域，跳过")

        logger.info(f"\n领域提取完成，共 {len(news_with_categories)} 条新闻有相关领域")

        if not news_with_categories:
            logger.info("没有相关领域的新闻")
            return

        # 4. 对每个用户匹配领域并推送（用户之间并行）
        dry_run = self.config.get("dry_run", False)
        if dry_run:
            logger.info("DRY RUN 模式已启用：不会发送飞书消息，也不会写入已推送记录")

        user_push_workers = self.config.get("concurrency", {}).get(
            "user_push_workers",
            min(len(self.config["users"]), max_workers)
        )
        user_push_workers = max(1, min(user_push_workers, len(self.config["users"])))
        logger.info(f"\n--- 开始并行推送飞书用户，并发用户数: {user_push_workers} ---")

        def process_user(user_config):
            """单个用户推送函数"""
            user_name = user_config["name"]
            user_interests = user_config["interests"]
            user_pushed = self.user_pushed_news.get(user_name, {})
            pushed_count = 0

            logger.info(f"\n--- 处理用户: {user_name} (关心领域: {', '.join(user_interests)}) ---")

            for news, categories, sentiment in news_with_categories:
                news_id = news["id"]

                if news_id in user_pushed:
                    logger.debug(f"[ {user_name} ] 新闻已推送过，跳过: {news_id}")
                    continue

                # 领域匹配
                match_categories = self.match_user_interests(categories, user_interests)
                if not match_categories:
                    logger.debug(f"[ {user_name} ] 未匹配到领域，跳过: {news['title'][:30]}")
                    continue

                logger.info(f"[ {user_name} ] 匹配到领域: {', '.join(match_categories)} | 情绪: {sentiment['sentiment']}")
                logger.info(f"[ {user_name} ] 正在推送: {news['title'][:30]}...")

                if self.push_to_feishu(news, categories, match_categories, sentiment, user_config):
                    pushed_count += 1
                    if not dry_run:
                        user_pushed[news_id] = "1"
                        self._append_pushed_news(user_name, news, categories, match_categories, sentiment)
                        time.sleep(1)

            logger.info(f"[ {user_name} ] 完成! 本次推送 {pushed_count} 条新闻")
            return user_name, pushed_count

        total_pushed = 0
        with ThreadPoolExecutor(max_workers=user_push_workers) as executor:
            future_to_user = {
                executor.submit(process_user, user_config): user_config["name"]
                for user_config in self.config["users"]
            }

            for future in as_completed(future_to_user):
                user_name = future_to_user[future]
                try:
                    _, pushed_count = future.result()
                    total_pushed += pushed_count
                except Exception as e:
                    logger.error(f"[ {user_name} ] 用户推送任务异常: {e}")

        logger.info("\n" + "=" * 60)
        logger.info(f"所有用户处理完成，本次共推送 {total_pushed} 条")
        logger.info("=" * 60)

    def run_scheduled(self):
        """运行定时任务"""
        interval = self.config["schedule"].get("interval_minutes", 30)
        schedule.every(interval).minutes.do(self.run)

        logger.info(f"定时任务已启动，每 {interval} 分钟检查一次")
        logger.info("按 Ctrl+C 停止")

        self.run()

        try:
            while True:
                schedule.run_pending()
                time.sleep(60)
        except KeyboardInterrupt:
            logger.info("定时任务已停止")


def main():
    """主函数"""
    import sys

    pusher = NewsPusher()

    if len(sys.argv) > 1 and sys.argv[1] == "--schedule":
        if pusher.config["schedule"].get("enabled", True):
            pusher.run_scheduled()
        else:
            logger.info("定时任务未启用，执行单次任务")
            pusher.run()
    else:
        pusher.run()


if __name__ == "__main__":
    main()
