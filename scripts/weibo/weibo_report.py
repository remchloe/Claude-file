# -*- coding: utf-8 -*-
"""微博博主帖子整理工具

用法:
    python weibo_report.py "博主昵称" [起始日期 YYYY-MM-DD]

示例:
    python weibo_report.py "王虎的舰桥" 2026-07-21

默认抓取最近 60 天。输出到 reports/weibo/<博主名>_微博报告/，包含:
    <博主名>_<起>-<止>.md / .html   整理报告（含配图、互动数据、原文链接）
    images/                          配图（本地化，规避微博图床防盗链）

抓取前需先运行 wb_login.py 完成扫码登录。

环境变量:
    WEIBO_PROFILE  登录态目录（默认 ~/weibo_profile，含敏感凭证，勿入库）
    WEIBO_OUTDIR   输出目录（默认 仓库 reports/weibo/）
"""
import sys, os, re, json, time, html as _html, datetime, collections
import urllib.request
import concurrent.futures as cf
from playwright.sync_api import sync_playwright

PROFILE = os.environ.get("WEIBO_PROFILE",
                         os.path.join(os.path.expanduser("~"), "weibo_profile"))
OUTDIR = os.environ.get("WEIBO_OUTDIR",
                        os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "..", "..", "reports", "weibo"))
H = {"Referer": "https://m.weibo.cn/", "X-Requested-With": "XMLHttpRequest",
     "MWeibo-Pwa": "1",
     "User-Agent": ("Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 "
                    "Mobile/15E148 Safari/604.1")}

def log(m):
    print("[%s] %s" % (datetime.datetime.now().strftime("%H:%M:%S"), m), flush=True)

def parse_dt(s):
    try:    return datetime.datetime.strptime(s, "%a %b %d %H:%M:%S %z %Y").replace(tzinfo=None)
    except Exception: return None

def clean(h):
    if not h: return ""
    h = h.replace("<br />", chr(10)).replace("<br/>", chr(10)).replace("<br>", chr(10))
    h = re.sub(r'<span class="url-icon">\s*<img[^>]*alt="([^"]*)"[^>]*>\s*</span>', r'\1', h)
    h = re.sub(r'<img[^>]*alt="([^"]*)"[^>]*>', r'\1', h)
    h = re.sub(r'<a[^>]*>(.*?)</a>', r'\1', h, flags=re.S)
    h = re.sub(r'<[^>]+>', '', h)
    h = _html.unescape(h)
    return re.sub(r'\n{3,}', chr(10)+chr(10), h).strip()

def search_uid(ctx, name):
    import urllib.parse
    q = urllib.parse.quote(name)
    url = ("https://m.weibo.cn/api/container/getIndex?containerid=100103type%3D3%26q%3D"
           + q + "&page_type=searchall")
    r = ctx.request.get(url, headers=H, timeout=25000)
    j = r.json(); res = []
    for c in j.get("data", {}).get("cards", []):
        for u in (c.get("card_group") or []):
            ui = u.get("user")
            if ui: res.append((ui.get("id"), ui.get("screen_name"), ui.get("followers_count"), ui.get("verified_reason")))
    return res

def fetch_posts(ctx, uid, start):
    posts, seen, page, stop = [], set(), 1, False
    while page <= 200 and not stop:
        u = ("https://m.weibo.cn/api/container/getIndex?type=uid&value=%s"
             "&containerid=107603%s&page=%d" % (uid, uid, page))
        try:
            mb = [c["mblog"] for c in ctx.request.get(u, headers=H, timeout=30000).json()
                  .get("data", {}).get("cards", []) if c.get("mblog")]
        except Exception as e:
            log("page %d err %s, retry" % (page, e)); time.sleep(6); continue
        if not mb: break
        dts = [parse_dt(m.get("created_at") or "") for m in mb]
        pinned = 0 if (page == 1 and len(dts) >= 2 and dts[0] and dts[1]
                       and (dts[1]-dts[0]).days > 30) else None
        oldest = None
        for idx, m in enumerate(mb):
            if str(m.get("id")) in seen: continue
            seen.add(str(m.get("id")))
            dt = parse_dt(m.get("created_at") or "")
            if dt and oldest is None and idx != pinned: oldest = dt
            if dt and dt < start:
                if idx != pinned: stop = True
                continue
            m["_dt"] = dt.strftime("%Y-%m-%d %H:%M:%S") if dt else ""
            posts.append(m)
        log("page %d: +%d, oldest %s, total %d" % (page, len(posts), oldest, len(posts)))
        if oldest and oldest < start: stop = True
        page += 1; time.sleep(2.5)
    return posts

