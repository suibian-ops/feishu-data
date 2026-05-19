# -*- coding: utf-8 -*-
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

"""
样稿制作周报推送脚本
每周一早上 9:00 自动推送上周 + 本月累计数据到钉钉群
"""
import os
import json
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone

BEIJING_TZ = timezone(timedelta(hours=8))


# ==================== 配置 ====================
DINGTALK_WEBHOOK = os.environ.get(
    "DINGTALK_WEBHOOK",
    "https://oapi.dingtalk.com/robot/send?access_token=fb6fe723f767944a73851c9de7d60cf5f985c3070af3d12b57024f2bf0989a7c"
)
DATA_URL = "https://raw.githubusercontent.com/suibian-ops/feishu-data/main/sample_production.json"


def get_date_range():
    """计算上周和本月的日期范围（北京时间）"""
    now = datetime.now(BEIJING_TZ)

    # 本周一（时间清零）
    this_monday = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)

    # 上周区间：上周一 ~ 上周日
    last_monday = this_monday - timedelta(days=7)
    last_sunday = this_monday - timedelta(days=1)

    # 本月区间：本月1号 ~ 今天
    this_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    return {
        "last_monday": last_monday.strftime("%Y-%m-%d"),
        "last_sunday": last_sunday.strftime("%Y-%m-%d"),
        "this_month_start": this_month_start.strftime("%Y-%m-%d"),
        "today": now.strftime("%Y-%m-%d"),
        "last_monday_dt": last_monday,
        "last_sunday_dt": last_sunday,
        "this_month_start_dt": this_month_start,
        "now_dt": now,
    }


def parse_date(date_str):
    """解析日期字符串为 datetime 对象（北京时间）"""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str[:10], "%Y-%m-%d").replace(
            tzinfo=BEIJING_TZ
        )
    except:
        return None


def load_data():
    """从 GitHub 加载 JSON 数据"""
    try:
        req = urllib.request.Request(DATA_URL, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"加载数据失败: {e}")
        return []


def calculate_stats(data, start_dt, end_dt):
    """按制作人统计指定日期范围内的样稿数量（求和样稿数量字段）"""
    stats = {}
    for record in data:
        date_str = record.get("deliverDate") or record.get("交付时间") or ""
        record_date = parse_date(date_str)
        if not record_date:
            continue
        if start_dt <= record_date <= end_dt:
            maker = record.get("maker") or record.get("制作人") or "未知"
            sample_count = record.get("sampleCount") or 0
            # 如果 sampleCount 是字符串，尝试转 int
            if isinstance(sample_count, str):
                try:
                    sample_count = int(sample_count)
                except ValueError:
                    sample_count = 0
            stats[maker] = stats.get(maker, 0) + sample_count
    return stats


def build_report(last_stats, month_stats, date_range):
    """生成钉钉消息文本"""
    last_total = sum(last_stats.values())
    month_total = sum(month_stats.values())

    # 上周汇总（按数量降序排列）
    last_lines = []
    for maker, count in sorted(last_stats.items(), key=lambda x: -x[1]):
        last_lines.append(f"• {maker} - {count} 个")

    # 本月累计（按数量降序排列）
    month_lines = []
    for maker, count in sorted(month_stats.items(), key=lambda x: -x[1]):
        month_lines.append(f"• {maker} - {count} 个")

    # 拼接消息
    lines = [
        "🌿 样稿制作周报",
        "",
        f"📊 上周汇总（{date_range['last_monday']}-{date_range['last_sunday']}）",
        f"• 总个数：{last_total} 个",
    ]
    lines.extend(last_lines)
    lines.extend(["", f"📈 本月累计（{date_range['this_month_start']}至今）"])
    lines.append(f"• 总个数：{month_total} 个")
    lines.extend(month_lines)

    return "\n".join(lines)


def send_dingtalk(message):
    """发送消息到钉钉群"""
    payload = json.dumps({
        "msgtype": "text",
        "text": {"content": message}
    }).encode("utf-8")

    req = urllib.request.Request(
        DINGTALK_WEBHOOK,
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            if result.get("errcode") == 0:
                print("✅ 钉钉消息发送成功！")
                return True
            else:
                print(f"❌ 钉钉返回错误: {result}")
                return False
    except Exception as e:
        print(f"❌ 发送失败: {e}")
        return False


def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始生成样稿制作周报...")

    # 计算日期范围
    date_range = get_date_range()
    print(f"  上周区间：{date_range['last_monday']} ~ {date_range['last_sunday']}")
    print(f"  本月区间：{date_range['this_month_start']} ~ {date_range['today']}")

    # 加载数据
    data = load_data()
    print(f"  共加载 {len(data)} 条记录")

    if not data:
        print("❌ 没有数据，退出")
        return

    # 计算统计
    last_stats = calculate_stats(
        data,
        date_range["last_monday_dt"],
        date_range["last_sunday_dt"] + timedelta(hours=23, minutes=59, seconds=59)
    )
    month_stats = calculate_stats(
        data,
        date_range["this_month_start_dt"],
        date_range["now_dt"]
    )

    print(f"  上周：{sum(last_stats.values())} 个，制作人 {len(last_stats)} 人")
    print(f"  本月：{sum(month_stats.values())} 个，制作人 {len(month_stats)} 人")

    # 生成报告
    report = build_report(last_stats, month_stats, date_range)
    print("\n--- 报告内容 ---")
    try:
        print(report)
    except UnicodeEncodeError:
        print(report.encode("utf-8", errors="replace").decode("utf-8", errors="replace"))
    print("--- 报告结束 ---\n")

    # 发送到钉钉（关键词：样稿 已包含在标题中）
    send_dingtalk(report)


if __name__ == "__main__":
    main()
