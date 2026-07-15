"""
聚宽 (JoinQuant) ETF策略模板
=======================
基于 etf-operation 实战体系的核心-卫星策略

使用方式：
  1. 登录 https://www.joinquant.com/
  2. 进入"策略" → "创建策略"
  3. 复制本文件内容粘贴
  4. 运行回测 → 模拟交易

初始资金建议: 100,000 (10万)
回测周期建议: 2025-01-01 至 2026-07-15
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
CASH_RATIO = 0.05       # 最低现金比例

# 再平衡参数
REBALANCE_THRESHOLD = 0.05  # 单资产偏离>5%时再平衡
REBALANCE_MIN_DAYS = 5      # 最小再平衡间隔（交易日）

# 风控参数
MAX_POSITION_PCT = 0.25     # 单品种最大仓位
MAX_DAILY_TURNOVER = 0.20   # 单日最大换手率
STOP_LOSS_PCT = -0.08       # 个股止损线（-8%）

# ============================================================
# 二、ETF标的池
# ============================================================

# 核心仓位标的（防御型）
CORE_ETF = {
    '510300.XSHG': {  # 沪深300ETF
        'name': '沪深300ETF',
        'target': 0.25,
        'type': 'core',
    },
    '510880.XSHG': {  # 红利ETF
        'name': '红利ETF',
        'target': 0.20,
        'type': 'core',
    },
    '512800.XSHG': {  # 银行ETF
        'name': '银行ETF',
        'target': 0.15,
        'type': 'core',
    },
    '159920.XSHE': {  # 恒生ETF
        'name': '恒生ETF',
        'target': 0.10,
        'type': 'core',
    },
}

# 卫星仓位标的（进攻型）
SATELLITE_ETF = {
    '588000.XSHG': {  # 科创50ETF
        'name': '科创50ETF',
        'target': 0.15,
        'type': 'satellite',
    },
    '513130.XSHG': {  # 恒生科技ETF
        'name': '恒生科技ETF',
        'target': 0.10,
        'type': 'satellite',
    },
    '512170.XSHG': {  # 医疗ETF
        'name': '医疗ETF',
        'target': 0.05,
        'type': 'satellite',
    },
}

# 全部标的合并
ALL_ETF = {**CORE_ETF, **SATELLITE_ETF}

# ============================================================
# 三、信号生成模块（核心分析逻辑）
# ============================================================

def generate_signals(context, data):
    """
    基于 etf-operation 框架生成交易信号。
    
    这是Claude分析的核心输出点——在模拟阶段，
    这个函数可以用Claude的分析结果来手动填充。
    
    返回: dict {etf_code: signal}
        signal: 1=买入, 0=持有, -1=卖出
    """
    signals = {}
    
    # ---- 这里在模拟阶段可以由Claude分析结果替代 ----
    # ---- 以下是一个基于均线策略的示例 ----
    
    for code in ALL_ETF:
        # 获取近20日收盘价
        close_prices = data[code].close
        if len(close_prices) < 20:
            signals[code] = 0
            continue
        
        # 计算均线
        ma5 = np.mean(close_prices[-5:])
        ma20 = np.mean(close_prices[-20:])
        current_price = close_prices[-1]
        
        # 简单的趋势跟踪信号
        if current_price > ma5 > ma20:
            # 上升趋势 → 买入或持有
            signals[code] = 1
        elif current_price < ma5 < ma20:
            # 下降趋势 → 卖出
            signals[code] = -1
        else:
            # 震荡 → 持有
            signals[code] = 0
    
    return signals


def get_claude_signals_from_json(json_str):
    """
    从Claude的分析输出中解析交易信号。
    
    Claude输出格式示例：
    {
        "signals": {
            "512480.XSHG": {"action": "sell", "reason": "芯片见顶确认"},
            "512800.XSHG": {"action": "buy", "reason": "避险资金流入"},
            "510880.XSHG": {"action": "hold", "reason": "防御配置"}
        },
        "market_phase": "防御期",
        "risk_level": "高",
        "core_weight_adjustment": {"510880.XSHG": 0.25}
    }
    
    参数:
        json_str: Claude输出的JSON字符串
    返回:
        dict {code: signal}
    """
    import json
    try:
        claude_output = json.loads(json_str)
        signals = {}
        action_map = {'buy': 1, 'hold': 0, 'sell': -1}
        for code, info in claude_output.get('signals', {}).items():
            signals[code] = action_map.get(info.get('action', 'hold'), 0)
        return signals
    except:
        # 解析失败，返回空信号
        return {}


# ============================================================
# 四、仓位计算模块
# ============================================================

def calculate_target_weights(context, signals):
    """
    根据信号计算目标权重。
    """
    weights = {}
    
    # 基础权重（从配置中获取）
    for code, info in ALL_ETF.items():
        weights[code] = info['target']
    
    # 根据信号调整权重
    for code, signal in signals.items():
        if code not in weights:
            continue
        
        if signal == -1:  # 卖出信号
            weights[code] = weights[code] * 0.5  # 减半
        elif signal == 1:  # 买入信号
            weights[code] = min(weights[code] * 1.2, MAX_POSITION_PCT)  # 加20%
        # signal==0不调整
    
    # 归一化确保总和=1
    total = sum(weights.values())
    if total > 0:
        for code in weights:
            weights[code] = weights[code] / total
    
    return weights


# ============================================================
# 五、交易执行模块
# ============================================================

def execute_trades(context, data, target_weights):
    """
    根据目标权重执行调仓。
    """
    current_positions = context.portfolio.positions
    total_value = context.portfolio.total_value
    available_cash = context.portfolio.available_cash
    
    for code, target_weight in target_weights.items():
        # 计算目标市值
        target_value = total_value * target_weight
        current_value = current_positions[code].total_amount if code in current_positions else 0
        diff_value = target_value - current_value
        
        # 如果偏差小于阈值，不交易
        if abs(diff_value) / total_value < REBALANCE_THRESHOLD:
            continue
        
        # 获取当前价格
        current_price = data[code].close
        if np.isnan(current_price):
            continue
        
        # 计算交易数量（按100的整数倍）
        diff_shares = int(diff_value / current_price / 100) * 100
        if diff_shares == 0:
            continue
        
        # 执行交易
        if diff_shares > 0:
            # 买入
            order_value = diff_shares * current_price
            if order_value <= available_cash:
                order(code, diff_shares)
                log.info(f"买入 {ALL_ETF[code]['name']}({code}): {diff_shares}股, 约{order_value:.0f}元")
        else:
            # 卖出
            order(code, diff_shares)
            log.info(f"卖出 {ALL_ETF[code]['name']}({code}): {abs(diff_shares)}股, 约{abs(order_value):.0f}元")


# ============================================================
# 六、聚宽策略入口
# ============================================================

def initialize(context):
    """初始化策略"""
    # 设置ETF标的
    g.etf_codes = list(ALL_ETF.keys())
    
    # 设置手续费（ETF万1）
    set_order_cost(OrderCost(open_tax=0, close_tax=0, 
                             open_commission=0.0001, close_commission=0.0001,
                             close_today_commission=0, min_commission=5), 
                   type='stock')
    
    # 设置滑点
    set_slippage(FixedSlippage(0.001))
    
    # 设置基准
    set_benchmark('000300.XSHG')
    
    # 按月调仓
    run_monthly(monthly_rebalance, 1, time='open')
    
    # 每日检查止损
    run_daily(check_stop_loss, time='14:50')
    
    log.info(f"策略初始化完成: 标的数量={len(g.etf_codes)}")
    log.info(f"核心仓位目标={CORE_RATIO*100:.0f}%, 卫星仓位={SATELLITE_RATIO*100:.0f}%")


def monthly_rebalance(context):
    """每月调仓"""
    current_date = context.current_dt.strftime('%Y-%m-%d')
    log.info(f"===== 月度调仓: {current_date} =====")
    
    # 获取历史数据
    data = get_price(g.etf_codes, count=30, frequency='daily')
    
    # 生成信号（这里将来可以用Claude的分析结果替换）
    signals = generate_signals(context, data)
    
    # 计算目标权重
    target_weights = calculate_target_weights(context, signals)
    
    # 执行交易
    execute_trades(context, data, target_weights)
    
    # 记录当前仓位
    log.info(f"当前总资产: {context.portfolio.total_value:.2f}")
    log.info(f"可用现金: {context.portfolio.available_cash:.2f}")


def check_stop_loss(context):
    """每日止损检查"""
    for code, position in context.portfolio.positions.items():
        if position.total_amount > 0:
            cost = position.avg_cost
            current = position.price
            pnl_pct = (current - cost) / cost
            
            if pnl_pct < STOP_LOSS_PCT:
                log.warn(f"触发止损: {code} 亏损{pnl_pct*100:.1f}%")
                order_target(code, 0)


# ============================================================
# 七、手动信号入口（用于接收Claude分析）
# ============================================================

def apply_claude_signal(context, data):
    """
    手动调用：将Claude的分析结果应用到策略中。
    
    使用方法：
        1. Claude生成当日的ETF分析报告
        2. 从报告中提取交易信号（见get_claude_signals_from_json）
        3. 在聚宽"研究"Notebook中运行此函数
        4. 策略自动调仓
    
    示例代码（在聚宽Notebook中运行）：
    
    ```python
    from jqdata import *
    
    # Claude的分析输出（JSON格式）
    claude_json = '''
    {
        "signals": {
            "512480.XSHG": {"action": "sell", "reason": "芯片见顶确认"},
            "512800.XSHG": {"action": "buy", "reason": "防御配置"}
        },
        "risk_level": "high",
        "market_phase": "defensive"
    }
    '''
    
    # 获取信号
    signals = get_claude_signals_from_json(claude_json)
    
    # 计算权重
    weights = calculate_target_weights(None, signals)
    
    # 查看结果
    for code, weight in sorted(weights.items(), key=lambda x: -x[1]):
        info = ALL_ETF.get(code, {})
        print(f"{info.get('name','')} ({code}): {weight*100:.1f}%")
    ```
    """
    pass


# ============================================================
# 八、回测结果分析（在聚宽Notebook中运行）
# ============================================================

"""
回测后分析代码（复制到聚宽研究Notebook中运行）：

```python
# 获取回测结果
from jqdata import *
from pandas import DataFrame

# 查看策略绩效
perf = get_performance()
print(f"年化收益: {perf.annualized_returns*100:.2f}%")
print(f"最大回撤: {perf.max_drawdown*100:.2f}%")
print(f"夏普比率: {perf.sharpe_ratio:.2f}")
print(f"胜率: {perf.win_rate*100:.1f}%")
print(f"交易次数: {perf.total_trades}")
```
"""
