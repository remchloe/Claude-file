import akshare as ak
import pandas as pd
from datetime import datetime, timedelta

# 本周日期范围 (2026-07-06 ~ 2026-07-10)
start_date = "20260706"
end_date = "20260710"
start_date_fmt = "2026-07-06"
end_date_fmt = "2026-07-10"

# A股主要ETF列表 (代码: 名称)
etf_list = {
    "510300": "沪深300ETF",
    "510500": "中证500ETF",
    "512100": "中证1000ETF",
    "588000": "科创50ETF",
    "159915": "创业板ETF",
    "512480": "半导体ETF",
    "159995": "芯片ETF",
    "510880": "红利ETF",
    "159928": "消费ETF",
    "512170": "医疗ETF",
    "512800": "银行ETF",
    "516160": "新能源ETF",
    "512000": "券商ETF",
    "512660": "军工ETF",
    "159869": "游戏ETF",
    "518880": "黄金ETF",
}

# 港股ETF列表
hk_etf_list = {
    "159920": "恒生ETF",
    "513130": "恒生科技ETF",
    "513060": "恒生医疗ETF",
}

def get_etf_weekly_return(code, name):
    try:
        df = ak.fund_etf_hist_em(symbol=code, period="daily",
                                  start_date=start_date, end_date=end_date,
                                  adjust="qfq")
        if df is None or df.empty:
            return None
        df = df.sort_values("日期")
        open_price = df.iloc[0]["开盘"]
        close_price = df.iloc[-1]["收盘"]
        weekly_return = (close_price - open_price) / open_price * 100
        turnover = df["成交额"].sum() / 1e8  # 亿元
        max_price = df["最高"].max()
        min_price = df["最低"].min()
        amplitude = (max_price - min_price) / open_price * 100
        return {
            "code": code,
            "name": name,
            "open": round(open_price, 3),
            "close": round(close_price, 3),
            "weekly_return": round(weekly_return, 2),
            "turnover_sum": round(turnover, 2),
            "amplitude": round(amplitude, 2),
            "days": len(df),
        }
    except Exception as e:
        return {"code": code, "name": name, "error": str(e)}

print("=" * 60)
print(f"A股 ETF 本周行情 ({start_date_fmt} ~ {end_date_fmt})")
print("=" * 60)

a_results = []
for code, name in etf_list.items():
    r = get_etf_weekly_return(code, name)
    a_results.append(r)
    if r and "error" not in r:
        print(f"{code} {name}: 周涨跌 {r['weekly_return']:+.2f}%, 振幅 {r['amplitude']:.2f}%, 成交额 {r['turnover_sum']:.2f}亿")
    else:
        print(f"{code} {name}: 获取失败 - {r.get('error', 'unknown')}")

print("\n" + "=" * 60)
print(f"港股 ETF 本周行情 ({start_date_fmt} ~ {end_date_fmt})")
print("=" * 60)

hk_results = []
for code, name in hk_etf_list.items():
    r = get_etf_weekly_return(code, name)
    hk_results.append(r)
    if r and "error" not in r:
        print(f"{code} {name}: 周涨跌 {r['weekly_return']:+.2f}%, 振幅 {r['amplitude']:.2f}%, 成交额 {r['turnover_sum']:.2f}亿")
    else:
        print(f"{code} {name}: 获取失败 - {r.get('error', 'unknown')}")

# 保存为CSV便于后续分析
df_a = pd.DataFrame([r for r in a_results if r and "error" not in r])
df_hk = pd.DataFrame([r for r in hk_results if r and "error" not in r])

if not df_a.empty:
    df_a.sort_values("weekly_return", ascending=False, inplace=True)
    df_a.to_csv("etf_a_weekly.csv", index=False, encoding="utf-8-sig")
    print("\n[A股 ETF 本周涨幅排名]")
    print(df_a[["code", "name", "weekly_return", "turnover_sum"]].to_string(index=False))

if not df_hk.empty:
    df_hk.sort_values("weekly_return", ascending=False, inplace=True)
    df_hk.to_csv("etf_hk_weekly.csv", index=False, encoding="utf-8-sig")
    print("\n[港股 ETF 本周涨幅排名]")
    print(df_hk[["code", "name", "weekly_return", "turnover_sum"]].to_string(index=False))

print("\n数据已保存到 etf_a_weekly.csv 和 etf_hk_weekly.csv")
