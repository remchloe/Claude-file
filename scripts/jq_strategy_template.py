"""
聚宽 ETF 策略 — 最终版
========================
使用方式：每天复制Claude报告底部的信号区 → 粘贴到下面 SIGNAL 区域 → 保存 ✅
"""

from jqdata import *
import numpy as np

# ================================================================
# ★ 每日更新区（Claude的报告末尾会附上这段代码，复制粘贴覆盖即可）
# ================================================================
SIGNAL = {
    "date": "2026-07-15",
    "market_phase": "防御期",
    "signals": {
        "510300.XSHG": 0,   # 沪深300: -1卖出 0持有 1买入
        "510880.XSHG": 1,   # 红利ETF
        "512800.XSHG": 1,   # 银行ETF
        "588000.XSHG": -1,  # 科创50
        "512170.XSHG": 1,   # 医疗ETF
    },
    "cash_pct": 0.10,
}
# ================================================================

ETF_CODE_LIST = ['510300.XSHG', '510880.XSHG', '512800.XSHG', '588000.XSHG', '512170.XSHG']
ETF_NAME_DICT = {
    '510300.XSHG': '沪深300', '510880.XSHG': '红利ETF', '512800.XSHG': '银行ETF',
    '588000.XSHG': '科创50', '512170.XSHG': '医疗ETF',
}
ETF_BASE_WEIGHT = {
    '510300.XSHG': 0.30, '510880.XSHG': 0.25, '512800.XSHG': 0.20,
    '588000.XSHG': 0.15, '512170.XSHG': 0.10,
}
SIGNAL_MULT = {1: 1.2, 0: 1.0, -1: 0.5}


def initialize(context):
    set_order_cost(OrderCost(0, 0, 0.0001, 0.0001, 0, 5), type='stock')
    set_slippage(FixedSlippage(0.001))
    set_benchmark('000300.XSHG')
    run_daily(daily_run, time='open')
    log.info('策略启动 | 每日更新SIGNAL即可')


def daily_run(context):
    sig = SIGNAL.get('signals', {})
    has_signal = len(sig) > 0

    if has_signal:
        log.info(f'使用当日信号 | {SIGNAL.get("date","")} | {SIGNAL.get("market_phase","")}')
    else:
        # 备选：均线
        log.info('无信号，使用均线备选')
        for code in ETF_CODE_LIST:
            df = attribute_history(code, 20, '1d', ['close'])
            if df is None or len(df) < 20:
                sig[code] = 0
            else:
                v = df['close'].values
                ma5, ma20 = float(v[-5:].mean()), float(v[-20:].mean())
                cur = float(v[-1])
                sig[code] = 1 if cur > ma5 > ma20 else (-1 if cur < ma5 < ma20 else 0)
        SIGNAL['cash_pct'] = 0.05

    # 权重
    cash_pct = SIGNAL.get('cash_pct', 0.05)
    w = {}
    for code in ETF_CODE_LIST:
        s = sig.get(code, 0)
        w[code] = min(ETF_BASE_WEIGHT[code] * SIGNAL_MULT.get(s, 1.0), 0.35)

    total = 0.0
    for v in w.values():
        total += v
    if total <= 0.0: return
    scale = 1.0 - cash_pct
    target = {k: v / total * scale for k, v in w.items()}

    # 调仓
    total_val = context.portfolio.total_value
    has_trade = False
    for code in ETF_CODE_LIST:
        df = attribute_history(code, 1, '1d', ['close'])
        if df is None or df.empty: continue
        price = float(df['close'].iloc[-1])
        if np.isnan(price) or price <= 0: continue

        want = total_val * target[code]
        pos = context.portfolio.positions.get(code)
        have = (pos.total_amount if pos else 0) * price
        diff = want - have

        if abs(diff) / total_val < 0.02: continue
        shares = int(diff / price / 100) * 100
        if shares == 0: continue

        try:
            order(code, shares)
            act = '买入' if shares > 0 else '卖出'
            log.info(f'{act} {ETF_NAME_DICT[code]} {abs(shares)}股 @ {price:.3f}')
            has_trade = True
        except Exception as e:
            log.error(f'下单失败 {code}: {e}')

    if not has_trade:
        log.info('持仓符合目标，无需调仓')