def fetch_long(ctx, posts):
    t = [m for m in posts if m.get("isLongText")]
    log("long texts: %d" % len(t)); ok = 0
    for m in t:
        try:
            d = (ctx.request.get("https://m.weibo.cn/statuses/extend?id=%s" % m["id"],
                                 headers=H, timeout=30000).json().get("data") or {})
            lt = d.get("longTextContent") or d.get("longText")
            if lt: m["long_text"] = lt; ok += 1
        except Exception: pass
        time.sleep(1.2)
    log("long texts fetched: %d" % ok)

def download_images(posts, dst):
    os.makedirs(dst, exist_ok=True)
    tasks = {}
    for m in posts:
        for p in (m.get("pics") or []):
            u = (p.get("large") or p.get("original") or p).get("url")
            if u: tasks[u.rsplit("/", 1)[-1]] = re.sub(r'sinaimg\.cn/\w+/', 'sinaimg.cn/bmiddle/', u)
    log("images: %d" % len(tasks))
    def get(it):
        base, url = it; fp = os.path.join(dst, base)
        if os.path.exists(fp) and os.path.getsize(fp) > 0: return 1
        for _ in range(3):
            try:
                d = urllib.request.urlopen(urllib.request.Request(
                    url, headers={"User-Agent": "curl/8.0", "Referer": "https://weibo.com/"}),
                    timeout=30).read()
                if d and len(d) > 200: open(fp, "wb").write(d); return 1
            except Exception: pass
        return 0
    ok = 0
    with cf.ThreadPoolExecutor(max_workers=12) as ex:
        for r in ex.map(get, tasks.items()): ok += r
    log("images saved: %d/%d" % (ok, len(tasks)))

def build(posts):
    posts.sort(key=lambda p: p.get("_dt", ""), reverse=True)
    recs = []
    for m in posts:
        rt = m.get("retweeted_status")
        r = {"dt": m.get("_dt", ""), "text": clean(m.get("long_text") or m.get("text") or ""),
             "likes": m.get("attitudes_count", 0), "comments": m.get("comments_count", 0),
             "reposts": m.get("reposts_count", 0), "is_rt": bool(rt),
             "imgs": [(p.get("large") or p.get("original") or p).get("url")
                      for p in (m.get("pics") or [])], "url": "https://m.weibo.cn/detail/%s" % m.get("id")}
        r["imgs"] = [u for u in r["imgs"] if u]
        if rt:
            r["rt_author"] = (rt.get("user") or {}).get("screen_name", "")
            r["rt_text"] = clean(rt.get("long_text") or rt.get("text") or "")
        recs.append(r)
    return recs

