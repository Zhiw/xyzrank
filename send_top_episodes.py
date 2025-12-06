import json
import requests
import sys


def load_episodes(file_path):
    """加载剧集数据"""
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("data", {}).get("episodes", [])


def filter_and_sort_episodes(episodes, exclude_genres=None, top_n=20):
    """
    过滤并排序剧集
    - exclude_genres: 要排除的类型列表
    - top_n: 返回前N个
    """
    if exclude_genres is None:
        exclude_genres = ["喜剧"]

    # 过滤掉指定类型
    filtered = [
        ep for ep in episodes
        if ep.get("primaryGenreName") not in exclude_genres
    ]

    # 按播放量降序排序
    sorted_episodes = sorted(filtered, key=lambda x: x.get("playCount", 0), reverse=True)

    return sorted_episodes[:top_n]


def format_episode_for_feishu(episode, rank):
    """格式化单个剧集信息"""
    play_count = episode.get("playCount", 0)
    if play_count >= 10000:
        play_count_str = f"{play_count / 10000:.1f}万"
    else:
        play_count_str = str(play_count)

    return {
        "rank": rank,
        "title": episode.get("title", ""),
        "podcast": episode.get("podcastName", ""),
        "playCount": play_count_str,
        "genre": episode.get("primaryGenreName", ""),
        "link": episode.get("link", ""),
    }


def build_feishu_message(episodes, title, top_n):
    """构建飞书消息卡片"""
    content_lines = []

    for i, ep in enumerate(episodes, 1):
        formatted = format_episode_for_feishu(ep, i)
        line = f"**{i}. {formatted['title']}**\n" \
               f"   播客: {formatted['podcast']} | 播放量: {formatted['playCount']} | 类型: {formatted['genre']}\n" \
               f"   [收听链接]({formatted['link']})\n"
        content_lines.append(line)

    message = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": title
                },
                "template": "blue"
            },
            "elements": [
                {
                    "tag": "markdown",
                    "content": "\n".join(content_lines)
                }
            ]
        }
    }

    return message


def send_to_feishu(webhook_url, message):
    """发送消息到飞书 webhook"""
    headers = {"Content-Type": "application/json"}

    response = requests.post(webhook_url, json=message, headers=headers, timeout=10)
    response.raise_for_status()

    result = response.json()
    if result.get("code") == 0:
        print("消息发送成功!")
        return True
    else:
        print(f"消息发送失败: {result}")
        return False


def process_and_send(webhook_url, file_path, title, top_n=20):
    """处理单个数据文件并发送"""
    print(f"\n{'='*60}")
    print(f"处理: {title}")
    print(f"{'='*60}")

    # 加载数据
    print(f"正在加载数据: {file_path}")
    episodes = load_episodes(file_path)
    print(f"共加载 {len(episodes)} 个剧集")

    # 过滤和排序
    print(f"正在筛选播放量前{top_n}（过滤喜剧类型）...")
    top_episodes = filter_and_sort_episodes(episodes, exclude_genres=["喜剧"], top_n=top_n)
    print(f"筛选出 {len(top_episodes)} 个剧集")

    # 打印预览
    print("\n预览:")
    print("-" * 60)
    for i, ep in enumerate(top_episodes, 1):
        formatted = format_episode_for_feishu(ep, i)
        print(f"{i}. {formatted['title'][:40]}...")
        print(f"   {formatted['podcast']} | {formatted['playCount']} | {formatted['genre']}")
    print("-" * 60)

    # 构建消息
    message = build_feishu_message(top_episodes, title, top_n)

    # 发送到飞书
    print("\n正在发送到飞书...")
    return send_to_feishu(webhook_url, message)


def main():
    # 飞书 webhook URL
    webhook_url = sys.argv[1] if len(sys.argv) > 1 else None

    if not webhook_url:
        print("用法: python send_top_episodes.py <飞书webhook地址>")
        print("示例: python send_top_episodes.py https://open.feishu.cn/open-apis/bot/v2/hook/xxx")
        sys.exit(1)

    # 定义要处理的数据源
    data_sources = [
        {
            "file": "hot_episodes.json",
            "title": "🎧 小宇宙热门播客 Top 20",
        },
        {
            "file": "hot_episodes_new.json",
            "title": "🌟 小宇宙新锐节目 Top 20",
        },
    ]

    # 处理每个数据源
    success_count = 0
    for source in data_sources:
        try:
            if process_and_send(webhook_url, source["file"], source["title"], top_n=20):
                success_count += 1
        except FileNotFoundError:
            print(f"文件不存在: {source['file']}")
        except Exception as e:
            print(f"处理 {source['file']} 时出错: {e}")

    print(f"\n完成! 成功发送 {success_count}/{len(data_sources)} 条消息")


if __name__ == "__main__":
    main()
