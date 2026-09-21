# -*- coding: utf-8 -*-
"""微博扫码登录工具（一次性）

首次使用或登录态失效时运行本脚本，会打开一个独立 Chrome 窗口，
用手机微博 App 扫码登录即可。登录态保存在 PROFILE 目录中（默认
~/weibo_profile），后续抓取脚本自动复用，不会影响你日常使用的 Chrome。

注意：PROFILE 目录包含登录凭证（Cookie），切勿提交到 git。
"""
import os, time
from playwright.sync_api import sync_playwright

# 登录态保存目录（含敏感凭证，勿入库）
PROFILE = os.environ.get("WEIBO_PROFILE", os.path.join(os.path.expanduser("~"), "weibo_profile"))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36")

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        user_data_dir=PROFILE, channel="chrome", headless=False, user_agent=UA,
        args=["--no-first-run", "--no-default-browser-check",
              "--disable-blink-features=AutomationControlled", "--start-maximized"],
        viewport=None)
    ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
    pg = ctx.pages[0] if ctx.pages else ctx.new_page()
    pg.goto("https://passport.weibo.com/sso/signin?entry=miniblog&source=miniblog"
            "&disp=popup&url=https%3A%2F%2Fweibo.com%2F",
            wait_until="domcontentloaded", timeout=60000)
    print("登录窗口已打开，请用手机微博 App 扫码登录...", flush=True)

    def check():
        # 用独立请求上下文检查登录态，不会刷新可见页面
        try:
            j = ctx.request.get("https://weibo.com/ajax/profile/info",
                                headers={"Referer": "https://weibo.com/"}, timeout=20000).json()
            u = (j.get("data") or {}).get("user") or {}
            return u.get("id"), u.get("screen_name")
        except Exception:
            return None, None

    for i in range(1800):                     # 最多等待 60 分钟
        uid, name = check()
        if uid:
            print("登录成功: uid=%s name=%s" % (uid, name), flush=True)
            break
        if i % 15 == 0:
            print("[%ds] 等待扫码..." % (i * 2), flush=True)
        time.sleep(2)
    time.sleep(3)
    ctx.close()
    print("已关闭，登录态已保存。", flush=True)
