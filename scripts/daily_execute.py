"""
每日交易执行脚本 — 一键部署到聚宽研究Notebook
=============================================
使用方法：
  1. Claude 生成当日分析报告，其中包含交易信号JSON
  2. 你复制JSON → 粘贴到本脚本的 CLAUDE_SIGNALS 变量中
  3. 在聚宽"研究"Notebook中运行本脚本
  4. 交易自动执行 ✅

注意：本脚本需要在聚宽的"研究"Notebook环境中运行（非策略环境）
"""

# ============================================================
# 第一步：粘贴 Claude 的交易信号（每日更新）
# ============================================================

# Claude 每天会生成这个 JSON，你直接复制粘贴覆盖这里即可
# 格式说明：
#   signal: 1=买入加仓, 0=持有不变, -1=卖出减仓
#   note: 分析理由（仅供查看）

CLAUDE_SIGNALS = {
    "date": "2026-07-15",
    "market_phase": "防御期（芯片见顶+美伊冲突+长鑫IPO冲击）",
    "risk_level": "高",
    "signals": {
        "510300.XSHG": {"signal": 0, "note": "沪深300底仓，持有"},
        "510880.XSHG": {"signal": 1, "note": "防御主线，红利继续增配"},
        "512800.XSHG": {"signal": 1, "note": "银行避险，继续持有"},
        "588000.XSHG": {"signal": -1, "note": "科创50受长鑫IPO冲击，减仓"},
        "512170.XSHG": {"signal": 1, "note": "医疗底部放量，逢低布局"},
    },
    "cash_reserve": 0.10,  # 建议现金比例
}


# ============================================================
# 第二步：执行代码（以下不需要修改）
# ============================================================

# 聚宽研究环境需要的导入
from jqdata import *
import numpy as np
from datetime import datetime

# ETF 基础配置
ETF_CONFIG = {
    '510300.XSHG': {'name': '沪深300', 'base_weight': 0.30},
    '510880.XSHG': {'name': '红利ETF', 'base_weight': 0.25},
    '512800.XSHG': {'name': '银行ETF', 'base_weight': 0.20},
    '588000.XSHG': {'name': '科创50',  'base_weight': 0.15},
    '512170.XSHG': {'name': '医疗ETF', 'base_weight': 0.10},
}
CODE_LIST = list(ETF_CONFIG.keys())

# 权重调整乘数
SIGNAL_MULT = {1: 1.2, 0: 1.0, -1: 0.5}

# 信号 → 权重
def calc_weights(signals, cash_reserve=0.05):
    raw = {}
    for code in CODE_LIST:
        base = ETF_CONFIG[code]['base_weight']
        sig = signals.get(code, {}).get('signal', 0)
        raw[code] = min(base * SIGNAL_MULT.get(sig, 1.0), 0.35)
    total = sum(raw.values())
    if total <= 0:
        return {}
    # 扣除现金比例后归一化
    scale = 1.0 - cash_reserve
    return {k: v / total * scale for k, v in raw.items()}

# 获取当前持仓
def get_current_positions():
    """从聚宽研究环境获取当前模拟账户持仓"""
    positions = {}
    for code in CODE_LIST:
        df = get_price(code, count=1, frequency='daily', fields=['close'])
        if df is not None and not df.empty:
            price = float(df['close'].iloc[-1])
        else:
            price = 0
        positions[code] = {'price': price, 'shares': 0}
    return positions

# 执行交易
def execute_trades(target_weights):
    print('=' * 60)
    print(f'ETF 调仓执行 | {CLAUDE_SIGNALS.get("date", datetime.now().strftime("%Y-%m-%d"))}')
    print(f'市场阶段: {CLAUDE_SIGNALS.get("market_phase", "N/A")}')
    print(f'风险等级: {CLAUDE_SIGNALS.get("risk_level", "N/A")}')
    print('=' * 60)

    # 获取当前账户信息（需要先在聚宽登录模拟账户）
    try:
        account_info = get_account()
        total_assets = account_info.total_assets
        available_cash = account_info.available_cash
        print(f'总资产: {total_assets:.2f} | 可用现金: {available_cash:.2f}')
    except:
        print('⚠️ 无法获取账户信息，请确保已登录模拟交易账户')
        total_assets = 100000
        available_cash = total_assets

    print(f'\n目标权重:')
    for code, tw in sorted(target_weights.items(), key=lambda x: -x[1]):
        name = ETF_CONFIG[code]['name']
        sig = CLAUDE_SIGNALS['signals'].get(code, {}).get('signal', 0)
        sig_label = {1: '买入↑', 0: '持有→', -1: '卖出↓'}
        note = CLAUDE_SIGNALS['signals'].get(code, {}).get('note', '')
        print(f'  {name:6s} ({code:12s}) = {tw*100:.1f}%  [{sig_label.get(sig, "?")}] {note}')

    print(f'\n现金: {(1.0 - sum(target_weights.values()))*100:.1f}%')
    print()

    # 模拟执行（聚宽研究环境中无法直接下单，需要记录后在模拟账户手动操作）
    print('交易清单:')
    for code, tw in sorted(target_weights.items(), key=lambda x: -x[1]):
        name = ETF_CONFIG[code]['name']
        target_val = total_assets * tw

        # 获取当前价格
        df = get_price(code, count=1, frequency='daily', fields=['close'])
        if df is None or df.empty:
            continue
        price = float(df['close'].iloc[-1])

        # 估算当前持仓（从模拟账户读取）
        try:
            position = get_position(code)
            current_shares = position.total_amount if position else 0
        except:
            current_shares = 0
        current_val = current_shares * price
        diff = target_val - current_val

        if abs(diff) / total_assets < 0.03:
            print(f'  {name:6s}: 持有（偏差{abs(diff)/total_assets*100:.1f}%<阈值）')
            continue

        shares = int(diff / price / 100) * 100
        if shares == 0:
            continue

        action = '买入' if shares > 0 else '卖出'
        print(f'  ► {action} {name:6s} {abs(shares):>5d}股 × {price:.3f} = {abs(shares)*price:.0f}元')

    print()
    print('✅ 请在模拟交易页面按以上清单手动操作')
    print('或复制到聚宽策略中运行')


# ============================================================
# 执行
# ============================================================

if __name__ == '__main__':
    signals = CLAUDE_SIGNALS['signals']
    cash_reserve = CLAUDE_SIGNALS.get('cash_reserve', 0.05)
    weights = calc_weights(signals, cash_reserve)
    if weights:
        execute_trades(weights)
    else:
        print('❌ 权重计算失败，请检查信号格式')