def write_reports(recs, name, uid, start, end, outdir, dname):
    os.makedirs(outdir, exist_ok=True)
    orig = [r for r in recs if not r["is_rt"]]
    bymonth = collections.Counter(r["dt"][:7] for r in recs if r["dt"])
    days = sorted({r["dt"][:10] for r in recs if r["dt"]})
    wimg = sum(1 for r in recs if r["imgs"]); wvid = 0
    top = sorted(recs, key=lambda r: r["likes"], reverse=True)[:10]
    fin = os.path.join(outdir, "%s_%s-%s" % (dname, start, end))
    md = []; A = md.append
    A("# %s · 微博整理报告" % name); A("")
    A("> 主页：https://weibo.com/u/%s　|　范围：**%s ~ %s**" % (uid, start, end)); A("")
    A("> 生成：%s　|　共 **%d** 条" % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), len(recs))); A("")
    A("## 概览"); A("")
    A("| 指标 | 数值 |"); A("|---|---|")
    for k, v in [("帖子总数", len(recs)), ("原创", len(orig)), ("转发", len(recs)-len(orig)),
                 ("含图", wimg), ("覆盖天数", len(days))]:
        A("| %s | %s |" % (k, v))
    A("| 日均 | %.1f 条 |" % (len(recs)/max(1, len(days)))); A("")
    A("**按月：** " + "　".join("%s：%d" % (k, v) for k, v in sorted(bymonth.items(), reverse=True))); A("")
    A("### 互动 TOP 10"); A("")
    A("| 时间 | 👍 | 💬 | 🔁 | 摘要 |"); A("|---|---|---|---|---|")
    for r in top:
        A("| %s | %d | %d | %d | %s |" % (r["dt"][5:16], r["likes"], r["comments"], r["reposts"],
          (r["text"][:40].replace(chr(10), " ") or "（转发）")))
    A("")
    cur = None
    for r in recs:
        mo = r["dt"][:7]
        if mo != cur: cur = mo; A(""); A("## %s（%d 条）" % (mo, bymonth[mo])); A("")
        A("### %s%s" % (r["dt"], "　🔁转发" if r["is_rt"] else "")); A("")
        if r["is_rt"]:
            A("> **转发 @%s：**" % r["rt_author"])
            for ln in (r["rt_text"] or "").split(chr(10)): A("> " + ln)
            A("")
            if r["text"].strip(): A("**评论：** " + r["text"]); A("")
        else:
            A(r["text"] or "（无正文）"); A("")
        for u in r["imgs"]: A("![](images/%s)" % u.rsplit("/", 1)[-1])
        if r["imgs"]: A("")
        A("互动：👍 %d　💬 %d　🔁 %d　| [原文](%s)" % (r["likes"], r["comments"], r["reposts"], r["url"]))
        A(""); A("---")
    open(fin + ".md", "w", encoding="utf-8").write(chr(10).join(md))
    H = []; B = H.append
    B("<!doctype html><html lang='zh'><head><meta charset='utf-8'>")
    B("<meta name='viewport' content='width=device-width,initial-scale=1'><title>%s 微博整理</title>" % name)
    B("<style>body{font-family:-apple-system,'Microsoft YaHei',sans-serif;max-width:860px;margin:0 auto;padding:24px;background:#f5f6f8;color:#1f2329;line-height:1.75}")
    B("h1{font-size:26px;border-bottom:3px solid #ff8140;padding-bottom:10px}h2{font-size:19px;margin-top:36px;background:#ff8140;color:#fff;padding:8px 14px;border-radius:6px}")
    B("h3{font-size:14px;color:#6b7280;margin:22px 0 6px}.post{background:#fff;border-radius:10px;padding:16px 18px;margin:12px 0;box-shadow:0 1px 4px rgba(0,0,0,.07)}")
    B(".post.rt{border-left:4px solid #4a90d9}.meta{color:#8a8f99;font-size:13px;margin-top:10px}.tag{font-size:12px;padding:1px 8px;border-radius:10px;background:#e6f0fb;color:#2d6cb5}")
    B("blockquote{margin:6px 0;padding:8px 12px;background:#f5f7fa;border-left:3px solid #c9d2dc}.stats{display:flex;gap:12px;flex-wrap:wrap;margin:16px 0}")
    B(".stat{background:#fff;border-radius:8px;padding:10px 16px;box-shadow:0 1px 3px rgba(0,0,0,.06);font-size:13px}.stat b{display:block;font-size:20px;color:#ff8140}")
    B("table{border-collapse:collapse;width:100%;background:#fff;border-radius:8px;overflow:hidden;font-size:14px}th,td{border-bottom:1px solid #eef1f5;padding:8px 10px;text-align:left}th{background:#fafbfc}")
    B("a{color:#2d6cb5;text-decoration:none}img{max-width:170px;border-radius:6px;margin:4px 4px 0 0}</style></head><body>")
    B("<h1>%s · 微博整理报告</h1>" % _html.escape(name))
    B("<p>主页：<a href='https://weibo.com/u/%s'>weibo.com/u/%s</a>　|　范围：<b>%s ~ %s</b>　|　共 <b>%d</b> 条</p>" % (uid, uid, start, end, len(recs)))
    B("<div class='stats'>")
    for k, v in [("总帖数", len(recs)), ("原创", len(orig)), ("转发", len(recs)-len(orig)), ("含图", wimg), ("覆盖天数", len(days))]:
        B("<div class='stat'>%s<b>%d</b></div>" % (k, v))
    B("</div><h2>互动量 TOP 10</h2><table><tr><th>时间</th><th>👍</th><th>💬</th><th>🔁</th><th>摘要</th></tr>")
    for r in top:
        B("<tr><td>%s</td><td>%d</td><td>%d</td><td>%d</td><td>%s</td></tr>" % (r["dt"][:16], r["likes"], r["comments"], r["reposts"], _html.escape(r["text"][:60].replace(chr(10), " ")) or "（转发）"))
    B("</table><h2>正文（按时间倒序）</h2>")
    cur = None
    for r in recs:
        mo = r["dt"][:7]
        if mo != cur: cur = mo; B("<h2>%s（%d 条）</h2>" % (mo, bymonth[mo]))
        B("<div class='post%s'>" % (" rt" if r["is_rt"] else ""))
        B("<h3>%s %s</h3>" % (r["dt"], "<span class='tag'>🔁 转发</span>" if r["is_rt"] else ""))
        if r["is_rt"]:
            B("<blockquote><b>@%s：</b><br>%s</blockquote>" % (_html.escape(r["rt_author"]), _html.escape(r["rt_text"]).replace(chr(10), "<br>")))
            if r["text"].strip(): B("<p>%s</p>" % _html.escape(r["text"]).replace(chr(10), "<br>"))
        else:
            B("<div>%s</div>" % (_html.escape(r["text"]).replace(chr(10), "<br>") or "（无正文）"))
        if r["imgs"]:
            B("<div>" + "".join("<a href='%s' target='_blank'><img src='images/%s' loading='lazy'></a>" % (u, u.rsplit("/", 1)[-1]) for u in r["imgs"]) + "</div>")
        B("<div class='meta'>👍 %d　💬 %d　🔁 %d　|　<a href='%s' target='_blank'>原文</a></div></div>" % (r["likes"], r["comments"], r["reposts"], r["url"]))
    B("</body></html>")
    open(fin + ".html", "w", encoding="utf-8").write("".join(H))
    log("输出: %s.md / %s.html" % (fin, fin))

