"""
聚宽 ETF 策略 — v9 Claude信号注入版
====================================
核心思路：保留v7的稳定执行框架，但信号来源改为"每日注入"。
Claude每天分析后生成信号，你只需要更新 CLAUDE_SIGNAL 字典。

工作流程：
  1. Claude 生成当日分析 → 输出 JSON 信号
  2. 你复制 JSON → 粘贴到下面 CLAUDE_SIGNAL 区域
  3. 策略下次运行时（run_daily 每日检查），自动按Claude信号调仓 ✅
  4. 如果当天没有新信号（CLAUDE_SIGNAL为空），策略会使用均线备选信号

这样你每天只需要：复制 → 粘贴 → 保存，3秒钟搞定。
"""

from jqdata import *
import numpy as np

# ============================================================
# ★★★ 每日更新区域 ★★★
# Claude 每天生成这个 JSON，你直接复制粘贴覆盖即可
# 如果为空 {}，策略会自动使用均线备选信号
# ============================================================

CLAUDE_SIGNAL = {
    "date": "2026-07-15",
    "market_phase": "防御期",
    "signals": {
        "510300.XSHG": 0,    # 沪深300: -1卖出 0持有 1买入
        "510880.XSHG": 1,    # 红利ETF: 防御配置，继续增配
        "512800.XSHG": 1,    # 银行ETF: 避险方向，持有
        "588000.XSHG": -1,   # 科创50: 长鑫IPO冲击，减仓
        "512170.XSHG": 1,    # 医疗ETF: 底部放量，逢低布局
    },
    "cash_pct": 0.10,         # 现金比例
}

# ============================================================
# ETF配置（一般情况下不需要改）
# ============================================================

ETF_CODE_LIST = ['510300.XSHG', '510880.XSHG', '512800.XSHG', '588000.XSHG', '512170.XSHG']
ETF_NAME_DICT = {
    '510300.XSHG': '沪深300',
    '510880.XSHG': '红利ETF',
    '512800.XSHG': '银行ETF',
    '588000.XSHG': '科创50',
    '512170.XSHG': '医疗ETF',
}
ETF_BASE_WEIGHT = {
    '510300.XSHG': 0.30,
    '510880.XSHG': 0.25,
    '512800.XSHG': 0.20,
    '588000.XSHG': 0.15,
    '512170.XSHG': 0.10,
}

CLAUDE_MULT = {1: 1.2, 0: 1.0, -1: 0.5}  # 信号→权重乘数


def initialize(context):
    set_order_cost(OrderCost(0, 0, 0.0001, 0.0001, 0, 5), type='stock')
    set_slippage(FixedSlippage(0.001))
    set_benchmark('000300.XSHG')

    # 每日开盘检查是否需要调仓
    run_daily(daily_check, time='open')

    log.info('策略v9启动 | Claude信号注入模式 | 每日检查调仓')


def gen_signals():
    """
    优先使用Claude信号，没有则用均线备选
    """
    sig = {}
    has_claude = CLAUDE_SIGNAL and len(CLAUDE_SIGNAL.get('signals', {})) > 0

    if has_claude:
        # 使用Claude信号
        for code in ETF_CODE_LIST:
            sig[code] = CLAUDE_SIGNAL['signals'].get(code, 0)
        log.info(f'使用Claude信号 | {CLAUDE_SIGNAL.get("date","")} | {CLAUDE_SIGNAL.get("market_phase","")}')
    else:
        # 备选：均线信号（聚宽环境内自生成）
        log.info('无Claude信号，使用均线备选')
        for code in ETF_CODE_LIST:
            df = attribute_history(code, 20, '1d', ['close'])
            if df is None or len(df) < 20:
                sig[code] = 0
                continue
            v = df['close'].values
            ma5 = float(v[-5:].mean())
            ma20 = float(v[-20:].mean())
            cur = float(v[-1])
            if cur > ma5 > ma20:
                sig[code] = 1
            elif cur < ma5 < ma20:
                sig[code] = -1
            else:
                sig[code] = 0

    return sig


def calc_target(signals):
    """信号 → 归一化权重"""
    cash_pct = CLAUDE_SIGNAL.get('cash_pct', 0.05) if CLAUDE_SIGNAL else 0.05
    w = {}
    for code in ETF_CODE_LIST:
        base = ETF_BASE_WEIGHT[code]
        s = signals.get(code, 0)
        w[code] = min(base * CLAUDE_MULT.get(s, 1.0), 0.35)
    total = sum(w.values())
    if total <= 0:
        return {}
    scale = 1.0 - cash_pct
    return {k: v / total * scale for k, v in w.items()}


def daily_check(context):
    """每日检查是否需要调仓"""
    signals = gen_signals()
    target = calc_target(signals)

    if not target:
        return

    total_val = context.portfolio.total_value
    has_trade = False

    for code in ETF_CODE_LIST:
        cur_price = attribute_history(code, 1, '1d', ['close'])
        if cur_price is None or cur_price.empty:
            continue
        price = float(cur_price['close'].iloc[-1])
        if np.isnan(price) or price <= 0:
            continue

        want_val = total_val * target[code]
        pos = context.portfolio.positions.get(code)
        have_shares = pos.total_amount if pos else 0
        have_val = have_shares * price
        diff = want_val - have_val

        if abs(diff) / total_val < 0.02:  # 2%阈值
            continue

        shares = int(diff / price / 100) * 100
        if shares == 0:
            continue

        try:
            order(code, shares)
            action = '买入' if shares > 0 else '卖出'
            log.info(f'{action} {ETF_NAME_DICT[code]} {abs(shares)}股 @ {price:.3f}')
            has_trade = True
        except Exception as e:
            log.error(f'下单失败 {code}: {e}')

    if not has_trade:
        log.info('无需调仓，当前持仓符合目标')
