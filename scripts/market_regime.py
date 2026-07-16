"""
市场环境分类器 (Market Regime Classifier)
==========================================
用于判断当前市场处于什么环境，帮助策略自适应调整。

输出四种环境：
  1. 单边上涨 — 趋势强，ETF普涨 → 加仓持有，让利润奔跑
  2. 单边下跌 — 趋势强，ETF普跌 → 降仓避险，现金为王
  3. 震荡 — 无方向，来回波动 → 高抛低吸，波段操作
  4. 分化 — 有的涨有的跌（当前）→ 分品种独立判断

使用方式：
  from market_regime import classify_market, adapt_signal_mult
  
  # 获取当前市场环境
  regime, signal_mult, description = classify_market(price_data)
  # regime: "uptrend" / "downtrend" / "range" / "divergent"
  # signal_mult: 根据环境调整后的信号乘数（+1对应乘数）
  # description: 中文描述
"""

import numpy as np


def calc_adx(high, low, close, period=14):
    """
    计算 ADX (Average Directional Index)
    ADX > 25 = 趋势行情，ADX < 20 = 震荡行情
    """
    n = len(close)
    if n < period + 1:
        return 20.0  # 默认震荡

    # 计算方向变动
    tr = np.zeros(n)
    plus_dm = np.zeros(n)
    minus_dm = np.zeros(n)

    for i in range(1, n):
        tr[i] = max(high[i] - low[i],
                    abs(high[i] - close[i - 1]),
                    abs(low[i] - close[i - 1]))
        plus_dm[i] = max(high[i] - high[i - 1], 0) if (high[i] - high[i - 1]) > (low[i - 1] - low[i]) else 0
        minus_dm[i] = max(low[i - 1] - low[i], 0) if (low[i - 1] - low[i]) > (high[i] - high[i - 1]) else 0

    # 平滑
    atr = np.mean(tr[-period:])
    plus_smooth = np.mean(plus_dm[-period:])
    minus_smooth = np.mean(minus_dm[-period:])

    if atr == 0:
        return 20.0

    plus_di = 100 * plus_smooth / atr
    minus_di = 100 * minus_smooth / atr
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di) if (plus_di + minus_di) > 0 else 0

    return dx


def calc_dispersion(returns_dict):
    """
    计算离散度——各ETF收益率的标准差。
    离散度高 = 分化行情，离散度低 = 单边行情。
    """
    returns = list(returns_dict.values())
    if len(returns) < 3:
        return 0.0
    return float(np.std(returns))


def classify_market(price_data_dict, lookback=20):
    """
    市场环境分类主函数。
    
    参数:
        price_data_dict: {code: 最近N日收盘价数组}
        lookback: 回看天数
    
    返回:
        regime: "uptrend" / "downtrend" / "range" / "divergent"
        signal_mult_adjust: {+1: 乘数调整, -1: 乘数调整, 0: 乘数调整}
        description: 中文描述
    """
    if not price_data_dict:
        return "range", {1: 1.2, 0: 1.0, -1: 0.5}, "数据不足，默认震荡"

    # --- 1. 计算各ETF近期表现 ---
    returns = {}
    short_rets = {}
    for code, prices in price_data_dict.items():
        if len(prices) >= lookback:
            returns[code] = (prices[-1] - prices[-lookback]) / prices[-lookback] * 100
        if len(prices) >= 5:
            short_rets[code] = (prices[-1] - prices[-5]) / prices[-5] * 100

    if not returns:
        return "range", {1: 1.2, 0: 1.0, -1: 0.5}, "数据不足，默认震荡"

    # --- 2. 核心指标 ---
    avg_ret = np.mean(list(returns.values()))
    dispersion = calc_dispersion(returns)
    pct_positive = sum(1 for r in returns.values() if r > 0) / len(returns)
    pct_strong = sum(1 for r in returns.values() if abs(r) > 5) / len(returns)

    # --- 3. 环境判断 ---
    # 高离散度 → 分化
    if dispersion > 4.0 and pct_strong > 0.3:
        regime = "divergent"
        description = f"分化行情（离散度{dispersion:.1f}，各品种各走各的）"

        # 分化行情下：信号乘数不变，但现金比例提高
        signal_mult = {1: 1.15, 0: 1.0, -1: 0.55}
        description += " → 分品种独立判断，提高现金比例"

    # 单边上涨
    elif avg_ret > 3.0 and pct_positive > 0.6:
        regime = "uptrend"
        signal_mult = {1: 1.3, 0: 1.0, -1: 0.6}  # 买入乘数提高，让利润跑
        description = f"单边上涨（平均{avg_ret:+.1f}%，{pct_positive*100:.0f}%品种上涨）"
        description += " → 加仓持有，让利润奔跑"

    # 单边下跌
    elif avg_ret < -3.0 and pct_positive < 0.4:
        regime = "downtrend"
        signal_mult = {1: 1.0, 0: 0.8, -1: 0.4}  # 卖出乘数降低，快速止损
        description = f"单边下跌（平均{avg_ret:+.1f}%，仅{pct_positive*100:.0f}%品种上涨）"
        description += " → 控制仓位，现金为王"

    # 震荡
    else:
        regime = "range"
        signal_mult = {1: 1.1, 0: 1.0, -1: 0.6}  # 买卖都轻一些，等方向
        description = f"震荡行情（平均{avg_ret:+.1f}%，离散度{dispersion:.1f}）"
        description += " → 轻仓观望，等方向明确"

    return regime, signal_mult, description


def get_price_array(df_close, min_length=20):
    """
    从 attribute_history 返回的 DataFrame 中提取价格数组。
    
    参数:
        df_close: attribute_history 返回的 DataFrame（列=['close']）
        min_length: 最少需要的数据天数
    
    返回:
        numpy array 或 None
    """
    if df_close is None or df_close.empty:
        return None
    v = df_close['close'].values
    if len(v) < min_length:
        return None
    return v


# ============================================================
# 使用示例
# ============================================================

if __name__ == '__main__':
    # 模拟测试数据
    import akshare as ak

    print("=" * 60)
    print("市场环境分类器 测试")
    print("=" * 60)

    codes = {
        '510300.XSHG': '沪深300', '510880.XSHG': '红利ETF', '512800.XSHG': '银行ETF',
        '588000.XSHG': '科创50', '512170.XSHG': '医疗ETF',
    }

    price_dict = {}
    for code in codes:
        try:
            # 用聚宽一样的 attribute_history（这里假数据，实际在聚宽中用attribute_history获取真实数据）
            # 这里用一个简单的随机序列代替
            np.random.seed(42)
            fake_prices = 100 + np.cumsum(np.random.randn(30) * 0.5)
            price_dict[code] = fake_prices
        except:
            pass

    if price_dict:
        regime, mult, desc = classify_market(price_dict)
        print(f"\n环境: {regime}")
        print(f"乘数: +1={mult[1]}, 0={mult[0]}, -1={mult[-1]}")
        print(f"描述: {desc}")
    else:
        print("无法获取数据")
