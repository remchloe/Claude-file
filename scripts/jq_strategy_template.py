"""
聚宽 ETF 策略 — v12 多策略投票版
====================================
与v11的区别：
  - 新增三策略投票机制（取代单信号模式）
  - 主策略(Claude宏观) 权重70%
  - 技术策略(均线动量) 权重20%
  - 环境策略(市场分类器) 权重10%
  - 三策略投票决定最终方向和仓位

使用方式不变：每天复制Claude报告底部的SIGNAL → 粘贴下面 → 保存 ✅
"""

from jqdata import *
import numpy as np

# ================================================================
# ★ 每日更新区
# ================================================================
SIGNAL = {
    "date": "2026-07-16",
    "market_phase": "分化震荡 长鑫申购日+CPI降温+美伊冲突",
    "signals": {
        "510300.XSHG": 0,
        "510880.XSHG": 1,
        "512800.XSHG": 1,
        "588000.XSHG": -1,
        "512170.XSHG": 1,
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


# ================================================================
# 市场环境分类器
# ================================================================

def classify_regime(price_dict):
    """
    判断市场环境，返回自适应参数。
    """
    if not price_dict:
        return "range", {1: 1.2, 0: 1.0, -1: 0.5}, 0.0, "数据不足"

    rets = {}
    for code, arr in price_dict.items():
        if len(arr) >= 20:
            rets[code] = (float(arr[-1]) - float(arr[-20])) / float(arr[-20]) * 100

    if not rets:
        return "range", {1: 1.2, 0: 1.0, -1: 0.5}, 0.0, "数据不足"

    avg_ret = float(np.mean(list(rets.values())))
    dispersion = float(np.std(list(rets.values())))
    pct_pos = sum(1 for r in rets.values() if r > 0) / len(rets)
    pct_strong = sum(1 for r in rets.values() if abs(r) > 5) / len(rets)

    if dispersion > 4.0 and pct_strong > 0.3:
        return "divergent", {1: 1.15, 0: 1.0, -1: 0.55}, 0.05, \
               "分化(离散%.0f) 各走各路" % dispersion

    if avg_ret > 3.0 and pct_pos > 0.6:
        return "uptrend", {1: 1.3, 0: 1.0, -1: 0.6}, -0.05, \
               "上涨(均%+.0f%%) 让利润跑" % avg_ret

    if avg_ret < -3.0 and pct_pos < 0.4:
        return "downtrend", {1: 1.0, 0: 0.85, -1: 0.4}, 0.10, \
               "下跌(均%+.0f%%) 现金为王" % avg_ret

    return "range", {1: 1.1, 0: 1.0, -1: 0.6}, 0.0, \
           "震荡(均%+.0f%% 离散%.0f)" % (avg_ret, dispersion)


def ma_signals():
    """均线交叉备选信号"""
    sig = {}
    for code in ETF_CODE_LIST:
        df = attribute_history(code, 20, '1d', ['close'])
        if df is None or len(df) < 20:
            sig[code] = 0
        else:
            v = df['close'].values
            ma5, ma20 = float(v[-5:].mean()), float(v[-20:].mean())
            cur = float(v[-1])
            sig[code] = 1 if cur > ma5 > ma20 else (-1 if cur < ma5 < ma20 else 0)
    return sig


# ================================================================
# 策略入口
# ================================================================

def initialize(context):
    set_order_cost(OrderCost(0, 0, 0.0001, 0.0001, 0, 5), type='stock')
    set_slippage(FixedSlippage(0.001))
    set_benchmark('000300.XSHG')
    run_daily(daily_run, time='open')


def daily_run(context):
    # ---- 第1步：获取价格数据 ----
    price_dict = {}
    for code in ETF_CODE_LIST:
        df = attribute_history(code, 25, '1d', ['close'])
        if df is not None and len(df) >= 20:
            price_dict[code] = df['close'].values

    # ---- 第2步：收集三策略独立信号 ----
    # 策略1（权重70%）：Claude宏观信号
    sig1 = SIGNAL.get('signals', {})
    has_signal = len(sig1) > 0

    # 策略2（权重20%）：均线动量信号
    sig2 = ma_signals()

    # 策略3（权重10%）：环境分类器信号
    regime, env_mult, env_cash, env_desc = classify_regime(price_dict)
    log.info('市场环境: ' + env_desc)

    sig3 = {}
    for code in ETF_CODE_LIST:
        if regime == 'uptrend':
            sig3[code] = 1
        elif regime == 'downtrend':
            sig3[code] = -1
        else:
            sig3[code] = 0

    # ---- 第3步：三策略加权投票 ----
    if not has_signal:
        log.info('无SIGNAL，降级为技术策略(80%)+环境策略(20%)')
        sig1 = {k: 0 for k in ETF_CODE_LIST}
        w1, w2, w3 = 0.0, 0.80, 0.20
    else:
        log.info('三策略投票 | ' + str(SIGNAL.get('date','')))
        w1, w2, w3 = 0.70, 0.20, 0.10

    final_sig = {}
    for code in ETF_CODE_LIST:
        vote = sig1.get(code, 0) * w1 + sig2.get(code, 0) * w2 + sig3.get(code, 0) * w3
        if vote > 0.3:
            final_sig[code] = 1
        elif vote < -0.3:
            final_sig[code] = -1
        else:
            final_sig[code] = 0

    for code in ETF_CODE_LIST:
        log.info('  %s: 宏观=%d 技术=%d 环境=%d -> 最终=%d' %
                 (ETF_NAME_DICT[code], sig1.get(code,0), sig2.get(code,0), sig3.get(code,0), final_sig[code]))

    # ---- 第4步：权重计算 ----
    cash_pct = SIGNAL.get('cash_pct', 0.10) + env_cash
    cash_pct = max(0.05, min(0.30, cash_pct))

    w = {}
    for code in ETF_CODE_LIST:
        s = final_sig.get(code, 0)
        w[code] = min(ETF_BASE_WEIGHT[code] * env_mult.get(s, 1.0), 0.35)

    total = 0.0
    for v in w.values():
        total += v
    if total <= 0.0:
        return
    scale = 1.0 - cash_pct
    target = {k: v / total * scale for k, v in w.items()}

    log.info('  现金=%d%%' % (cash_pct * 100))

    # ---- 第5步：调仓 ----
    total_val = context.portfolio.total_value
    has_trade = False
    for code in ETF_CODE_LIST:
        if code not in price_dict:
            continue
        price = float(price_dict[code][-1])
        if np.isnan(price) or price <= 0:
            continue

        want = total_val * target[code]
        pos = context.portfolio.positions.get(code)
        have = (pos.total_amount if pos else 0) * price
        diff = want - have

        if abs(diff) / total_val < 0.02:
            continue
        shares = int(diff / price / 100) * 100
        if shares == 0:
            continue

        try:
            order(code, shares)
            act = '买入' if shares > 0 else '卖出'
            log.info('%s %s %d股 @ %.3f' % (act, ETF_NAME_DICT[code], abs(shares), price))
            has_trade = True
        except Exception as e:
            log.error('下单失败 %s: %s' % (code, str(e)))

    if not has_trade:
        log.info('持仓符合目标，无需调仓')
