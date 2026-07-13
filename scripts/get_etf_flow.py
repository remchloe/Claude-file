import akshare as ak
import pandas as pd

# 获取ETF资金流向数据 (东方财富)
print("=" * 60)
print("A股 ETF 资金流向 (单位: 亿元)")
print("=" * 60)

# 尝试获取ETF资金流向
try:
    flow_df = ak.fund_etf_flow_em()
    if flow_df is not None and not flow_df.empty:
        # 只保留我们关注的ETF
        target_codes = ["510300", "510500", "512100", "588000", "159915",
                        "512480", "159995", "510880", "159928", "512170",
                        "512800", "516160", "512000", "512660", "159869", "518880"]
        # 代码格式匹配
        filtered = flow_df[flow_df["代码"].isin(target_codes)]
        if not filtered.empty:
            print(filtered[["代码", "名称", "主力净流入", "主力流入", "主力流出", "最新价", "涨跌幅"]].to_string(index=False))
        else:
            print("未匹配到目标ETF资金流向，输出全量前20:")
            print(flow_df.head(20)[["代码", "名称", "主力净流入", "最新价", "涨跌幅"]].to_string(index=False))
    else:
        print("未能获取资金流向数据")
except Exception as e:
    print(f"获取资金流向失败: {e}")

# 获取近20日数据用于动量对比
print("\n" + "=" * 60)
print("近20日动量对比 (用于判断轮动)")
print("=" * 60)

start_20d = "20260613"  # 约20交易日前
end_date = "20260710"

etf_short = {
    "510300": "沪深300ETF",
    "588000": "科创50ETF",
    "512480": "半导体ETF",
    "159995": "芯片ETF",
    "510880": "红利ETF",
    "512800": "银行ETF",
    "516160": "新能源ETF",
    "512100": "中证1000ETF",
    "159915": "创业板ETF",
    "512000": "券商ETF",
    "159869": "游戏ETF",
    "513130": "恒生科技ETF",
}

momentum_results = []
for code, name in etf_short.items():
    try:
        df = ak.fund_etf_hist_em(symbol=code, period="daily",
                                  start_date=start_20d, end_date=end_date,
                                  adjust="qfq")
        if df is not None and len(df) >= 2:
            df = df.sort_values("日期")
            # 近5日动量
            ret_5d = (df.iloc[-1]["收盘"] - df.iloc[-5]["收盘"]) / df.iloc[-5]["收盘"] * 100 if len(df) >= 5 else None
            # 近20日动量
            ret_20d = (df.iloc[-1]["收盘"] - df.iloc[0]["收盘"]) / df.iloc[0]["收盘"] * 100
            momentum_results.append({
                "code": code, "name": name,
                "ret_5d": round(ret_5d, 2) if ret_5d else None,
                "ret_20d": round(ret_20d, 2),
            })
    except Exception as e:
        pass

mom_df = pd.DataFrame(momentum_results)
if not mom_df.empty:
    mom_df.sort_values("ret_5d", ascending=False, inplace=True)
    mom_df.to_csv("etf_momentum.csv", index=False, encoding="utf-8-sig")
    print(mom_df.to_string(index=False))

print("\n数据已保存到 etf_momentum.csv")
