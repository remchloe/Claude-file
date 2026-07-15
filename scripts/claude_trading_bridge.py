"""
Claude → 量化交易 桥接脚本
=========================
作用：将Claude的分析输出转化为交易指令，对接交易平台。

工作流程：
  Claude生成分析报告
      ↓ (本脚本)
  解析为结构化JSON信号
      ↓
  风控检查（金额/频率/黑名单）
      ↓
  转换为平台交易指令
      ↓
  [聚宽模拟] / [QMT实盘] / [记录日志]

当前状态：✅ Claude信号解析就绪 | 🟡 风控模块就绪 | ⏳ 实盘接口待接入
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

# ============================================================
# 一、信号格式定义（Claude输出 → 标准格式）
# ============================================================

# Claude输出示例
CLAUDE_OUTPUT_EXAMPLE = {
    "report_date": "2026-07-15",
    "market_phase": "防御期（芯片见顶+地缘冲突）",
    "risk_level": "高",
    "core_allocation": 0.70,
    "satellite_allocation": 0.30,
    "signals": {
        "512480.XSHG": {  # 半导体ETF
            "action": "sell",
            "reason": "芯片见顶确认+韩国暴跌+长鑫IPO抽血",
            "confidence": 0.85,
            "target_reduction": 0.5  # 减半
        },
        "512800.XSHG": {  # 银行ETF
            "action": "buy",
            "reason": "避险唯一方向",
            "confidence": 0.90,
            "target_increase": 1.2
        },
        "159869.XSHG": {  # 游戏ETF
            "action": "reduce",
            "reason": "补涨品种反弹减仓",
            "confidence": 0.60,
            "target_reduction": 0.3
        },
        "512170.XSHG": {  # 医疗ETF
            "action": "buy",
            "reason": "底部放量+政策支撑",
            "confidence": 0.70,
            "target_increase": 1.3
        }
    },
    "stop_loss_alerts": [
        {"code": "512480.XSHG", "level": -5.0, "note": "若继续跌5%则清仓"},
        {"code": "588000.XSHG", "level": -3.0, "note": "若跌破2.0则减仓"}
    ]
}


def parse_claude_report(text: str) -> dict:
    """
    从Claude的分析报告中提取交易信号。
    
    两种模式：
    1. Markdown报告中包含JSON代码块 → 直接解析
    2. 纯文本 → AI提取（需配合LLM调用）
    
    参数:
        text: Claude输出的完整报告文本
    
    返回:
        标准化的信号字典
    """
    # 模式1：查找JSON代码块
    import re
    
    # 查找 ```json ... ``` 块
    json_pattern = r'```json\s*([\s\S]*?)```'
    matches = re.findall(json_pattern, text)
    
    for match in matches:
        try:
            data = json.loads(match.strip())
            # 验证必要字段
            if 'signals' in data:
                return data
        except json.JSONDecodeError:
            continue
    
    # 模式2：查找不带标记的JSON对象
    brace_pattern = r'\{[\s\S]*"signals"[\s\S]*"action"[\s\S]*\}'
    matches = re.findall(brace_pattern, text)
    
    for match in matches:
        try:
            data = json.loads(match.strip())
            if 'signals' in data:
                return data
        except:
            continue
    
    # 未找到有效信号
    return {
        "report_date": datetime.now().strftime("%Y-%m-%d"),
        "signals": {},
        "note": "未能从报告中解析出结构化信号"
    }


def format_trading_signals(claude_output: dict) -> List[dict]:
    """
    将Claude的输出转换为标准化的交易指令列表。
    
    参数:
        claude_output: 解析后的Claude输出
    
    返回:
        trade_orders: [
            {
                "code": "512480.XSHG",
                "action": "sell",
                "reason": "...",
                "priority": 1,
                "time_preference": "开盘/盘中/尾盘"
            },
            ...
        ]
    """
    orders = []
    signals = claude_output.get('signals', {})
    
    for code, signal in signals.items():
        action = signal.get('action', 'hold')
        confidence = signal.get('confidence', 0.5)
        
        # 跳过低置信度信号
        if confidence < 0.5:
            continue
        
        order = {
            "code": code,
            "action": action,
            "reason": signal.get('reason', ''),
            "confidence": confidence,
            "timestamp": datetime.now().isoformat(),
        }
        
        # 设置优先级和时间偏好
        if action in ['sell', 'reduce']:
            order['priority'] = 1
            order['time_preference'] = '开盘'
        elif action == 'buy':
            order['priority'] = 2
            order['time_preference'] = '尾盘'
        else:
            order['priority'] = 3
            order['time_preference'] = '盘中'
        
        orders.append(order)
    
    # 按优先级排序
    orders.sort(key=lambda x: x['priority'])
    
    return orders


# ============================================================
# 二、风控模块
# ============================================================

class RiskController:
    """风控检查"""
    
    def __init__(self):
        self.trade_history = []  # 交易历史
        self.daily_trade_count = 0
        self.last_trade_date = None
        
        # 风控参数
        self.max_daily_trades = 5           # 每日最大交易次数
        self.max_single_order_pct = 0.25    # 单笔最大仓位比例
        self.min_trade_interval_min = 5     # 最小交易间隔（分钟）
        self.blacklist = []                 # 黑名单（临时禁用代码）
    
    def check_order(self, order: dict, portfolio_value: float) -> Tuple[bool, str]:
        """
        检查单笔交易是否通过风控。
        
        返回: (通过/拒绝, 原因)
        """
        # 1. 每日交易次数限制
        today = datetime.now().date()
        if self.last_trade_date != today:
            self.daily_trade_count = 0
            self.last_trade_date = today
        
        if self.daily_trade_count >= self.max_daily_trades:
            return False, f"已达每日最大交易次数({self.max_daily_trades})"
        
        # 2. 黑名单检查
        if order['code'] in self.blacklist:
            return False, f"{order['code']} 在黑名单中"
        
        # 3. 交易间隔检查
        if self.trade_history:
            last_trade_time = self.trade_history[-1]['timestamp']
            last_trade_time = datetime.fromisoformat(last_trade_time)
            elapsed = (datetime.now() - last_trade_time).total_seconds() / 60
            if elapsed < self.min_trade_interval_min:
                return False, f"交易间隔过短({elapsed:.0f}分钟 < {self.min_trade_interval_min}分钟)"
        
        # 4. 置信度检查
        if order['confidence'] < 0.5:
            return False, f"信号置信度不足({order['confidence']})"
        
        return True, "通过"
    
    def record_trade(self, order: dict, executed: bool):
        """记录交易（通过风控的交易）"""
        if executed:
            self.daily_trade_count += 1
            self.trade_history.append({
                **order,
                "executed_at": datetime.now().isoformat(),
            })
    
    def get_summary(self) -> dict:
        """获取风控汇总"""
        return {
            "today_trades": self.daily_trade_count,
            "max_daily": self.max_daily_trades,
            "total_trades_today": len(self.trade_history),
            "blacklist": self.blacklist,
        }


# ============================================================
# 三、交易平台接口（抽象基类）
# ============================================================

class TradingPlatform:
    """交易平台接口基类"""
    
    def __init__(self, name: str, mode: str = "simulation"):
        self.name = name
        self.mode = mode  # "simulation" 或 "live"
        self.orders_log = []
    
    def connect(self) -> bool:
        """连接到交易平台"""
        raise NotImplementedError
    
    def place_order(self, code: str, action: str, amount: float) -> dict:
        """下单"""
        raise NotImplementedError
    
    def get_position(self, code: str) -> dict:
        """查询持仓"""
        raise NotImplementedError
    
    def get_account_info(self) -> dict:
        """查询账户信息"""
        raise NotImplementedError
    
    def log_order(self, order: dict):
        """记录订单"""
        self.orders_log.append({
            **order,
            "platform": self.name,
            "mode": self.mode,
            "timestamp": datetime.now().isoformat(),
        })


class SimulationPlatform(TradingPlatform):
    """模拟交易平台——供Phase 1使用"""
    
    def __init__(self, initial_cash: float = 100000):
        super().__init__("模拟交易", mode="simulation")
        self.cash = initial_cash
        self.positions = {}  # code -> shares
        self.prices = {}     # code -> last_price
    
    def connect(self) -> bool:
        print(f"[模拟交易] 连接成功 | 初始资金: {self.cash:.2f}")
        return True
    
    def place_order(self, code: str, action: str, amount: float) -> dict:
        """
        模拟下单。
        
        参数:
            code: ETF代码（含交易所后缀）
            action: "buy" 或 "sell"
            amount: 金额（元）
        """
        price = self.prices.get(code, 1.0)
        shares = int(amount / price / 100) * 100
        
        if action == "buy":
            cost = shares * price
            if cost > self.cash:
                return {"status": "rejected", "reason": "资金不足"}
            self.cash -= cost
            self.positions[code] = self.positions.get(code, 0) + shares
        elif action == "sell":
            current = self.positions.get(code, 0)
            if shares > current:
                shares = current
            revenue = shares * price
            self.cash += revenue
            self.positions[code] = current - shares
        
        order_record = {
            "code": code, "action": action, "shares": shares,
            "price": price, "amount": shares * price,
            "status": "filled", "timestamp": datetime.now().isoformat(),
        }
        self.log_order(order_record)
        return order_record
    
    def get_position(self, code: str) -> dict:
        return {
            "code": code,
            "shares": self.positions.get(code, 0),
            "value": self.positions.get(code, 0) * self.prices.get(code, 0),
        }
    
    def get_account_info(self) -> dict:
        total_value = self.cash + sum(
            shares * self.prices.get(code, 0)
            for code, shares in self.positions.items()
        )
        return {
            "cash": self.cash,
            "positions_value": total_value - self.cash,
            "total": total_value,
            "position_count": len(self.positions),
        }


# ============================================================
# 四、主流程：Claude信号 → 交易执行
# ============================================================

class ClaudeTradingPipeline:
    """
    Claude信号 → 交易执行 完整流水线
    
    使用示例：
        pipeline = ClaudeTradingPipeline()
        
        # 从Claude报告解析信号
        orders = pipeline.analyze_report(claude_report_text)
        
        # 查看解析结果
        for order in orders:
            print(f"{order['action']} {order['code']}: {order['reason']}")
        
        # 执行交易（模拟模式）
        results = pipeline.execute(platform=SimulationPlatform())
        print(results)
    """
    
    def __init__(self):
        self.risk_controller = RiskController()
        self.current_orders = []
    
    def analyze_report(self, report_text: str) -> List[dict]:
        """分析Claude报告，生成交易指令"""
        claude_data = parse_claude_report(report_text)
        self.current_orders = format_trading_signals(claude_data)
        return self.current_orders
    
    def execute(self, platform: TradingPlatform = None) -> List[dict]:
        """执行当前交易指令"""
        if platform is None:
            platform = SimulationPlatform()
            platform.connect()
        
        if not platform.connect():
            return [{"error": "无法连接到交易平台"}]
        
        results = []
        for order in self.current_orders:
            # 风控检查
            passed, reason = self.risk_controller.check_order(
                order, portfolio_value=100000
            )
            
            if not passed:
                results.append({
                    **order, "status": "rejected", "reason": reason
                })
                continue
            
            # 执行交易
            result = platform.place_order(
                code=order['code'],
                action=order['action'],
                amount=10000  # 示例固定金额
            )
            
            # 记录交易
            self.risk_controller.record_trade(order, executed=True)
            results.append(result)
        
        return results
    
    def generate_report(self, platform: TradingPlatform = None) -> str:
        """生成交易执行报告"""
        lines = []
        lines.append("=" * 50)
        lines.append(f"交易执行报告 | {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        lines.append("=" * 50)
        
        if platform:
            info = platform.get_account_info()
            lines.append(f"\n账户状态:")
            lines.append(f"  总资产: {info['total']:.2f}")
            lines.append(f"  现金: {info['cash']:.2f}")
            lines.append(f"  持仓数: {info['position_count']}")
        
        lines.append(f"\n风控信息:")
        rc = self.risk_controller.get_summary()
        lines.append(f"  今日交易: {rc['today_trades']}/{rc['max_daily']}")
        
        lines.append(f"\n交易明细:")
        for order in self.current_orders:
            lines.append(f"  [{order['action'].upper()}] {order['code']}: {order['reason']}")
        
        return '\n'.join(lines)


# ============================================================
# 五、使用示例
# ============================================================

if __name__ == "__main__":
    print("=" * 50)
    print("Claude → 量化交易 桥接示例")
    print("=" * 50)
    
    # 模拟Claude输出
    sample_report = f"""
```json
{json.dumps(CLAUDE_OUTPUT_EXAMPLE, ensure_ascii=False, indent=2)}
```
    """
    
    # 创建流水线
    pipeline = ClaudeTradingPipeline()
    
    # 解析信号
    orders = pipeline.analyze_report(sample_report)
    print(f"\n解析到 {len(orders)} 条交易指令:")
    for o in orders:
        print(f"  [{o['priority']}] {o['action']} {o['code']} (置信度:{o['confidence']})")
    
    # 执行交易
    sim = SimulationPlatform(initial_cash=100000)
    results = pipeline.execute(sim)
    
    print(f"\n执行结果:")
    for r in results:
        status = r.get('status', 'unknown')
        print(f"  {status}: {r.get('action','?')} {r.get('code','?')} -> {r.get('reason','')}")
    
    # 生成报告
    print(f"\n{pipeline.generate_report(sim)}")
