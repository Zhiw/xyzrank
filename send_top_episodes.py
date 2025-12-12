import json
import subprocess
import requests
import sys


def get_last_commit_content(file_path):
    """获取上次提交时的文件内容"""
    try:
        result = subprocess.run(
            ["git", "show", f"HEAD:{file_path}"],
            capture_output=True,
            text=True,
            check=True
        )
        return json.loads(result.stdout)
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return None


def get_top_list_set(episodes, exclude_genres, top_n):
    """获取 Top N 列表的集合（标题+播客名）"""
    filtered = [
        ep for ep in episodes
        if ep.get("primaryGenreName") not in exclude_genres
    ]
    sorted_eps = sorted(filtered, key=lambda x: x.get("playCount", 0), reverse=True)[:top_n]
    return set((ep.get("title"), ep.get("podcastName")) for ep in sorted_eps)


def get_new_episodes(file_path, exclude_genres, top_n):
    """获取新增的播客列表"""
    # 获取当前文件内容
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            current_data = json.load(f)
        current_episodes = current_data.get("data", {}).get("episodes", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return None  # 文件不存在或解析失败

    # 获取上次提交的内容
    last_data = get_last_commit_content(file_path)
    if not last_data:
        return None  # 无法获取上次内容，返回全部

    last_episodes = last_data.get("data", {}).get("episodes", [])

    # 获取当前和上次的 Top N 集合
    current_set = get_top_list_set(current_episodes, exclude_genres, top_n)
    last_set = get_top_list_set(last_episodes, exclude_genres, top_n)

    # 找出新增的（在当前列表中但不在上次列表中）
    new_keys = current_set - last_set

    if not new_keys:
        return []  # 没有新增

    # 返回新增的完整播客信息
    filtered = [
        ep for ep in current_episodes
        if ep.get("primaryGenreName") not in exclude_genres
    ]
    sorted_eps = sorted(filtered, key=lambda x: x.get("playCount", 0), reverse=True)[:top_n]

    return [ep for ep in sorted_eps if (ep.get("title"), ep.get("podcastName")) in new_keys]


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


def build_feishu_message(episodes, title):
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
    """处理单个数据文件并发送（只发送新增的播客）"""
    exclude_genres = ["喜剧"]

    print(f"\n{'='*60}")
    print(f"处理: {title}")
    print(f"{'='*60}")

    # 获取新增的播客
    new_episodes = get_new_episodes(file_path, exclude_genres, top_n)

    if new_episodes is None:
        # 无法比较（首次运行或 git 错误），发送完整列表
        print("无法获取历史数据，发送完整列表")
        episodes = load_episodes(file_path)
        new_episodes = filter_and_sort_episodes(episodes, exclude_genres=exclude_genres, top_n=top_n)
    elif len(new_episodes) == 0:
        print("没有新增播客，跳过发送")
        return None

    print(f"发现 {len(new_episodes)} 个新增播客")

    # 打印预览
    print("\n新增播客预览:")
    print("-" * 60)
    for i, ep in enumerate(new_episodes, 1):
        formatted = format_episode_for_feishu(ep, i)
        print(f"{i}. {formatted['title'][:40]}...")
        print(f"   {formatted['podcast']} | {formatted['playCount']} | {formatted['genre']}")
    print("-" * 60)

    # 构建消息（标题加上"新增"标识）
    msg_title = f"{title}（新增 {len(new_episodes)} 个）"
    message = build_feishu_message(new_episodes, msg_title)

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
    skip_count = 0
    for source in data_sources:
        try:
            result = process_and_send(webhook_url, source["file"], source["title"], top_n=20)
            if result is True:
                success_count += 1
            elif result is None:
                skip_count += 1
        except FileNotFoundError:
            print(f"文件不存在: {source['file']}")
        except Exception as e:
            print(f"处理 {source['file']} 时出错: {e}")

    print(f"\n完成! 发送 {success_count} 条，跳过 {skip_count} 条（无新增）")


if __name__ == "__main__":
    main()
