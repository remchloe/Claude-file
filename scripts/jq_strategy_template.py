"""
聚宽 ETF 核心-卫星策略 — v4 最终简化版
============================================
基于 etf-operation 实战体系

使用方法：
  1. https://www.joinquant.com/ → 策略 → 创建策略
  2. 全部删除，粘贴本文件全部内容
  3. 回测设置：初始资金 10万 | 周期 2025-07-01 至 2026-07-15
  4. 点击运行

⚠️ 如果之前复制过旧版本，确保先全部删除再粘贴。
   错误日志中若出现 w.items() 或 dict_values 说明跑的还是旧代码。
"""

from jqdata import *
import numpy as np

# ============================================================
# 一、策略配置
# ============================================================

# ETF 配置 {代码: 名称, 目标权重}
ETF_CONFIG = {
    '510300.XSHG': {'name': '沪深300', 'weight': 0.30},
    '510880.XSHG': {'name': '红利ETF', 'weight': 0.25},
    '512800.XSHG': {'name': '银行ETF', 'weight': 0.20},
    '588000.XSHG': {'name': '科创50',  'weight': 0.15},
    '512170.XSHG': {'name': '医疗ETF', 'weight': 0.10},
}
CODES = list(ETF_CONFIG.keys())

# ============================================================
# 二、调仓（每月1日执行）
# ============================================================

def do_rebalance(context):
    today = context.current_dt

    # 只在每月第一个交易日执行
    if today.day != 1:
        return

    # --- 获取数据：用 history 替代 get_price ---
    # history(count, unit, field, security_list, df=True)
    # 返回 DataFrame：行=日期，列=股票代码
    close_df = history(30, unit='1d', field='close', security_list=CODES, df=True)

    if close_df is None or close_df.empty:
        log.warn('无法获取行情数据，跳过本次调仓')
        return

    # --- 生成均线信号 ---
    signals = {}
    for code in CODES:
        if code not in close_df.columns:
            signals[code] = 0
            continue
        prices = close_df[code].dropna().values
        if len(prices) < 20:
            signals[code] = 0
            continue
        ma5 = float(np.mean(prices[-5:]))
        ma20 = float(np.mean(prices[-20:]))
        cur = float(prices[-1])
        if cur > ma5 > ma20:
            signals[code] = 1
        elif cur < ma5 < ma20:
            signals[code] = -1
        else:
            signals[code] = 0

    # --- 信号 → 权重（归一化）---
    raw = {}
    for code in CODES:
        base = ETF_CONFIG[code]['weight']
        sig = signals.get(code, 0)
        if sig == -1:
            raw[code] = base * 0.5
        elif sig == 1:
            raw[code] = base * 1.2
        else:
            raw[code] = base
        if raw[code] > 0.30:
            raw[code] = 0.30

    total_w = sum(raw.values())
    if total_w <= 0:
        log.warn('权重合计<=0，跳过调仓')
        return
    target_w = {k: v / total_w for k, v in raw.items()}

    # --- 执行调仓 ---
    portfolio_total = context.portfolio.total_value
    for code, tw in target_w.items():
        price = float(close_df[code].iloc[-1])
        if np.isnan(price) or price <= 0:
            continue

        target_value = portfolio_total * tw
        pos = context.portfolio.positions.get(code)
        current_shares = pos.total_amount if pos else 0
        current_value = current_shares * price
        diff = target_value - current_value

        # 偏差<5%不调
        if abs(diff) / portfolio_total < 0.05:
            continue

        shares = int(diff / price / 100) * 100
        if shares == 0:
            continue

        try:
            order(code, shares)
            action = '买入' if shares > 0 else '卖出'
            log.info(f"{action} {ETF_CONFIG[code]['name']} {abs(shares)}股 @ {price:.3f}")
        except Exception as e:
            log.error(f"下单失败 {code}: {e}")

    log.info(f"调仓完成 | 总资产: {portfolio_total:.2f}")


# ============================================================
# 三、策略入口
# ============================================================

def initialize(context):
    set_order_cost(OrderCost(0, 0, 0.0001, 0.0001, 0, 5), type='stock')
    set_slippage(FixedSlippage(0.001))
    set_benchmark('000300.XSHG')

    # 每月1日开盘调仓
    run_monthly(do_rebalance, 1, time='open')

    log.info(f"ETF策略启动 | {len(CODES)}只标的")
    for c in CODES:
        log.info(f"  {ETF_CONFIG[c]['name']}({c}) = {ETF_CONFIG[c]['weight']*100:.0f}%")
