#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
xisohi GitHub Profile 自研主页生成器（不依赖任何第三方模板/服务）

数据源: GitHub REST API + GraphQL（贡献日历）
输出  : output/*.svg，由 .github/workflows/main.yml 定时重绘并提交

用法:
  python scripts/build.py           # 真实模式（GITHUB_TOKEN 存在时画热力图/贪吃蛇）
  python scripts/build.py --mock    # 模拟数据模式（本地验证渲染逻辑）
"""
import argparse
import datetime
import json
import os
import sys
import urllib.request

USER = "xisohi"
API = "https://api.github.com"
TOKEN = os.environ.get("GITHUB_TOKEN", "")

# ---------- 基础工具 ----------

def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


def http(path, method="GET", body=None):
    req = urllib.request.Request(path if path.startswith("http") else API + path,
                                 method=method)
    req.add_header("User-Agent", "xisohi-profile-builder")
    req.add_header("Accept", "application/vnd.github+json")
    if TOKEN:
        req.add_header("Authorization", "Bearer " + TOKEN)
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, data, timeout=30) as resp:
            return json.load(resp)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def fetch_user_repos():
    repos, page = [], 1
    while True:
        batch = http("/users/%s/repos?per_page=100&page=%d&type=owner"
                     % (USER, page))
        if not batch:
            break
        repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return repos


def fetch_contributions():
    """GraphQL 贡献日历；无 token 时返回 None（本地降级）。"""
    if not TOKEN:
        return None
    now = datetime.datetime.now(datetime.timezone.utc)
    frm = now - datetime.timedelta(days=364)
    query = (
        "query($from: DateTime!, $to: DateTime!){"
        " user(login:\"%s\"){"
        "  contributionsCollection(from:$from,to:$to){"
        "   contributionCalendar{ totalContributions"
        "    weeks{ contributionDays{ date contributionCount level } }"
        " } } } }" % USER)
    try:
        data = http("https://api.github.com/graphql", "POST",
                    {"query": query,
                     "variables": {"from": frm.isoformat(),
                                   "to": now.isoformat()}})
        return data["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    except Exception as exc:  # noqa: BLE001
        print("[warn] GraphQL 贡献数据获取失败: %s" % exc)
        return None


# ---------- SVG 渲染 ----------

BG = "#0d1117"
CARD = "#161b22"
FG = "#e6edf3"
MUT = "#8b949e"
GREEN = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]
ORANGE = "#f0883e"
ACCENT = "#58a6ff"


def svg_head(w, h, extra=""):
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
            'viewBox="0 0 %d %d">%s'
            '<rect x="0" y="0" width="%d" height="%d" fill="%s" rx="10"/>'
            % (w, h, w, h, extra, w, h, BG))


def svg_tail():
    return "</svg>"


def render_stats(user, repos):
    stars = sum(r["stargazers_count"] for r in repos)
    forks = sum(r["forks_count"] for r in repos)
    cells = [
        ("Stars", stars),
        ("Repos", len(repos)),
        ("Forks", forks),
        ("Followers", user.get("followers", 0)),
    ]
    w, h = 520, 120
    body = ['<text x="20" y="26" font-size="13" fill="%s" '
            'font-family="Segoe UI,Arial">%s 的 GitHub 数据</text>'
            % (MUT, esc(USER))]
    cw = 116
    for i, (label, val) in enumerate(cells):
        x = 20 + i * (cw + 6)
        body.append('<rect x="%d" y="40" width="%d" height="62" rx="8" fill="%s"/>'
                    % (x, cw, CARD))
        body.append('<text x="%d" y="66" font-size="20" font-weight="bold" '
                    'fill="%s" font-family="Segoe UI,Arial">%s</text>'
                    % (x + 12, ACCENT if label != "Stars" else GREEN[4],
                       "{:,}".format(val)))
        body.append('<text x="%d" y="90" font-size="12" fill="%s" '
                    'font-family="Segoe UI,Arial">%s</text>'
                    % (x + 12, MUT, esc(label)))
    return svg_head(w, h) + "".join(body) + svg_tail()


def _grid_days(cal):
    """把 contributionCalendar 展平成 (date,count,level) 列表。"""
    days = []
    for wk in cal["weeks"]:
        for d in wk["contributionDays"]:
            days.append(d)
    return days


def render_heatmap(cal):
    days = _grid_days(cal)
    cols, rows = 53, 7
    pad_x, pad_y, cell, gap = 20, 44, 14, 3
    pitch = cell + gap
    w = pad_x * 2 + cols * pitch
    h = pad_y + rows * pitch + 30
    body = []
    body.append('<text x="20" y="26" font-size="14" fill="%s" '
                'font-family="Segoe UI,Arial">过去一年贡献（共 %d 次）</text>'
                % (FG, cal.get("totalContributions", 0)))
    for row, label in enumerate(["日", "一", "二", "三", "四", "五", "六"]):
        body.append('<text x="%d" y="%d" font-size="10" fill="%s" '
                    'font-family="Segoe UI,Arial">%s</text>'
                    % (6, pad_y + row * pitch + 12, MUT, label))
    for i, d in enumerate(days):
        col = i // rows
        row = i % rows
        x = pad_x + col * pitch
        y = pad_y + row * pitch
        level = min(int(d.get("level", 0)), 4)
        body.append('<rect x="%d" y="%d" width="%d" height="%d" rx="3" '
                    'fill="%s"/>' % (x, y, cell, cell, GREEN[level]))
    lx = w - 150
    body.append('<text x="%d" y="%d" font-size="11" fill="%s" '
                'font-family="Segoe UI,Arial">少</text>' % (lx - 6, h - 12, MUT))
    for lv in range(5):
        body.append('<rect x="%d" y="%d" width="11" height="11" rx="3" '
                    'fill="%s"/>' % (lx + 14 + lv * 17, h - 19, GREEN[lv]))
    body.append('<text x="%d" y="%d" font-size="11" fill="%s" '
                'font-family="Segoe UI,Arial">多</text>'
                % (lx + 14 + 5 * 17, h - 12, MUT))
    return svg_head(w, h) + "".join(body) + svg_tail()


def render_langs(repos):
    lang_cnt = {}
    for r in repos:
        lang = r.get("language")
        if lang:
            lang_cnt[lang] = lang_cnt.get(lang, 0) + 1
    if not lang_cnt:
        return '<svg xmlns="http://www.w3.org/2000/svg" width="520" ' \
               'height="60"><rect width="520" height="60" fill="%s"/>' \
               '<text x="20" y="38" fill="%s" font-size="14">暂无语言数据</text>' \
               '</svg>' % (BG, FG)
    items = sorted(lang_cnt.items(), key=lambda kv: -kv[1])[:8]
    total = sum(lang_cnt.values())
    w, h = 520, 30 + len(items) * 30
    body = ['<text x="20" y="26" font-size="13" fill="%s" '
            'font-family="Segoe UI,Arial">仓库语言分布（按仓库数）</text>' % MUT]
    palette = ["#f05138", "#3776ab", "#f1e05a", "#563d7c", "#2b7489",
               "#3572A5", "#b07219", "#89e051"]
    bar_max = items[0][1]
    for i, (lang, cnt) in enumerate(items):
        y = 44 + i * 30
        pct = cnt * 100.0 / total
        bw = int(330 * cnt / bar_max)
        body.append('<rect x="20" y="%d" width="10" height="10" rx="2" '
                    'fill="%s"/>' % (y, palette[i % len(palette)]))
        body.append('<text x="38" y="%d" font-size="12" fill="%s" '
                    'font-family="Consolas,Segoe UI">%s</text>'
                    % (y + 10, FG, esc(lang)))
        body.append('<rect x="170" y="%d" width="%d" height="10" rx="3" '
                    'fill="%s" opacity="0.85"/>' % (y, bw, palette[i % len(palette)]))
        body.append('<text x="%d" y="%d" font-size="11" fill="%s" '
                    'font-family="Segoe UI,Arial">%d 个 · %.0f%%</text>'
                    % (170 + bw + 10, y + 10, MUT, cnt, pct))
    return svg_head(w, h) + "".join(body) + svg_tail()


def _rel_time(ts):
    try:
        dt = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:  # noqa: BLE001
        return ts[:10]
    diff = datetime.datetime.now(datetime.timezone.utc) - dt
    secs = int(diff.total_seconds())
    if secs < 3600:
        return "%d 分钟前" % max(secs // 60, 1)
    if secs < 86400:
        return "%d 小时前" % (secs // 3600)
    if secs < 86400 * 30:
        return "%d 天前" % (secs // 86400)
    return ts[:10]


def _event_text(e):
    t = e.get("type", "")
    repo = (e.get("repo") or {}).get("name", "")
    if t == "PushEvent":
        c = len((e.get("payload") or {}).get("commits", []))
        return "推送 %d 个提交到 %s" % (c, repo)
    if t == "CreateEvent":
        p = e.get("payload") or {}
        return "创建 %s %s @ %s" % (p.get("ref_type", ""), p.get("ref", ""), repo)
    if t == "StarEvent":
        return "Star 了 %s" % repo
    if t == "ForkEvent":
        return "Fork 了 %s" % repo
    if t == "IssueCommentEvent":
        return "评论了 %s 的 Issue" % repo
    if t == "PullRequestEvent":
        return "PR 了 %s" % repo
    return "%s @ %s" % (t.replace("Event", ""), repo)


def render_activity(events):
    w, h = 540, 30 + len(events) * 26
    body = ['<text x="20" y="26" font-size="13" fill="%s" '
            'font-family="Segoe UI,Arial">最近动态</text>' % MUT]
    for i, e in enumerate(events):
        y = 44 + i * 26
        txt = _event_text(e)
        if len(txt) > 40:
            txt = txt[:39] + "…"
        body.append('<circle cx="24" cy="%d" r="3" fill="%s"/>' % (y - 4, ACCENT))
        body.append('<text x="36" y="%d" font-size="12" fill="%s" '
                    'font-family="Segoe UI,Arial">%s</text>' % (y, FG, esc(txt)))
        ts = _rel_time(e.get("created_at", ""))
        body.append('<text x="%d" y="%d" font-size="10" fill="%s" '
                    'text-anchor="end" font-family="Segoe UI,Arial">%s</text>'
                    % (w - 20, y, MUT, ts))
    return svg_head(w, h) + "".join(body) + svg_tail()


def _snake_path(cols, rows, pad_x, pad_y, pitch):
    """S 形折返路径，覆盖每个格子中心。"""
    pts = []
    for row in range(rows):
        rng = range(cols) if row % 2 == 0 else range(cols - 1, -1, -1)
        for col in rng:
            pts.append((pad_x + col * pitch, pad_y + row * pitch))
    d = "M %d %d" % pts[0]
    for p in pts[1:]:
        d += " L %d %d" % p
    return d


def render_snake(cal):
    days = _grid_days(cal)
    cols, rows = 53, 7
    pad_x, pad_y, cell, gap = 20, 44, 14, 3
    pitch = cell + gap
    w = pad_x * 2 + cols * pitch
    h = pad_y + rows * pitch + 26
    body = []
    body.append('<text x="20" y="26" font-size="14" fill="%s" '
                'font-family="Segoe UI,Arial">贡献贪吃蛇（吃掉的绿点 = 有贡献的日子）</text>' % FG)
    for i, d in enumerate(days):
        col, row = i // rows, i % rows
        x = pad_x + col * pitch
        y = pad_y + row * pitch
        lv = min(int(d.get("level", 0)), 4)
        body.append('<rect x="%d" y="%d" width="%d" height="%d" rx="3" '
                    'fill="%s"/>' % (x, y, cell, cell, GREEN[lv]))
        if lv >= 3:
            body.append('<circle cx="%d" cy="%d" r="3.5" fill="%s"/>'
                        % (x + cell / 2, y + cell / 2, ORANGE))
    path = _snake_path(cols, rows, pad_x + cell / 2, pad_y + cell / 2, pitch)
    snake_color = ["#39d353", "#2ea44f", "#238636", "#1f7a37", "#1a6e30", "#16622a"]
    for i in range(6):
        r = 7 - i
        begin = "%.2fs" % (i * 0.14)
        body.append('<circle r="%d" fill="%s" opacity="%s">'
                    '<animateMotion dur="12s" begin="%s" repeatCount="indefinite" '
                    'path="%s"/></circle>' % (r, snake_color[i], max(0.85 - i * 0.1, 0.25), begin, path))
    body.append('<circle r="8" fill="#f6f8fa" stroke="#39d353" stroke-width="2">'
                '<animateMotion dur="12s" begin="0s" repeatCount="indefinite" '
                'path="%s"/></circle>' % path)
    return svg_head(w, h) + "".join(body) + svg_tail()


# ---------- 模拟数据（本地验证渲染） ----------

def mock_calendar():
    weeks, day = [], datetime.date(2025, 11, 3)
    for _ in range(53):
        wk = []
        for _r in range(7):
            count = (day.day * 7 + day.month) % 9
            level = 0 if count < 3 else (1 if count < 5 else (2 if count < 7 else (3 if count < 8 else 4)))
            wk.append({"date": day.isoformat(), "contributionCount": count, "level": level})
            day += datetime.timedelta(days=1)
        weeks.append({"contributionDays": wk})
    total = sum(d["contributionCount"] for wk in weeks for d in wk["contributionDays"])
    return {"totalContributions": total, "weeks": weeks}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true", help="用模拟数据渲染")
    args = ap.parse_args()

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "output")
    out = os.path.abspath(out)
    os.makedirs(out, exist_ok=True)

    if args.mock:
        print("[mock] 使用模拟数据渲染全部模块")
        user = {"followers": 123}
        repos = []
        for i, lang in enumerate(["Java", "Kotlin", "Python", "Shell", "C", "HTML", "CSS", "Vue"]):
            repos.append({"stargazers_count": 200 - i * 20, "forks_count": 50 - i * 4,
                          "language": lang, "name": "repo%d" % i})
        events = []
        for i in range(10):
            events.append({"type": ["PushEvent", "StarEvent", "CreateEvent", "ForkEvent", "IssueCommentEvent"][i % 5],
                           "repo": {"name": "xisohi/project%d" % i},
                           "created_at": (datetime.datetime.now(datetime.timezone.utc) -
                                          datetime.timedelta(hours=i * 6)).isoformat(),
                           "payload": {"commits": [{}] * (i % 4), "ref_type": "repository", "ref": "demo"}})
        cal = mock_calendar()
    else:
        print("[live] 拉取 GitHub 数据（用户: %s）" % USER)
        user = http("/users/" + USER)
        repos = fetch_user_repos()
        cal = fetch_contributions()
        try:
            events = http("/users/%s/events/public?per_page=10" % USER)
        except Exception as exc:  # noqa: BLE001
            print("[warn] 最近动态获取失败: %s" % exc)
            events = []
        print("  repos=%d stars=%d forks=%d" %
              (len(repos), sum(r["stargazers_count"] for r in repos),
               sum(r["forks_count"] for r in repos)))
        print("  贡献日历: %s" % ("已获取" if cal else "未获取（无 GITHUB_TOKEN，跳过热力图/贪吃蛇）"))

    files = {
        "stats.svg": render_stats(user, repos),
        "langs.svg": render_langs(repos),
        "activity.svg": render_activity(events),
    }
    if cal:
        files["heatmap.svg"] = render_heatmap(cal)
        files["snake.svg"] = render_snake(cal)
    else:
        for name in ("heatmap.svg", "snake.svg"):
            files[name] = ('<svg xmlns="http://www.w3.org/2000/svg" width="520" '
                           'height="60"><rect width="520" height="60" fill="%s"/>'
                           '<text x="20" y="38" fill="%s" font-size="14">'
                           '配置 GITHUB_TOKEN 后由 Actions 自动生成</text></svg>'
                           % (BG, MUT))

    for name, content in files.items():
        with open(os.path.join(out, name), "w", encoding="utf-8") as f:
            f.write(content)
        print("  ✓ output/%s (%d bytes)" % (name, len(content)))
    print("[done] 全部生成完毕 → %s" % out)


if __name__ == "__main__":
    sys.exit(main())
