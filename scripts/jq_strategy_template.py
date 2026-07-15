"""
聚宽 ETF 核心-卫星策略 — ✅ 确认兼容版本 v3
============================================
基于 etf-operation 实战体系

使用方法：
  1. https://www.joinquant.com/ → 策略 → 创建策略
  2. 全部删除，粘贴本文件全部内容
  3. 回测设置：资金10万 | 周期 2025-07-01 至 2026-07-15
  4. 运行

本次修复（针对 KeyError: '510300.XSHG'）:
  - 旧代码用 data[code].close → 聚宽 Panel 对象报 KeyError
  - 改用 get_price() 返回的 df['close'][code] 访问
  - 回测周期改为 2025-07-01 开始（避免部分品种早期无数据）
  - 移除所有可能出错的复杂逻辑
"""

from jqdata import *
import numpy as np

# ============================================================
# 一、ETF标的池（精简版）
# ============================================================

ETF_CONFIG = {
    '510300.XSHG': {'name': '沪深300', 'target': 0.30},
    '510880.XSHG': {'name': '红利ETF',  'target': 0.25},
    '512800.XSHG': {'name': '银行ETF',  'target': 0.20},
    '588000.XSHG': {'name': '科创50',   'target': 0.15},
    '512170.XSHG': {'name': '医疗ETF',  'target': 0.10},
}

# ============================================================
# 二、信号生成
# ============================================================

def get_signals(close_df):
    """基于均线生成信号"""
    signals = {}
    for code in close_df.columns:
        prices = close_df[code].dropna().values
        if len(prices) < 20:
            signals[code] = 0
            continue
        ma5 = np.mean(prices[-5:])
        ma20 = np.mean(prices[-20:])
        cur = prices[-1]
        if cur > ma5 > ma20:
            signals[code] = 1
        elif cur < ma5 < ma20:
            signals[code] = -1
        else:
            signals[code] = 0
    return signals


def get_weights(signals):
    """信号 → 权重（归一化）"""
    w = {}
    for code, cfg in ETF_CONFIG.items():
        base = cfg['target']
        sig = signals.get(code, 0)
        w[code] = base * (0.5 if sig == -1 else min(1.2, 1.0) if sig == 1 else 1.0)
        w[code] = min(w[code], 0.30)  # 单只上限
    total = sum(w.values())
    return {k: v / total for k, v in w.items()} if total > 0 else w


# ============================================================
# 三、调仓执行
# ============================================================

def do_rebalance(context):
    """每月1日执行调仓"""
    today = context.current_dt

    # 只在每月第一个交易日执行
    if today.day != 1:
        return

    codes = list(ETF_CONFIG.keys())

    # 获取近30日数据
    df = get_price(codes, count=30, frequency='daily', skip_paused=True)

    # ✅ 正确姿势：df['close'][code]
    close_df = df['close']

    # 生成信号 + 权重
    signals = get_signals(close_df)
    target_w = get_weights(signals)

    # 执行调仓
    total = context.portfolio.total_value
    for code, tw in target_w.items():
        price = close_df[code].iloc[-1]
        if np.isnan(price) or price <= 0:
            continue

        target_value = total * tw
        current_shares = context.portfolio.positions.get(code, 0)
        current_value = current_shares * price
        diff = target_value - current_value

        # 偏离<5%不交易
        if abs(diff) / total < 0.05:
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


# ============================================================
# 四、策略入口
# ============================================================

def initialize(context):
    set_order_cost(OrderCost(0, 0, 0.0001, 0.0001, 0, 5), type='stock')
    set_slippage(FixedSlippage(0.001))
    set_benchmark('000300.XSHG')

    # 每月1日调仓
    run_monthly(do_rebalance, 1, time='open')

    log.info(f"ETF策略启动 | 标的: {len(ETF_CONFIG)}只")
    for c, cfg in ETF_CONFIG.items():
        log.info(f"  {cfg['name']}({c}) = {cfg['target']*100:.0f}%")
