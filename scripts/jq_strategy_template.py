"""
聚宽 ETF 策略 — v10 外部信号读取版
====================================
不再需要每天修改策略代码！
你只需要每天上传一个 signal_YYYYMMDD.json 文件到聚宽就行。

工作流程：
  08:00  Claude 生成分析 → 同时输出 signal_20260715.json
  08:30  你打开聚宽"研究"Notebook → 上传json文件（拖拽即可）
  09:30  策略自动读取最新信号文件 → 自动调仓 ✅

  如果当天忘了上传信号文件 → 策略使用均线备选（不会空转）
"""

from jqdata import *
import numpy as np
import json
import os

# ---- ETF配置 ----
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
SIGNAL_MULT = {1: 1.2, 0: 1.0, -1: 0.5}


def initialize(context):
    set_order_cost(OrderCost(0, 0, 0.0001, 0.0001, 0, 5), type='stock')
    set_slippage(FixedSlippage(0.001))
    set_benchmark('000300.XSHG')
    run_daily(daily_run, time='open')
    log.info('v10启动 | 每日自动读取信号文件 | 上传json即可')


def read_signal():
    """
    读取最新的信号文件。
    搜索 Research 目录下的 signal_*.json 文件，取最新的。
    """
    # 优先读取聚宽研究环境的共享数据目录
    search_dirs = [
        '/home/jquser/upload/',
        '/home/jquser/Research/',
        '/home/jquser/',
        '/tmp/',
        './',
    ]
    for d in search_dirs:
        try:
            files = [f for f in os.listdir(d) if f.startswith('signal_') and f.endswith('.json')]
            if not files:
                continue
            latest = sorted(files)[-1]  # 取最新的
            path = os.path.join(d, latest)
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            log.info(f'读取信号文件: {latest}')
            return data
        except:
            continue
    return None


def gen_signals():
    """读取信号文件 → 返回信号字典"""
    data = read_signal()
    if data and len(data.get('signals', {})) > 0:
        log.info(f'使用外部信号 | {data.get("date","")} | {data.get("market_phase","")}')
        return data['signals'], data.get('cash_pct', 0.05)

    # 备选：均线信号
    log.info('无信号文件，使用均线备选')
    sig = {}
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
    return sig, 0.05


def daily_run(context):
    """每日调仓检查"""
    signals, cash_pct = gen_signals()

    # 权重计算
    w = {}
    for code in ETF_CODE_LIST:
        base = ETF_BASE_WEIGHT[code]
        s = signals.get(code, 0)
        w[code] = min(base * SIGNAL_MULT.get(s, 1.0), 0.35)

    total = sum(w.values())
    if total <= 0:
        return
    scale = 1.0 - cash_pct
    target = {k: v / total * scale for k, v in w.items()}

    # 调仓
    total_val = context.portfolio.total_value
    has_trade = False

    for code in ETF_CODE_LIST:
        df = attribute_history(code, 1, '1d', ['close'])
        if df is None or df.empty:
            continue
        price = float(df['close'].iloc[-1])
        if np.isnan(price) or price <= 0:
            continue

        want = total_val * target[code]
        pos = context.portfolio.positions.get(code)
        have_shares = pos.total_amount if pos else 0
        have = have_shares * price
        diff = want - have

        if abs(diff) / total_val < 0.02:
            continue

        shares = int(diff / price / 100) * 100
        if shares == 0:
            continue

        try:
            order(code, shares)
            act = '买入' if shares > 0 else '卖出'
            log.info(f'{act} {ETF_NAME_DICT[code]} {abs(shares)}股 @ {price:.3f}')
            has_trade = True
        except Exception as e:
            log.error(f'下单失败 {code}: {e}')

    if not has_trade:
        log.info('当前持仓符合目标，无需调仓')
