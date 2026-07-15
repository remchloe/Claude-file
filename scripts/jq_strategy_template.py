"""
聚宽 ETF 核心-卫星策略 — v5 最终版
====================================
使用方法：
  1. 全部删除旧代码，粘贴本文件全部内容
  2. 回测：10万 | 2025-07-01 至 2026-07-15
  3. 运行
"""

from jqdata import *
import numpy as np

# ETF配置
CODES = {
    '510300.XSHG': '沪深300',
    '510880.XSHG': '红利ETF',
    '512800.XSHG': '银行ETF',
    '588000.XSHG': '科创50',
    '512170.XSHG': '医疗ETF',
}
# 目标权重
TARGET = {
    '510300.XSHG': 0.30,
    '510880.XSHG': 0.25,
    '512800.XSHG': 0.20,
    '588000.XSHG': 0.15,
    '512170.XSHG': 0.10,
}
CODE_LIST = list(CODES.keys())


def initialize(context):
    set_order_cost(OrderCost(0, 0, 0.0001, 0.0001, 0, 5), type='stock')
    set_slippage(FixedSlippage(0.001))
    set_benchmark('000300.XSHG')
    run_monthly(rebalance, 1, time='open')
    log.info('策略启动 | 5只ETF')


def rebalance(context):
    if context.current_dt.day != 1:
        return

    # ---- 用 get_price 获取收盘价 ----
    # panel=False 返回 MultiIndex DataFrame: df['close'][code] 是收盘价序列
    df = get_price(CODE_LIST, count=30, frequency='daily',
                   fields=['close'], panel=False)
    close_data = df['close']  # DataFrame: 行=日期, 列=代码

    # ---- 均线信号 ----
    signal = {}
    for code in CODE_LIST:
        series = close_data[code].dropna()
        if len(series) < 20:
            signal[code] = 0
            continue
        v = series.values
        ma5 = float(v[-5:].mean())
        ma20 = float(v[-20:].mean())
        cur = float(v[-1])
        if cur > ma5 > ma20:
            signal[code] = 1
        elif cur < ma5 < ma20:
            signal[code] = -1
        else:
            signal[code] = 0

    # ---- 权重计算 ----
    raw = {}
    for code in CODE_LIST:
        w = TARGET[code]
        sig = signal.get(code, 0)
        if sig == -1:
            w = w * 0.5
        elif sig == 1:
            w = w * 1.2
        raw[code] = min(w, 0.30)

    total = sum(raw.values())
    if total <= 0:
        return
    target_w = {k: v / total for k, v in raw.items()}

    # ---- 执行调仓 ----
    total_value = context.portfolio.total_value
    for code, tw in target_w.items():
        price = float(close_data[code].iloc[-1])
        if np.isnan(price) or price <= 0:
            continue

        target_val = total_value * tw
        pos = context.portfolio.positions.get(code)
        cur_shares = pos.total_amount if pos else 0
        cur_val = cur_shares * price
        diff = target_val - cur_val

        if abs(diff) / total_value < 0.05:
            continue

        shares = int(diff / price / 100) * 100
        if shares == 0:
            continue

        try:
            order(code, shares)
            act = '买入' if shares > 0 else '卖出'
            log.info(f'{act} {CODES[code]} {abs(shares)}股 @ {price:.3f}')
        except Exception as e:
            log.error(f'下单失败 {code}: {e}')
