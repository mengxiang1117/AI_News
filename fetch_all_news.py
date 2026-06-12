"""
同花顺新闻爬虫 - 整合版
获取所有6个新闻源并保存到统一文件夹和各自文件夹
"""
import json
import re
import os
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from bs4 import BeautifulSoup


def replace_newlines_with_period(text):
    """将文本中的换行符替换为句号"""
    if not text:
        return text
    # 先将多个换行或空格替换为单个空格
    text = re.sub(r'\s+', ' ', text)
    # 确保句子结尾有句号
    text = text.strip()
    if text and not text.endswith(('。', '.', '！', '!', '？', '?')):
        text += '。'
    return text


def fetch_news_detail(news_url, max_retries=3):
    """获取新闻详情内容和完整标题（支持重试）"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    for attempt in range(max_retries):
        try:
            resp = requests.get(news_url, headers=headers, timeout=10)
            # 直接使用原始字节让BeautifulSoup处理编码
            soup = BeautifulSoup(resp.content, 'html.parser')

            # 提取完整标题
            full_title = ""

            # 1. 先从 <title> 标签提取
            title_tag = soup.find('title')
            if title_tag and title_tag.string:
                full_title = title_tag.string.strip()
                # 去除常见的后缀如 " - 同花顺财经"
                for suffix in [" - 同花顺财经", "_同花顺财经", "|同花顺财经", " - 同花顺", "_同花顺"]:
                    if full_title.endswith(suffix):
                        full_title = full_title[:-len(suffix)].strip()

            # 2. 再尝试 CSS 选择器获取更准确的标题
            title_selectors = [
                ".main-title",
                ".article-title",
                "h1",
                ".title",
                ".arc-title"
            ]
            for selector in title_selectors:
                elem = soup.select_one(selector)
                if elem:
                    title_text = elem.get_text(strip=True)
                    if title_text and len(title_text) > 5:
                        full_title = title_text
                        break

            # 提取内容 - 尝试多个选择器
            content = ""
            content_selectors = [
                ".main-text",
                ".content",
                ".article-content",
                "#content",
                "article",
                ".detail",
                ".news-content",
                ".arc-body",
            ]

            for selector in content_selectors:
                elem = soup.select_one(selector)
                if elem:
                    content = elem.get_text()
                    if content and len(content.strip()) > 50:
                        break

            return {"title": full_title, "content": content.strip() if content else ""}
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"获取详情失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                time.sleep(1)
            else:
                print(f"获取详情失败 (已重试 {max_retries} 次): {e}")
                return {"title": "", "content": ""}


def check_file_exists(news_id, folder):
    """检查文件是否在指定文件夹存在"""
    file_path = os.path.join(folder, f"{news_id}.md")
    return os.path.exists(file_path)


def save_news_to_path(news_item, news_id, md_content, output_dir):
    """保存新闻到指定目录"""
    os.makedirs(output_dir, exist_ok=True)
    file_path = os.path.join(output_dir, f"{news_id}.md")

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    return file_path, True


def fetch_24hours_news(max_retries=3):
    """从数据源获取7×24小时新闻列表（支持重试）"""
    timestamp = int(time.time())
    data_url = f"http://stock.10jqka.com.cn/thsgd/ywjh.js?t={timestamp}"

    print(f"正在获取数据源: {data_url}")

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    for attempt in range(max_retries):
        try:
            resp = requests.get(data_url, headers=headers, timeout=10)
            break
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"获取数据源失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                time.sleep(1)
            else:
                print(f"获取数据源失败 (已重试 {max_retries} 次): {e}")
                return []
    # 尝试多种编码解码
    js_content = ""
    for enc in ['gbk', 'gb18030', 'utf-8', 'latin-1']:
        try:
            js_content = resp.content.decode(enc)
            break
        except UnicodeDecodeError:
            continue

    print(f"获取到 {len(js_content)} 字符数据")

    pub_date_match = re.search(r'pubDate:"([^"]+)"', js_content)
    if pub_date_match:
        print(f"数据源发布时间: {pub_date_match.group(1)}")

    start_marker = '"item":['
    start_idx = js_content.find(start_marker)
    if start_idx == -1:
        start_marker = 'item:['
        start_idx = js_content.find(start_marker)

    if start_idx != -1:
        start_idx += len(start_marker) - 1
        bracket_count = 1
        end_idx = start_idx + 1
        while end_idx < len(js_content) and bracket_count > 0:
            if js_content[end_idx] == '[':
                bracket_count += 1
            elif js_content[end_idx] == ']':
                bracket_count -= 1
            end_idx += 1

        if bracket_count == 0:
            json_str = js_content[start_idx:end_idx]
            json_str = re.sub(r"'([^']+)'", r'"\1"', json_str)
            json_str = re.sub(r'([{,])\s*(\w+):', r'\1"\2":', json_str)

            try:
                news_list = json.loads(json_str)
                print(f"成功解析 {len(news_list)} 条新闻")
                if news_list:
                    print(f"最新新闻时间: {news_list[0].get('pubDate', 'N/A')}")
                return news_list
            except json.JSONDecodeError as e:
                print(f"JSON 解析失败: {e}")

    return []


def fetch_yuanchuang_list(url, source_name, max_retries=3):
    """获取原创类新闻列表（支持重试）"""
    print(f"正在访问: {url}")

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    for attempt in range(max_retries):
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            # 直接使用原始字节让BeautifulSoup处理编码
            soup = BeautifulSoup(resp.content, 'html.parser')
            break
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"访问失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                time.sleep(1)
            else:
                print(f"访问失败 (已重试 {max_retries} 次): {e}")
                return []

    news_list = []
    items = soup.select(".list-con li")
    print(f"找到 {len(items)} 条新闻")

    for item in items:
        try:
            title_elem = item.select_one(".arc-title a")
            if not title_elem:
                continue

            title = title_elem.get("title", "").strip()
            link = title_elem.get("href", "").strip()

            time_elem = item.select_one(".arc-title span")
            pub_time = time_elem.get_text(strip=True) if time_elem else ""

            summary_elem = item.select_one(".arc-cont")
            summary = summary_elem.get_text(strip=True) if summary_elem else ""

            news_id = ""
            if link:
                match = re.search(r'/c(\d+)\.shtml', link)
                if match:
                    news_id = f"c{match.group(1)}"

            if title and link:
                news_list.append({
                    "id": news_id,
                    "title": title,
                    "url": link,
                    "time": pub_time,
                    "summary": summary,
                    "source": source_name
                })
        except Exception as e:
            print(f"解析条目失败: {e}")
            continue

    return news_list


def process_24hours_news_with_check(news_item, folder_name):
    """处理7×24小时新闻，先检查是否已存在"""
    url = news_item.get('url', '')
    news_id = ''

    if url:
        match = re.search(r'/c(\d+)\.shtml', url)
        if match:
            news_id = f"c{match.group(1)}"

    if not news_id:
        news_id = f"c{news_item.get('seq', '')}"

    # 检查是否已存在
    if check_file_exists(news_id, folder_name):
        print(f"  文件已存在，跳过: {news_id}")
        return news_id, None, False

    title = news_item.get('title', '无标题')
    summary = news_item.get('content', '')
    pub_date = news_item.get('pubDate', '')
    source = news_item.get('source', '')

    detail_content = ""
    if url:
        print(f"  正在获取详情: {news_id}")
        detail_result = fetch_news_detail(url)
        detail_content = detail_result.get("content", "")
        # 使用详情页的完整标题（如果有的话）
        if detail_result.get("title"):
            title = detail_result["title"]

    full_content = detail_content if detail_content else summary
    full_content = replace_newlines_with_period(full_content)

    md_content = f"# {title}\n\n"
    if pub_date:
        md_content += f"**发布时间**: {pub_date}\n\n"
    if source:
        md_content += f"**来源**: {source}\n\n"
    if url:
        md_content += f"**原文链接**: {url}\n\n"
    md_content += "---\n\n"
    md_content += f"{full_content}\n"

    return news_id, md_content, True


def process_yuanchuang_news_with_check(news_item, source_name, folder_name):
    """处理原创类新闻，先检查是否已存在"""
    news_id = news_item.get("id", "")
    if not news_id:
        news_id = f"news_{int(time.time())}"

    # 检查是否已存在
    if check_file_exists(news_id, folder_name):
        print(f"  文件已存在，跳过: {news_id}")
        return news_id, None, False

    title = news_item.get("title", "无标题")
    summary = news_item.get("summary", "")
    pub_time = news_item.get("time", "")
    url = news_item.get("url", "")

    detail_content = ""
    if url:
        print(f"  正在获取详情: {news_id}")
        detail_result = fetch_news_detail(url)
        detail_content = detail_result.get("content", "")
        # 使用详情页的完整标题（如果有的话）
        if detail_result.get("title"):
            title = detail_result["title"]

    full_content = detail_content if detail_content else summary
    full_content = replace_newlines_with_period(full_content)

    md_content = f"# {title}\n\n"
    if pub_time:
        md_content += f"**发布时间**: {pub_time}\n\n"
    md_content += f"**来源**: {source_name}\n\n"
    if url:
        md_content += f"**原文链接**: {url}\n\n"
    md_content += "---\n\n"
    md_content += f"{full_content}\n"

    return news_id, md_content, True


def process_news_source(news_list, processor, source_name, folder_name, unified_dir="news"):
    """处理新闻源并保存到两个位置"""
    saved_count = 0
    skipped_count = 0

    for i, news in enumerate(news_list, 1):
        print(f"\n[{i}/{len(news_list)}] 处理新闻...")
        try:
            if processor == "24hours":
                news_id, md_content, is_new = process_24hours_news_with_check(news, folder_name)
            else:
                news_id, md_content, is_new = process_yuanchuang_news_with_check(news, source_name, folder_name)

            # 仅当是新文件时才保存
            if is_new and md_content:
                save_news_to_path(news, news_id, md_content, folder_name)
                save_news_to_path(news, news_id, md_content, unified_dir)
                print(f"  已保存: {folder_name}/{news_id}.md 和 {unified_dir}/{news_id}.md")
                saved_count += 1
            else:
                print(f"  跳过，不保存到 news/")
                skipped_count += 1

        except Exception as e:
            print(f"  保存失败: {e}")

    return saved_count, skipped_count


def clear_news_folder(folder="news"):
    """清空指定文件夹中的所有 .md 文件"""
    if os.path.exists(folder):
        count = 0
        for filename in os.listdir(folder):
            if filename.endswith('.md'):
                file_path = os.path.join(folder, filename)
                try:
                    os.remove(file_path)
                    count += 1
                except Exception as e:
                    print(f"  删除失败 {filename}: {e}")
        print(f"已清空 {folder}/ 文件夹，删除了 {count} 个旧文件")


def _fetch_single_source(source_config):
    """
    获取单个新闻源的新闻（供线程池调用）

    Args:
        source_config: 包含新闻源配置的元组 (source_type, source_name, url, folder_name)

    Returns:
        tuple: (source_name, news_list, folder_name)
    """
    source_type, source_name, url, folder_name = source_config
    news_list = []

    print(f"\n[{source_name}] 开始爬取...")

    try:
        if source_type == "24hours":
            raw_news = fetch_24hours_news()
            if raw_news:
                for news in raw_news:
                    news_id, md_content, is_new = process_24hours_news_with_check(news, folder_name)
                    if is_new and md_content:
                        save_news_to_path(news, news_id, md_content, folder_name)
                        save_news_to_path(news, news_id, md_content, "news")
                        news_list.append({
                            "id": news_id,
                            "title": news.get('title', ''),
                            "content": news.get('content', ''),
                            "url": news.get('url', ''),
                            "time": news.get('pubDate', ''),
                            "source": news.get('source', ''),
                            "md_content": md_content
                        })
        else:
            raw_news = fetch_yuanchuang_list(url, source_name)
            if raw_news:
                for news in raw_news:
                    news_id, md_content, is_new = process_yuanchuang_news_with_check(news, source_name, folder_name)
                    if is_new and md_content:
                        save_news_to_path(news, news_id, md_content, folder_name)
                        save_news_to_path(news, news_id, md_content, "news")
                        news_list.append({
                            "id": news_id,
                            "title": news.get('title', ''),
                            "content": news.get('summary', ''),
                            "url": news.get('url', ''),
                            "time": news.get('time', ''),
                            "source": source_name,
                            "md_content": md_content
                        })

        print(f"[{source_name}] 完成，获取 {len(news_list)} 条新闻")
    except Exception as e:
        print(f"[{source_name}] 爬取失败: {e}")

    return source_name, news_list, folder_name


def fetch_all_news_sources(clear_news=True, max_workers=6):
    """
    并行获取所有新闻源的新闻

    Args:
        clear_news: 是否清空 news 文件夹
        max_workers: 最大并发线程数，默认6（6个新闻源）

    Returns:
        list: 所有新闻的列表，每条新闻包含 id, title, content, url, time, source 等字段
    """
    if clear_news:
        print("\n正在清空 news/ 文件夹...")
        clear_news_folder("news")

    # 定义所有新闻源配置
    source_configs = [
        ("24hours", "7×24小时要闻", "", "24hours_news"),
        ("yuanchuang", "同花顺原创", "https://yuanchuang.10jqka.com.cn/ycall_list/", "yuanchuang_news"),
        ("yuanchuang", "同花顺涨停解密", "https://yuanchuang.10jqka.com.cn/mrnxgg_list/", "mrnxgg_news"),
        ("yuanchuang", "同花顺快评", "https://yuanchuang.10jqka.com.cn/djkuaiping_list/", "djkuaiping_news"),
        ("yuanchuang", "同花顺公司互动", "https://yuanchuang.10jqka.com.cn/djgshd_list/", "djgshd_news"),
        ("yuanchuang", "同花顺公告解读", "https://yuanchuang.10jqka.com.cn/djggjd_list/", "djggjd_news"),
    ]

    all_news = []

    print(f"\n开始并行爬取 {len(source_configs)} 个新闻源 (最大并发数: {max_workers})")
    print("=" * 70)

    # 使用线程池并行爬取
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_source = {
            executor.submit(_fetch_single_source, config): config[1]
            for config in source_configs
        }

        for future in as_completed(future_to_source):
            source_name = future_to_source[future]
            try:
                name, news_list, folder = future.result()
                all_news.extend(news_list)
            except Exception as e:
                print(f"[{source_name}] 线程执行异常: {e}")

    print("=" * 70)
    return all_news


def main():
    print("=" * 70)
    print("同花顺新闻爬虫 - 整合版")
    print("=" * 70)

    all_news = fetch_all_news_sources(clear_news=True)

    print("\n" + "=" * 70)
    print(f"全部完成! 共获取 {len(all_news)} 条新新闻")
    print("=" * 70)


if __name__ == "__main__":
    main()
