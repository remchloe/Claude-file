"""
ETF数据采集 v2 — 多源备份
============================
主数据源：baostock（免费、稳定、无需注册）
备选数据源：akshare Sina API（与原脚本一致）

使用方法：
  python scripts/get_etf_data_v2.py
  
  输出：reports/目录下的CSV数据文件

相比 v1（get_etf_data.py）的改进：
  - 主数据源改为 baostock，避免 EastMoney 被拦截的问题
  - 自动 fallback：baostock 失败时自动切换 Sina
  - 输出格式与 v1 完全兼容
"""

import os
import sys
import time
from datetime import datetime, timedelta

# ================================================================
# 数据源1：baostock（主数据源）
# ================================================================

def get_data_baostock(code, name, start_date, end_date):
    """
    通过 baostock 获取ETF日线数据。
    
    参数:
        code: ETF代码，如 '510300'
        name: ETF名称
        start_date/end_date: 'YYYY-MM-DD' 格式
    
    返回: dict 或 None
    """
    try:
        import baostock as bs
        lg = bs.login()
        if lg.error_code != '0':
            return None

        # baostock 中沪市代码前缀 sh.，深市前缀 sz.
        prefix = 'sz' if code.startswith('15') or code.startswith('16') else 'sh'
        bs_code = f"{prefix}.{code}"

        rs = bs.query_history_k_data_plus(
            bs_code,
            "date,open,close,high,low,volume,amount",
            start_date=start_date, end_date=end_date,
            frequency='d', adjustflag='2'  # 前复权
        )

        if rs.error_code != '0':
            bs.logout()
            return None

        # 解析数据
        rows = []
        while rs.next():
            row = rs.get_row_data()
            if row[0]:  # 有日期
                rows.append({
                    'date': row[0],
                    'open': float(row[1]),
                    'close': float(row[2]),
                    'high': float(row[3]),
                    'low': float(row[4]),
                    'volume': int(row[5]),
                    'amount': float(row[6]) if row[6] else 0,
                })

        bs.logout()

        if not rows:
            return None

        # 计算周涨跌幅
        open_price = rows[0]['open']
        close_price = rows[-1]['close']
        weekly_return = (close_price - open_price) / open_price * 100

        # 计算振幅
        max_price = max(r['high'] for r in rows)
        min_price = min(r['low'] for r in rows)
        amplitude = (max_price - min_price) / open_price * 100

        # 成交额合计
        turnover = sum(r['amount'] for r in rows) / 1e8

        return {
            'code': code,
            'name': name,
            'open': round(open_price, 3),
            'close': round(close_price, 3),
            'weekly_return': round(weekly_return, 2),
            'turnover_sum': round(turnover, 2),
            'amplitude': round(amplitude, 2),
            'high': round(max_price, 3),
            'low': round(min_price, 3),
            'days': len(rows),
            'source': 'baostock',
        }
    except ImportError:
        return None
    except Exception as e:
        return {'code': code, 'name': name, 'error': str(e)[:60]}


# ================================================================
# 数据源2：akshare Sina API（备选）
# ================================================================

def get_data_sina(code, name, start_date, end_date):
    """
    通过 akshare Sina API 获取ETF数据。
    与原 get_etf_data.py 完全一致。
    """
    try:
        import akshare as ak
        prefix = 'sz' if code.startswith('15') or code.startswith('16') else 'sh'
        symbol = f"{prefix}{code}"
        df = ak.fund_etf_hist_sina(symbol=symbol)
        if df is None or df.empty:
            return None

        df['date'] = pd.to_datetime(df['date'])
        mask = (df['date'] >= start_date) & (df['date'] <= end_date)
        period_df = df[mask].sort_values('date')
        if period_df.empty:
            return None

        open_price = float(period_df.iloc[0]['open'])
        close_price = float(period_df.iloc[-1]['close'])
        weekly_return = (close_price - open_price) / open_price * 100
        turnover = period_df['amount'].sum() / 1e8
        max_price = period_df['high'].max()
        min_price = period_df['low'].min()
        amplitude = (max_price - min_price) / open_price * 100

        return {
            'code': code, 'name': name,
            'open': round(open_price, 3), 'close': round(close_price, 3),
            'weekly_return': round(weekly_return, 2),
            'turnover_sum': round(turnover, 2),
            'amplitude': round(amplitude, 2),
            'high': round(max_price, 3), 'low': round(min_price, 3),
            'days': len(period_df), 'source': 'sina',
        }
    except:
        return None


# ================================================================
# 主函数
# ================================================================

if __name__ == '__main__':
    import pandas as pd

    # 日期范围（默认最近一周）
    today = datetime.now()
    end = today.strftime('%Y-%m-%d')
    start = (today - timedelta(days=7)).strftime('%Y-%m-%d')

    print("=" * 60)
    print("ETF数据采集 v2 — 多源备份")
    print(f"数据范围: {start} ~ {end}")
    print("=" * 60)

    etf_list = {
        '510300': '沪深300ETF', '510500': '中证500ETF', '512100': '中证1000ETF',
        '588000': '科创50ETF', '159915': '创业板ETF', '512480': '半导体ETF',
        '159995': '芯片ETF', '510880': '红利ETF', '159928': '消费ETF',
        '512170': '医疗ETF', '512800': '银行ETF', '516160': '新能源ETF',
        '512000': '券商ETF', '512660': '军工ETF', '159869': '游戏ETF',
        '518880': '黄金ETF',
    }

    results = []
    fail_count = 0
    baostock_ok = False

    for code, name in etf_list.items():
        # 优先 baostock
        r = get_data_baostock(code, name, start, end)
        if r and 'error' not in r:
            results.append(r)
            if not baostock_ok:
                baostock_ok = True
            print(f"  [baostock] {code} {name}: {r['weekly_return']:+.2f}%")
            continue

        # 备选 Sina
        time.sleep(0.3)
        r2 = get_data_sina(code, name, start, end)
        if r2 and 'error' not in r2:
            results.append(r2)
            print(f"  [sina]     {code} {name}: {r2['weekly_return']:+.2f}%")
            continue

        fail_count += 1
        print(f"  [FAIL]     {code} {name}: 所有数据源均失败")

    # 保存
    if results:
        df = pd.DataFrame(results)
        df.sort_values('weekly_return', ascending=False, inplace=True)
        out_path = os.path.join('data', 'etf_weekly_v2.csv')
        df.to_csv(out_path, index=False, encoding='utf-8-sig')
        print(f"\n✅ 保存到 {out_path}")
        print(f"   成功: {len(results)}/{len(etf_list)} | 失败: {fail_count}")

        if baostock_ok:
            print(f"   主数据源: baostock ✅")
        else:
            print(f"   主数据源: baostock ❌ 已回退到 Sina")
    else:
        print("\n❌ 所有数据源均失败")