def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    name = sys.argv[1]
    start = sys.argv[2] if len(sys.argv) > 2 else (datetime.datetime.now() - datetime.timedelta(days=60)).strftime("%Y-%m-%d")
    end = datetime.date.today().strftime("%Y-%m-%d")
    start_dt = datetime.datetime.strptime(start, "%Y-%m-%d")
    log("目标博主: %s | 起始: %s" % (name, start))

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=PROFILE, channel="chrome", headless=True,
            args=["--no-first-run", "--no-default-browser-check"])

        cfg = ctx.request.get("https://m.weibo.cn/api/config", headers=H, timeout=25000).json().get("data", {})
        if not cfg.get("login"):
            log("!! 未登录。请先运行 wb_login.py 扫码登录。"); ctx.close(); return
        log("已登录 uid=%s" % cfg.get("uid"))

        if name.isdigit():
            uid = name
        else:
            cands = search_uid(ctx, name)
            if not cands:
                log("!! 未找到该博主，换个昵称或直接用 uid"); ctx.close(); return
            exact = [c for c in cands if c[1] == name]
            uid, cname, fans, ver = (exact or cands)[0]
            log("匹配到: %s (uid=%s, 粉丝=%s, %s)" % (cname, uid, fans, ver))

        posts = fetch_posts(ctx, uid, start_dt)
        log("抓取完成: %d 条" % len(posts))
        fetch_long(ctx, posts)
        outdir = os.path.join(OUTDIR, "%s_微博报告" % name)
        download_images(posts, os.path.join(outdir, "images"))
        recs = build(posts)
        write_reports(recs, name, uid, start, end, outdir, name)
        log("全部完成 -> %s" % outdir)
        ctx.close()

if __name__ == "__main__":
    main()
