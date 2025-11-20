#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
策略回测工具
用于测试策略在历史数据上的表现
"""

import sys
import os
from pathlib import Path
import pandas as pd
import numpy as np
import yaml
from datetime import datetime, timedelta
from typing import Dict, List

# 添加src目录到Python路径
src_path = Path(__file__).parent.parent / 'src'
sys.path.insert(0, str(src_path))

from strategy import TrendFollowingStrategy, SignalType
import ccxt

class Backtester:
    """回测器"""
    
    def __init__(self, config_path: str = 'config.yaml'):
        self.config = self._load_config(config_path)
        self.strategy = TrendFollowingStrategy(self.config)
        
        # 回测参数
        self.initial_balance = 1000000  # 初始资金
        self.current_balance = self.initial_balance
        self.position = 0
        self.entry_price = 0
        self.trades = []
        
        # 性能统计
        self.total_trades = 0
        self.winning_trades = 0
        self.total_pnl = 0
        self.max_drawdown = 0
        self.balance_history = []
        
    def _load_config(self, config_path: str) -> Dict:
        """加载配置文件"""
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    
    def get_historical_data(self, symbol: str, timeframe: str, 
                           start_date: str, end_date: str) -> pd.DataFrame:
        """获取历史数据"""
        try:
            # 初始化交易所
            exchange = ccxt.binance({
                'apiKey': self.config['exchange']['apiKey'],
                'secret': self.config['exchange']['secretKey'],
                'enableRateLimit': True
            })
            exchange.httpsProxy = "http://127.0.0.1:7890/"
            # 测试连接
            exchange.load_markets()
            # 转换时间格式
            start_timestamp = exchange.parse8601(start_date + 'T00:00:00Z')
            end_timestamp = exchange.parse8601(end_date + 'T23:59:59Z')
            
            all_data = []
            current_timestamp = start_timestamp
            
            print(f"获取历史数据: {symbol} {timeframe} from {start_date} to {end_date}")
            
            while current_timestamp and end_timestamp and current_timestamp < end_timestamp:
                try:
                    ohlcv = exchange.fetch_ohlcv(
                        symbol=symbol,
                        timeframe=timeframe,
                        since=current_timestamp,
                        limit=1000
                    )
                    
                    if not ohlcv:
                        break
                    
                    all_data.extend(ohlcv)
                    current_timestamp = ohlcv[-1][0] + 1
                    
                    print(f"已获取 {len(all_data)} 条数据...")
                    
                except Exception as e:
                    print(f"获取数据出错: {e}")
                    break
            
            # 转换为DataFrame
            if not all_data:
                return pd.DataFrame()
            
            # 构造DataFrame
            df = pd.DataFrame(all_data)
            df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            
            # 去重并排序
            df = df[~df.index.duplicated(keep='first')]
            df = df.sort_index()
            
            print(f"历史数据获取完成: {len(df)} 条记录")
            return df if isinstance(df, pd.DataFrame) else pd.DataFrame()
            
        except Exception as e:
            print(f"获取历史数据失败: {e}")
            return pd.DataFrame()
    
    def run_backtest(self, data: pd.DataFrame) -> Dict:
        """运行回测"""
        print("开始回测...")
        
        # 计算技术指标
        data = self.strategy.calculate_indicators(data)
        
        # 逐行处理数据
        for i in range(len(data)):
            if i < 50:  # 跳过前50行，确保指标计算完整
                continue
            
            current_data = data.iloc[:i+1]
            current_price = float(current_data['close'].iloc[-1])
            current_time = current_data.index[-1]
            
            # 生成交易信号
            signal = self.strategy.generate_signal(current_data)
            
            # 添加调试信息
            if i % 100 == 0:  # 每100条数据打印一次调试信息
                rsi_value = current_data['rsi'].iloc[-1] if 'rsi' in current_data.columns else 'N/A'
                macd_value = current_data['macd'].iloc[-1] if 'macd' in current_data.columns else 'N/A'
                rsi_str = f"{rsi_value:.2f}" if rsi_value != 'N/A' else 'N/A'
                macd_str = f"{macd_value:.4f}" if macd_value != 'N/A' else 'N/A'
                print(f"调试信息 - 时间: {current_time}, 价格: {current_price:.2f}, RSI: {rsi_str}, MACD: {macd_str}, 信号: {signal.name}")
            
            # 执行交易
            if signal != SignalType.HOLD:
                print(f"交易信号: {signal.name} at {current_time} - Price: {current_price}")
                self._execute_backtest_trade(signal, current_price, current_time)
            
            # 记录余额历史
            unrealized_pnl = self._calculate_unrealized_pnl(current_price)
            current_equity = self.current_balance + unrealized_pnl
            self.balance_history.append({
                'timestamp': current_time,
                'balance': self.current_balance,
                'equity': current_equity,
                'position': self.position,
                'price': current_price
            })
        
        # 如果最后还有持仓，平仓
        if self.position != 0:
            final_price = float(data['close'].iloc[-1])
            final_time = data.index[-1]
            self._close_position(final_price, final_time, 'final_close')
        
        # 计算性能指标
        performance = self._calculate_performance()
        
        print("回测完成")
        return performance
    
    def _execute_backtest_trade(self, signal: SignalType, price: float, timestamp):
        """执行回测交易"""
        trade_amount = self.config['trading']['trade_amount']
        
        if signal == SignalType.BUY and self.position <= 0:
            # 买入
            cost = trade_amount * price
            if self.current_balance >= cost:
                self.position += trade_amount
                self.current_balance -= cost
                self.entry_price = price
                
                self.trades.append({
                    'timestamp': timestamp,
                    'signal': signal.value,
                    'side': 'buy',
                    'amount': trade_amount,
                    'price': price,
                    'balance': self.current_balance
                })
                
                print(f"{timestamp}: BUY {trade_amount} @ {price:.4f}")
        
        elif signal == SignalType.SELL and self.position > 0:
            # 卖出
            self._close_position(price, timestamp, 'sell')
        
        elif signal == SignalType.LONG and self.position <= 0:
            # 做多(合约)
            self.position = trade_amount
            self.entry_price = price
            
            self.trades.append({
                'timestamp': timestamp,
                'signal': signal.value,
                'side': 'long',
                'amount': trade_amount,
                'price': price,
                'balance': self.current_balance
            })
            
            print(f"{timestamp}: LONG {trade_amount} @ {price:.4f}")
        
        elif signal == SignalType.SHORT and self.position >= 0:
            # 做空(合约)
            self.position = -trade_amount
            self.entry_price = price
            
            self.trades.append({
                'timestamp': timestamp,
                'signal': signal.value,
                'side': 'short',
                'amount': trade_amount,
                'price': price,
                'balance': self.current_balance
            })
            
            print(f"{timestamp}: SHORT {trade_amount} @ {price:.4f}")
        
        elif signal in [SignalType.CLOSE_LONG, SignalType.CLOSE_SHORT]:
            # 平仓
            if self.position != 0:
                self._close_position(price, timestamp, 'close')
    
    def _close_position(self, price: float, timestamp, reason: str):
        """平仓"""
        if self.position == 0:
            return
        
        # 计算盈亏
        if self.position > 0:  # 多头
            pnl = (price - self.entry_price) * self.position
            self.current_balance += self.position * price
        else:  # 空头
            pnl = (self.entry_price - price) * abs(self.position)
            self.current_balance += pnl
        
        self.total_pnl += pnl
        self.total_trades += 1
        
        if pnl > 0:
            self.winning_trades += 1
        
        self.trades.append({
            'timestamp': timestamp,
            'signal': reason,
            'side': 'close',
            'amount': abs(self.position),
            'price': price,
            'pnl': pnl,
            'balance': self.current_balance
        })
        
        print(f"{timestamp}: CLOSE {abs(self.position)} @ {price:.4f}, PnL: {pnl:.4f}")
        
        self.position = 0
        self.entry_price = 0
    
    def _calculate_unrealized_pnl(self, current_price: float) -> float:
        """计算未实现盈亏"""
        if self.position == 0 or self.entry_price == 0:
            return 0
        
        if self.position > 0:  # 多头
            return (current_price - self.entry_price) * self.position
        else:  # 空头
            return (self.entry_price - current_price) * abs(self.position)
    
    def _calculate_performance(self) -> Dict:
        """计算性能指标"""
        if not self.balance_history:
            return {}
        
        # 转换为DataFrame
        balance_df = pd.DataFrame(self.balance_history)
        
        # 计算收益率
        balance_df['returns'] = balance_df['equity'].pct_change()
        
        # 基础指标
        final_balance = self.current_balance
        total_return = (final_balance - self.initial_balance) / self.initial_balance * 100
        
        # 胜率
        win_rate = (self.winning_trades / self.total_trades * 100) if self.total_trades > 0 else 0
        
        # 最大回撤
        balance_df['peak'] = balance_df['equity'].expanding().max()
        balance_df['drawdown'] = (balance_df['peak'] - balance_df['equity']) / balance_df['peak'] * 100
        max_drawdown = balance_df['drawdown'].max()
        
        # 夏普比率
        if balance_df['returns'].std() > 0:
            sharpe_ratio = balance_df['returns'].mean() / balance_df['returns'].std() * np.sqrt(252)
        else:
            sharpe_ratio = 0
        
        # 盈亏比
        winning_trades_df = pd.DataFrame([t for t in self.trades if t.get('pnl', 0) > 0])
        losing_trades_df = pd.DataFrame([t for t in self.trades if t.get('pnl', 0) < 0])
        
        avg_win = winning_trades_df['pnl'].mean() if not winning_trades_df.empty else 0
        avg_loss = abs(losing_trades_df['pnl'].mean()) if not losing_trades_df.empty else 0
        profit_loss_ratio = avg_win / avg_loss if avg_loss > 0 else 0
        
        performance = {
            'initial_balance': self.initial_balance,
            'final_balance': final_balance,
            'total_return': round(total_return, 2),
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.total_trades - self.winning_trades,
            'win_rate': round(win_rate, 2),
            'total_pnl': round(self.total_pnl, 4),
            'max_drawdown': round(max_drawdown, 2),
            'sharpe_ratio': round(sharpe_ratio, 2),
            'profit_loss_ratio': round(profit_loss_ratio, 2),
            'avg_win': round(avg_win, 4),
            'avg_loss': round(avg_loss, 4)
        }
        
        return performance
    
    def save_results(self, performance: Dict, filename: str = None):
        """保存回测结果"""
        if filename is None:
            filename = f"backtest/backtest_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        # 保存交易记录
        trades_df = pd.DataFrame(self.trades)
        base_filename = filename.replace('.csv', '') if filename and filename.endswith('.csv') else (filename if filename else 'backtest_results')
        trades_df.to_csv(f"backtest/trades_{base_filename}.csv", index=False)
        
        # 保存余额历史
        balance_df = pd.DataFrame(self.balance_history)
        balance_filename = filename.replace('.csv', '') if filename and filename.endswith('.csv') else (filename if filename else 'backtest_results')
        balance_df.to_csv(f"backtest/balance_{balance_filename}.csv", index=False)
        
        # 保存性能指标
        performance_filename = filename.replace('.csv', '') if filename and filename.endswith('.csv') else (filename if filename else 'backtest_results')
        performance_filename = f"{performance_filename}.txt"
        with open(f"performance_{performance_filename}", 'w') as f:
            f.write("回测性能报告\n")
            f.write("=" * 50 + "\n")
            for key, value in performance.items():
                f.write(f"{key}: {value}\n")
        
        print(f"回测结果已保存: {filename}")

def main():
    """主函数"""
    # 回测参数
    symbol = 'ETH/USDT'
    timeframe = '1h'
    start_date = '2025-01-01'
    end_date = '2025-11-15'
    
    # 创建回测器
    backtester = Backtester()
    
    # 获取历史数据
    data = backtester.get_historical_data(symbol, timeframe, start_date, end_date)
    
    if data.empty:
        print("无法获取历史数据")
        return
    
    # 运行回测
    performance = backtester.run_backtest(data)
    
    # 打印结果
    print("\n" + "="*50)
    print("回测结果")
    print("="*50)
    for key, value in performance.items():
        print(f"{key}: {value}")
    
    # 保存结果
    backtester.save_results(performance)

if __name__ == "__main__":
    main()