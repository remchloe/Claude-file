"""
聚宽 ETF 策略 — v7 极限容错版
====================================
改动：避免所有可能的环境兼容性问题
- 不用 dict.values() + sum() 改用手动累加
- 所有变量名避开常用关键字
- 只用 attribute_history 逐个取数据

使用方法：
  1. 全部删除旧代码，粘贴本文件全部内容
  2. 回测：10万 | 2025-07-01 至 2026-07-15
  3. 运行
"""

from jqdata import *
import numpy as np

# ETF配置
ETF_CODE_LIST = ['510300.XSHG', '510880.XSHG', '512800.XSHG', '588000.XSHG', '512170.XSHG']
ETF_NAME_DICT = {
    '510300.XSHG': '沪深300',
    '510880.XSHG': '红利ETF',
    '512800.XSHG': '银行ETF',
    '588000.XSHG': '科创50',
    '512170.XSHG': '医疗ETF',
}
ETF_TARGET_DICT = {
    '510300.XSHG': 0.30,
    '510880.XSHG': 0.25,
    '512800.XSHG': 0.20,
    '588000.XSHG': 0.15,
    '512170.XSHG': 0.10,
}


def initialize(context):
    set_order_cost(OrderCost(0, 0, 0.0001, 0.0001, 0, 5), type='stock')
    set_slippage(FixedSlippage(0.001))
    set_benchmark('000300.XSHG')
    run_monthly(rebalance, 1, time='open')
    log.info('ETF策略启动 | 5只标的')


def rebalance(context):
    if context.current_dt.day != 1:
        return

    # ---- 第一步：逐一获取数据 ----
    # price_map: code -> 最近30个收盘价的数组
    price_map = {}
    for code in ETF_CODE_LIST:
        df = attribute_history(code, 30, '1d', ['close'])
        if df is None or len(df) < 20:
            continue
        price_map[code] = df['close'].values

    # ---- 第二步：生成信号 ----
    # sig_map: code -> 1(买入)/0(持有)/-1(卖出)
    sig_map = {}
    for code in ETF_CODE_LIST:
        arr = price_map.get(code)
        if arr is None:
            sig_map[code] = 0
            continue
        ma5_val = float(arr[-5:].mean())
        ma20_val = float(arr[-20:].mean())
        cur_val = float(arr[-1])
        if cur_val > ma5_val > ma20_val:
            sig_map[code] = 1
        elif cur_val < ma5_val < ma20_val:
            sig_map[code] = -1
        else:
            sig_map[code] = 0

    # ---- 第三步：计算权重 ----
    # 先算原始加权值
    w_map = {}
    for code in ETF_CODE_LIST:
        base_w = ETF_TARGET_DICT[code]
        s = sig_map.get(code, 0)
        if s == -1:
            w_map[code] = base_w * 0.5
        elif s == 1:
            w_map[code] = base_w * 1.2
        else:
            w_map[code] = base_w
        if w_map[code] > 0.30:
            w_map[code] = 0.30

    # 手动累加（避免 sum(dict.values()) 的环境兼容性问题）
    w_total = 0.0
    for code in ETF_CODE_LIST:
        w_total += w_map[code]

    if w_total <= 0.0:
        return

    # 归一化
    target_map = {}
    for code in ETF_CODE_LIST:
        target_map[code] = w_map[code] / w_total

    # ---- 第四步：执行调仓 ----
    total_assets = context.portfolio.total_value
    for code in ETF_CODE_LIST:
        if code not in price_map:
            continue
        cur_price = float(price_map[code][-1])
        if np.isnan(cur_price) or cur_price <= 0:
            continue

        want_val = total_assets * target_map[code]
        pos_obj = context.portfolio.positions.get(code)
        have_shares = pos_obj.total_amount if pos_obj else 0
        have_val = have_shares * cur_price
        diff_val = want_val - have_val

        if abs(diff_val) / total_assets < 0.05:
            continue

        trade_shares = int(diff_val / cur_price / 100) * 100
        if trade_shares == 0:
            continue

        try:
            order(code, trade_shares)
            action_word = '买入' if trade_shares > 0 else '卖出'
            log.info(f'{action_word} {ETF_NAME_DICT[code]} {abs(trade_shares)}股 @ {cur_price:.3f}')
        except Exception as e:
            log.error(f'下单失败 {code}: {e}')
