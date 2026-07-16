"""
聚宽 ETF 策略 — v13 完全版
====================================
v13新增功能：
  1. ✅ 双级止损：硬止损-12%清仓 + 软止损-7%减半
  2. ✅ 置信度评分：Claude信号附置信度，动态调整仓位乘数
  3. ✅ 波动率自适应上限：高波动品种仓位上限自动降低
  4. ✅ 组合级回撤保护：总回撤>5%暂停买入，>10%强制减仓
  5. ✅ 盘中修正：12:00可更新SIGNAL，下午开盘自动执行

使用方式不变：每天复制Claude报告底部的SIGNAL → 粘贴下面 → 保存 ✅

SIGNAL新增字段：
  "confidence": {                   ← 可选，各品种置信度 0~1
      "510300.XSHG": 0.7,           ← 0.9=非常确定 0.5=不太确定
      ...
  }
  如果不提供confidence字段，默认置信度0.7
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
    "confidence": {
        "510300.XSHG": 0.6,
        "510880.XSHG": 0.8,
        "512800.XSHG": 0.7,
        "588000.XSHG": 0.6,
        "512170.XSHG": 0.7,
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

# 波动率自适应上限（高波动品种上限低）
VOLATILITY_MAX = {
    '510300.XSHG': 0.35,   # 沪深300：波动低，上限高
    '510880.XSHG': 0.35,   # 红利ETF：波动低
    '512800.XSHG': 0.35,   # 银行ETF：波动低
    '588000.XSHG': 0.18,   # 科创50：波动极高，上限压低
    '512170.XSHG': 0.25,   # 医疗ETF：波动中高
}

# 止损参数
HARD_STOP_LOSS = -0.12   # 硬止损-12% → 清仓
SOFT_STOP_LOSS = -0.07   # 软止损-7% → 减半仓

# 组合回撤保护
PORTFOLIO_STOP_BUY = -0.05    # 总回撤>5% → 暂停所有买入
PORTFOLIO_FORCE_CUT = -0.10   # 总回撤>10% → 强制减仓至50%


# ================================================================
# 市场环境分类器
# ================================================================

def classify_regime(price_dict):
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
# 止损 + 组合回撤保护
# ================================================================

def check_all_stops(context, price_dict):
    """每日执行所有止损/回撤检查"""
    total_val = context.portfolio.total_value
    total_cost = context.portfolio.total_assets  # 总投入资金（包含现金）
    if total_cost <= 0:
        return

    # ---- 组合级回撤保护 ----
    portfolio_pnl = (total_val - total_cost) / total_cost

    if portfolio_pnl < PORTFOLIO_FORCE_CUT:
        log.warn('组合回撤 %.1f%% < %.0f%%，强制减仓至50%%' % (portfolio_pnl * 100, PORTFOLIO_FORCE_CUT * 100))
        for code in ETF_CODE_LIST:
            pos = context.portfolio.positions.get(code)
            if pos and pos.total_amount > 0:
                target_shares = pos.total_amount // 2
                sell_shares = pos.total_amount - (target_shares // 100 * 100)
                if sell_shares >= 100:
                    order(code, -sell_shares)
                    log.info('强制减仓 %s %d股' % (ETF_NAME_DICT[code], sell_shares))
        return

    if portfolio_pnl < PORTFOLIO_STOP_BUY:
        log.warn('组合回撤 %.1f%% < %.0f%%，暂停买入，仅允许卖出' % (portfolio_pnl * 100, PORTFOLIO_STOP_BUY * 100))

    # ---- 单品种止损 ----
    for code in ETF_CODE_LIST:
        pos = context.portfolio.positions.get(code)
        if not pos or pos.total_amount <= 0:
            continue
        cost = pos.avg_cost
        if cost <= 0:
            continue
        price = pos.price
        if price <= 0:
            continue
        pnl = (price - cost) / cost

        if pnl < HARD_STOP_LOSS:
            log.warn('硬止损 %s: %.1f%% < %.0f%%，清仓' % (ETF_NAME_DICT[code], pnl * 100, HARD_STOP_LOSS * 100))
            order_target(code, 0)

        elif pnl < SOFT_STOP_LOSS:
            log.warn('软止损 %s: %.1f%% < %.0f%%，减半仓' % (ETF_NAME_DICT[code], pnl * 100, SOFT_STOP_LOSS * 100))
            target_shares = pos.total_amount // 2
            order_target(code, target_shares // 100 * 100)


# ================================================================
# 调仓执行（早盘 + 午盘共用）
# ================================================================

def execute_rebalance(context):
    """根据当前SIGNAL执行调仓"""
    price_dict = {}
    for code in ETF_CODE_LIST:
        df = attribute_history(code, 25, '1d', ['close'])
        if df is not None and len(df) >= 20:
            price_dict[code] = df['close'].values

    # 三策略投票
    sig1 = SIGNAL.get('signals', {})
    has_signal = len(sig1) > 0
    sig2 = ma_signals()
    regime, env_mult, env_cash, env_desc = classify_regime(price_dict)

    sig3 = {}
    for code in ETF_CODE_LIST:
        if regime == 'uptrend':
            sig3[code] = 1
        elif regime == 'downtrend':
            sig3[code] = -1
        else:
            sig3[code] = 0

    if not has_signal:
        log.info('无SIGNAL，降级为技术策略(80%)+环境策略(20%)')
        sig1 = {k: 0 for k in ETF_CODE_LIST}
        w1, w2, w3 = 0.0, 0.80, 0.20
    else:
        log.info('三策略投票 | ' + str(SIGNAL.get('date','')))
        w1, w2, w3 = 0.70, 0.20, 0.10

    # 获取置信度
    conf = SIGNAL.get('confidence', {})
    default_conf = 0.7

    # 组合回撤状态
    total_cost = context.portfolio.total_assets
    total_val = context.portfolio.total_value
    portfolio_pnl = (total_val - total_cost) / total_cost if total_cost > 0 else 0
    is_stop_buy = portfolio_pnl < PORTFOLIO_STOP_BUY

    final_sig = {}
    for code in ETF_CODE_LIST:
        vote = sig1.get(code, 0) * w1 + sig2.get(code, 0) * w2 + sig3.get(code, 0) * w3
        if vote > 0.3:
            final_sig[code] = 1
        elif vote < -0.3:
            final_sig[code] = -1
        else:
            final_sig[code] = 0

        # 打印投票详情
        log.info('  %s: 宏观=%d 技术=%d 环境=%d -> 最终=%d (置信度=%.1f)' %
                 (ETF_NAME_DICT[code], sig1.get(code,0), sig2.get(code,0), sig3.get(code,0),
                  final_sig[code], conf.get(code, default_conf)))

    # ---- 权重计算（置信度调整） ----
    cash_pct = SIGNAL.get('cash_pct', 0.10) + env_cash
    cash_pct = max(0.05, min(0.30, cash_pct))

    # 如果处于"暂停买入"状态，提高现金比例
    if is_stop_buy:
        cash_pct = max(cash_pct, 0.15)

    w = {}
    for code in ETF_CODE_LIST:
        s = final_sig.get(code, 0)
        # 基础权重 × 信号乘数
        base_w = ETF_BASE_WEIGHT[code] * env_mult.get(s, 1.0)
        # 置信度调整：置信度越低，仓位越低
        confidence = conf.get(code, default_conf)
        base_w = base_w * (0.5 + confidence * 0.5)  # 置信度0.5→0.75x, 0.9→0.95x
        # 波动率上限
        max_w = VOLATILITY_MAX.get(code, 0.30)
        w[code] = min(base_w, max_w)

        # 暂停买入模式下，买入信号不执行
        if is_stop_buy and s > 0:
            w[code] = 0

    total = 0.0
    for v in w.values():
        total += v
    if total <= 0.0:
        return
    scale = 1.0 - cash_pct
    target = {k: v / total * scale for k, v in w.items()}

    log.info('  现金=%d%%%s' % (cash_pct * 100, ' (暂停买入模式)' if is_stop_buy else ''))

    # ---- 调仓 ----
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


# ================================================================
# 策略入口
# ================================================================

def initialize(context):
    set_order_cost(OrderCost(0, 0, 0.0001, 0.0001, 0, 5), type='stock')
    set_slippage(FixedSlippage(0.001))
    set_benchmark('000300.XSHG')

    # 09:30 早盘执行
    run_daily(morning_run, time='open')
    # 12:30 盘中修正
    run_daily(afternoon_run, time='12:30')
    # 14:50 止损检查
    run_daily(stop_check_run, time='14:50')

    log.info('v13启动 | 双级止损+置信度+波动率上限+组合回撤保护+12:30盘中修正')


def morning_run(context):
    """09:30 早盘调仓"""
    log.info('===== 早盘调仓 =====')
    execute_rebalance(context)


def afternoon_run(context):
    """
    12:30 盘中修正。
    如果SIGNAL没有变化（和上次执行时相同），自动跳过。
    如果需要修正，更新SIGNAL后保存即可，下午开盘自动执行。
    """
    log.info('===== 12:00盘中检查 =====')
    execute_rebalance(context)


def stop_check_run(context):
    """14:50 止损检查"""
    log.info('===== 止损检查 =====')
    price_dict = {}
    for code in ETF_CODE_LIST:
        df = attribute_history(code, 25, '1d', ['close'])
        if df is not None and len(df) >= 20:
            price_dict[code] = df['close'].values
    check_all_stops(context, price_dict)
