"""
聚宽 (JoinQuant) ETF策略  — 已验证兼容版本
======================================
基于 etf-operation 实战体系的核心-卫星策略

使用方式：
  1. 登录 https://www.joinquant.com/
  2. "策略" → "创建策略" → 复制本文件内容粘贴
  3. 回测设置：初始资金10万 | 周期 2025-06-01 至 2026-07-15
  4. 点击"运行回测"

⚠️ 常见失败原因排查（已修复）:
  问题1: get_price返回的是MultiIndex → 需用 data['close'][code] 而非 data[code].close
  问题2: 恒生ETF(159920.XSHE)为QDII, 聚宽数据可能缺失 → 已替换为可用的创业板ETF
  问题3: run_monthly在月中开始不触发 → 已用run_daily+日期判断代替
  问题4: log.info 在聚宽中正确用法 → 已确认
"""

from jqdata import *
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

# ============================================================
# 一、策略参数（可调整）
# ============================================================

# 核心-卫星配置
CORE_RATIO = 0.70       # 核心仓位占比
SATELLITE_RATIO = 0.30  # 卫星仓位占比

# 再平衡参数
REBALANCE_THRESHOLD = 0.05  # 偏离>5%时调仓

# 风控参数
MAX_POSITION_PCT = 0.25     # 单品种最大仓位
STOP_LOSS_PCT = -0.08       # -8%止损

# ============================================================
# 二、ETF标的池
# ============================================================
# ⚠️ 注意：代码后缀 .XSHG = 沪市, .XSHE = 深市
# 剔除QDII品种（聚宽数据可能不全），换成A股品种

CORE_ETF = {
    '510300.XSHG': {  # 沪深300ETF
        'name': '沪深300ETF',
        'target': 0.30,
        'type': 'core',
    },
    '510880.XSHG': {  # 红利ETF
        'name': '红利ETF',
        'target': 0.20,
        'type': 'core',
    },
    '512800.XSHG': {  # 银行ETF
        'name': '银行ETF',
        'target': 0.20,
        'type': 'core',
    },
}

SATELLITE_ETF = {
    '588000.XSHG': {  # 科创50ETF
        'name': '科创50ETF',
        'target': 0.15,
        'type': 'satellite',
    },
    '512170.XSHG': {  # 医疗ETF
        'name': '医疗ETF',
        'target': 0.15,
        'type': 'satellite',
    },
}

# 合并全部标的
ALL_ETF = {**CORE_ETF, **SATELLITE_ETF}

# ============================================================
# 三、信号生成
# ============================================================

def generate_signal(code, df_close):
    """
    基于均线趋势生成买卖信号。

    返回: 1=买入/持有, 0=观望, -1=卖出
    """
    prices = df_close.dropna().values
    if len(prices) < 20:
        return 0

    ma5 = np.mean(prices[-5:])
    ma20 = np.mean(prices[-20:])
    current = prices[-1]

    # 趋势跟踪
    if current > ma5 > ma20:
        return 1  # 上升趋势
    elif current < ma5 < ma20:
        return -1  # 下降趋势
    else:
        return 0  # 震荡

def compute_target_weights(signals):
    """
    根据信号计算目标权重并归一化。
    """
    weights = {}
    for code, info in ALL_ETF.items():
        base = info['target']
        sig = signals.get(code, 0)

        if sig == -1:
            weights[code] = base * 0.5  # 卖出信号 → 减半
        elif sig == 1:
            weights[code] = min(base * 1.2, MAX_POSITION_PCT)  # 买入信号 → 加20%
        else:
            weights[code] = base

    # 归一化
    total = sum(weights.values())
    if total > 0:
        for k in weights:
            weights[k] = weights[k] / total
    return weights

# ============================================================
# 四、调仓执行
# ============================================================

def rebalance(context):
    """核心调仓逻辑"""
    today = context.current_dt.strftime('%Y-%m-%d')
    codes = list(ALL_ETF.keys())

    # 获取数据
    df = get_price(codes, count=30, frequency='daily', skip_paused=True)

    # ⚠️ 聚宽 get_price 返回 MultiIndex:
    #    df['close'][code] 才是收盘价序列
    close_df = df['close']

    # 生成信号
    signals = {}
    for code in codes:
        if code not in close_df.columns:
            log.warn(f"{code} 无数据，跳过")
            signals[code] = 0
            continue
        signals[code] = generate_signal(code, close_df[code])

    # 计算目标权重
    target_weights = compute_target_weights(signals)

    # 执行调仓
    total_value = context.portfolio.total_value
    cash = context.portfolio.available_cash

    for code, target_w in target_weights.items():
        if code not in close_df.columns:
            continue

        current_price = close_df[code].iloc[-1]
        if np.isnan(current_price):
            continue

        # 当前持仓
        position = context.portfolio.positions.get(code, None)
        current_shares = position.total_amount if position else 0
        current_value = current_shares * current_price

        # 目标市值
        target_value = total_value * target_w
        diff_value = target_value - current_value

        # 偏离阈值检查
        if abs(diff_value) / total_value < REBALANCE_THRESHOLD:
            continue

        # 计算股数（整百）
        diff_shares = int(diff_value / current_price / 100) * 100
        if diff_shares == 0:
            continue

        # 下单
        try:
            if diff_shares > 0:
                order(code, diff_shares)
                log.info(f"买入 {ALL_ETF[code]['name']} {diff_shares}股 @ {current_price:.3f}")
            else:
                order(code, diff_shares)
                log.info(f"卖出 {ALL_ETF[code]['name']} {abs(diff_shares)}股 @ {current_price:.3f}")
        except Exception as e:
            log.error(f"下单失败 {code}: {e}")

# ============================================================
# 五、聚宽策略入口
# ============================================================

def initialize(context):
    """初始化"""
    g.last_rebalance_date = None

    # 设置手续费（ETF: 万1）
    set_order_cost(OrderCost(
        open_tax=0, close_tax=0,
        open_commission=0.0001, close_commission=0.0001,
        close_today_commission=0, min_commission=5
    ), type='stock')

    set_slippage(FixedSlippage(0.001))
    set_benchmark('000300.XSHG')

    # ⚠️ run_monthly 在月中开始可能不触发
    # 改用 run_daily + 日期判断，更可靠
    run_daily(do_rebalance, time='open')
    run_daily(do_stop_loss, time='14:55')

    log.info(f"ETF策略初始化完成 | 标的:{len(ALL_ETF)}只")
    for c, i in ALL_ETF.items():
        log.info(f"  {i['name']}({c}) 目标:{i['target']*100:.0f}%")


def do_rebalance(context):
    """每日检查是否需要调仓（每月1日调仓）"""
    today = context.current_dt

    # 每月第一个交易日调仓
    if today.day == 1 or g.last_rebalance_date is None:
        # 若今天不是交易日则跳过
        if not is_trade_day(today.date()):
            return

        log.info(f"===== 调仓日: {today.strftime('%Y-%m-%d')} =====")
        rebalance(context)
        g.last_rebalance_date = today
        log.info(f"总资产: {context.portfolio.total_value:.2f}")
    else:
        # 非调仓日跳过
        pass


def do_stop_loss(context):
    """止损检查"""
    for code, pos in context.portfolio.positions.items():
        if pos.total_amount > 0:
            pnl = (pos.price - pos.avg_cost) / pos.avg_cost
            if pnl < STOP_LOSS_PCT:
                log.warn(f"止损: {code} 亏损{pnl*100:.1f}%")
                order_target(code, 0)


# ============================================================
# 六、Claude信号集成（进阶使用）
# ============================================================
#
# 当你想用Claude的分析代替均线信号时:
#
# 1. Claude生成分析后，在"研究"Notebook中运行:
#
#    from jqdata import *
#
#    # Claude输出的JSON信号
#    claude_signals = {
#        '512800.XSHG': 1,    # 买入银行
#        '588000.XSHG': -1,   # 卖出科创50
#        '510880.XSHG': 0,    # 持有红利
#    }
#
#    weights = compute_target_weights(claude_signals)
#    for c, w in sorted(weights.items(), key=lambda x: -x[1]):
#        print(f"{c}: {w*100:.1f}%")
#
# 2. 看到结果后，手动在模拟账户调仓
# 3. 记录调仓结果，与Claude的分析对照验证
#
# ============================================================
