#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
交易机器人监控工具
实时监控机器人状态、性能和风险
"""

import sys
import os
from pathlib import Path
import pandas as pd
import time
import yaml
from datetime import datetime, timedelta
from typing import Dict, List
import sqlite3
import json

# 添加src目录到Python路径
src_path = Path(__file__).parent.parent / 'src'
sys.path.insert(0, str(src_path))

class TradingMonitor:
    """交易监控器"""
    
    def __init__(self, config_path: str = '../config.yaml'):
        self.config = self._load_config(config_path)
        self.db_path = Path('../data/trading_bot.db')
        
        # 监控参数
        self.refresh_interval = 30  # 刷新间隔(秒)
        self.alert_thresholds = {
            'max_drawdown': 10.0,  # 最大回撤警告阈值
            'daily_loss': -500,    # 每日亏损警告阈值
            'win_rate': 30.0       # 胜率警告阈值
        }
        
    def _load_config(self, config_path: str) -> Dict:
        """加载配置文件"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"配置文件加载失败: {e}")
            return {}
    
    def get_real_time_status(self) -> Dict:
        """获取实时状态"""
        try:
            if not self.db_path.exists():
                return {'error': '数据库文件不存在'}
            
            conn = sqlite3.connect(self.db_path)
            
            # 获取最新交易记录
            latest_trade_query = """
                SELECT * FROM trades 
                ORDER BY timestamp DESC 
                LIMIT 1
            """
            latest_trade = pd.read_sql_query(latest_trade_query, conn)
            
            # 获取今日交易统计
            today = datetime.now().date().isoformat()
            today_trades_query = """
                SELECT COUNT(*) as count, 
                       SUM(pnl) as total_pnl,
                       AVG(pnl) as avg_pnl
                FROM trades 
                WHERE DATE(timestamp) = ?
            """
            today_stats = pd.read_sql_query(today_trades_query, conn, params=[today])
            
            # 获取最新信号
            latest_signal_query = """
                SELECT * FROM signals 
                ORDER BY timestamp DESC 
                LIMIT 1
            """
            latest_signal = pd.read_sql_query(latest_signal_query, conn)
            
            # 获取性能统计
            performance_query = """
                SELECT * FROM performance 
                ORDER BY date DESC 
                LIMIT 7
            """
            recent_performance = pd.read_sql_query(performance_query, conn)
            
            conn.close()
            
            # 组装状态信息
            status = {
                'timestamp': datetime.now().isoformat(),
                'latest_trade': latest_trade.to_dict('records')[0] if not latest_trade.empty else None,
                'today_stats': {
                    'trades_count': int(today_stats['count'].iloc[0]) if not today_stats.empty else 0,
                    'total_pnl': float(today_stats['total_pnl'].iloc[0]) if not today_stats.empty and today_stats['total_pnl'].iloc[0] else 0,
                    'avg_pnl': float(today_stats['avg_pnl'].iloc[0]) if not today_stats.empty and today_stats['avg_pnl'].iloc[0] else 0
                },
                'latest_signal': latest_signal.to_dict('records')[0] if not latest_signal.empty else None,
                'recent_performance': recent_performance.to_dict('records') if not recent_performance.empty else []
            }
            
            return status
            
        except Exception as e:
            return {'error': f'获取状态失败: {e}'}
    
    def calculate_risk_metrics(self) -> Dict:
        """计算风险指标"""
        try:
            if not self.db_path.exists():
                return {'error': '数据库文件不存在'}
            
            conn = sqlite3.connect(self.db_path)
            
            # 获取最近30天的交易记录
            thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
            trades_query = """
                SELECT * FROM trades 
                WHERE timestamp >= ? 
                ORDER BY timestamp
            """
            trades_df = pd.read_sql_query(trades_query, conn, params=[thirty_days_ago])
            
            conn.close()
            
            if trades_df.empty:
                return {'message': '无交易记录'}
            
            # 计算风险指标
            trades_df['timestamp'] = pd.to_datetime(trades_df['timestamp'])
            trades_df['cumulative_pnl'] = trades_df['pnl'].cumsum()
            
            # 最大回撤
            peak = trades_df['cumulative_pnl'].expanding().max()
            drawdown = (peak - trades_df['cumulative_pnl']) / peak * 100
            max_drawdown = drawdown.max() if not drawdown.empty else 0
            
            # 胜率
            winning_trades = len(trades_df[trades_df['pnl'] > 0])
            total_trades = len(trades_df)
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            
            # 盈亏比
            avg_win = trades_df[trades_df['pnl'] > 0]['pnl'].mean() if winning_trades > 0 else 0
            avg_loss = abs(trades_df[trades_df['pnl'] < 0]['pnl'].mean()) if (total_trades - winning_trades) > 0 else 0
            profit_loss_ratio = avg_win / avg_loss if avg_loss > 0 else 0
            
            # 夏普比率(简化)
            returns = trades_df['pnl']
            sharpe_ratio = returns.mean() / returns.std() if returns.std() > 0 else 0
            
            # 最大连续亏损
            trades_df['is_loss'] = trades_df['pnl'] < 0
            trades_df['loss_group'] = (trades_df['is_loss'] != trades_df['is_loss'].shift()).cumsum()
            loss_streaks = trades_df[trades_df['is_loss']].groupby('loss_group').size()
            max_consecutive_losses = loss_streaks.max() if not loss_streaks.empty else 0
            
            risk_metrics = {
                'max_drawdown': round(max_drawdown, 2),
                'win_rate': round(win_rate, 2),
                'profit_loss_ratio': round(profit_loss_ratio, 2),
                'sharpe_ratio': round(sharpe_ratio, 2),
                'max_consecutive_losses': int(max_consecutive_losses),
                'total_trades': total_trades,
                'winning_trades': winning_trades,
                'total_pnl': round(trades_df['pnl'].sum(), 4),
                'avg_trade_pnl': round(trades_df['pnl'].mean(), 4)
            }
            
            return risk_metrics
            
        except Exception as e:
            return {'error': f'计算风险指标失败: {e}'}
    
    def check_alerts(self, risk_metrics: Dict) -> List[str]:
        """检查警告条件"""
        alerts = []
        
        try:
            # 检查最大回撤
            if risk_metrics.get('max_drawdown', 0) > self.alert_thresholds['max_drawdown']:
                alerts.append(f"⚠️ 最大回撤过高: {risk_metrics['max_drawdown']:.2f}%")
            
            # 检查胜率
            if risk_metrics.get('win_rate', 100) < self.alert_thresholds['win_rate']:
                alerts.append(f"⚠️ 胜率过低: {risk_metrics['win_rate']:.2f}%")
            
            # 检查今日盈亏
            status = self.get_real_time_status()
            today_pnl = status.get('today_stats', {}).get('total_pnl', 0)
            if today_pnl < self.alert_thresholds['daily_loss']:
                alerts.append(f"⚠️ 今日亏损过大: {today_pnl:.4f}")
            
            # 检查连续亏损
            if risk_metrics.get('max_consecutive_losses', 0) >= 5:
                alerts.append(f"⚠️ 连续亏损次数过多: {risk_metrics['max_consecutive_losses']}")
            
        except Exception as e:
            alerts.append(f"❌ 警告检查失败: {e}")
        
        return alerts
    
    def generate_report(self) -> str:
        """生成监控报告"""
        try:
            status = self.get_real_time_status()
            risk_metrics = self.calculate_risk_metrics()
            alerts = self.check_alerts(risk_metrics)
            
            # 生成报告
            report = f"""
╔══════════════════════════════════════════════════════════════╗
║                    交易机器人监控报告                          ║
╠══════════════════════════════════════════════════════════════╣
║ 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}                           ║
╠══════════════════════════════════════════════════════════════╣
║ 今日交易统计                                                 ║
║ • 交易次数: {status.get('today_stats', {}).get('trades_count', 0):>3}                                          ║
║ • 总盈亏:   {status.get('today_stats', {}).get('total_pnl', 0):>8.4f}                                   ║
║ • 平均盈亏: {status.get('today_stats', {}).get('avg_pnl', 0):>8.4f}                                   ║
╠══════════════════════════════════════════════════════════════╣
║ 风险指标 (最近30天)                                          ║
║ • 最大回撤: {risk_metrics.get('max_drawdown', 0):>6.2f}%                                    ║
║ • 胜率:     {risk_metrics.get('win_rate', 0):>6.2f}%                                    ║
║ • 盈亏比:   {risk_metrics.get('profit_loss_ratio', 0):>6.2f}                                      ║
║ • 夏普比率: {risk_metrics.get('sharpe_ratio', 0):>6.2f}                                      ║
║ • 总交易:   {risk_metrics.get('total_trades', 0):>6}                                        ║
║ • 盈利交易: {risk_metrics.get('winning_trades', 0):>6}                                        ║
╠══════════════════════════════════════════════════════════════╣
"""
            
            # 添加最新交易信息
            latest_trade = status.get('latest_trade')
            if latest_trade:
                report += f"""║ 最新交易                                                     ║
║ • 时间: {latest_trade.get('timestamp', '')[:19]}                           ║
║ • 方向: {latest_trade.get('side', '').upper():>4}                                          ║
║ • 数量: {latest_trade.get('amount', 0):>8.4f}                                   ║
║ • 价格: {latest_trade.get('price', 0):>8.4f}                                   ║
║ • 盈亏: {latest_trade.get('pnl', 0):>8.4f}                                   ║
╠══════════════════════════════════════════════════════════════╣
"""
            
            # 添加最新信号
            latest_signal = status.get('latest_signal')
            if latest_signal:
                report += f"""║ 最新信号                                                     ║
║ • 时间: {latest_signal.get('timestamp', '')[:19]}                           ║
║ • 信号: {latest_signal.get('signal_type', ''):>8}                                    ║
║ • 价格: {latest_signal.get('price', 0):>8.4f}                                   ║
║ • 置信度: {latest_signal.get('confidence', 0):>6.2f}                                      ║
╠══════════════════════════════════════════════════════════════╣
"""
            
            # 添加警告信息
            if alerts:
                report += "║ 警告信息                                                     ║\n"
                for alert in alerts:
                    report += f"║ {alert:<60} ║\n"
                report += "╠══════════════════════════════════════════════════════════════╣\n"
            
            report += "╚══════════════════════════════════════════════════════════════╝"
            
            return report
            
        except Exception as e:
            return f"生成报告失败: {e}"
    
    def save_report(self, report: str, filename: str = None):
        """保存报告到文件"""
        try:
            if filename is None:
                filename = f"monitor_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            
            reports_dir = Path('../logs/reports')
            reports_dir.mkdir(parents=True, exist_ok=True)
            
            with open(reports_dir / filename, 'w', encoding='utf-8') as f:
                f.write(report)
            
            print(f"报告已保存: {reports_dir / filename}")
            
        except Exception as e:
            print(f"保存报告失败: {e}")
    
    def start_monitoring(self):
        """开始监控"""
        print("开始监控交易机器人...")
        print(f"刷新间隔: {self.refresh_interval}秒")
        print("按 Ctrl+C 停止监控\n")
        
        try:
            while True:
                # 清屏
                os.system('clear' if os.name == 'posix' else 'cls')
                
                # 生成并显示报告
                report = self.generate_report()
                print(report)
                
                # 等待下次刷新
                time.sleep(self.refresh_interval)
                
        except KeyboardInterrupt:
            print("\n监控已停止")
        except Exception as e:
            print(f"监控异常: {e}")
    
    def export_data(self, days: int = 7):
        """导出数据"""
        try:
            if not self.db_path.exists():
                print("数据库文件不存在")
                return
            
            conn = sqlite3.connect(self.db_path)
            
            # 导出目录
            export_dir = Path('../data/exports')
            export_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            
            # 导出交易记录
            start_date = (datetime.now() - timedelta(days=days)).isoformat()
            trades_query = "SELECT * FROM trades WHERE timestamp >= ? ORDER BY timestamp"
            trades_df = pd.read_sql_query(trades_query, conn, params=[start_date])
            trades_df.to_csv(export_dir / f'trades_{timestamp}.csv', index=False)
            
            # 导出信号记录
            signals_query = "SELECT * FROM signals WHERE timestamp >= ? ORDER BY timestamp"
            signals_df = pd.read_sql_query(signals_query, conn, params=[start_date])
            signals_df.to_csv(export_dir / f'signals_{timestamp}.csv', index=False)
            
            # 导出性能记录
            performance_query = "SELECT * FROM performance ORDER BY date DESC LIMIT 30"
            performance_df = pd.read_sql_query(performance_query, conn)
            performance_df.to_csv(export_dir / f'performance_{timestamp}.csv', index=False)
            
            conn.close()
            
            print(f"数据导出完成: {export_dir}")
            print(f"导出文件: trades_{timestamp}.csv, signals_{timestamp}.csv, performance_{timestamp}.csv")
            
        except Exception as e:
            print(f"数据导出失败: {e}")

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='交易机器人监控工具')
    parser.add_argument('--mode', choices=['monitor', 'report', 'export'], 
                       default='monitor', help='运行模式')
    parser.add_argument('--interval', type=int, default=30, 
                       help='监控刷新间隔(秒)')
    parser.add_argument('--days', type=int, default=7, 
                       help='导出数据天数')
    
    args = parser.parse_args()
    
    # 创建监控器
    monitor = TradingMonitor()
    monitor.refresh_interval = args.interval
    
    if args.mode == 'monitor':
        # 实时监控模式
        monitor.start_monitoring()
    
    elif args.mode == 'report':
        # 生成报告模式
        report = monitor.generate_report()
        print(report)
        monitor.save_report(report)
    
    elif args.mode == 'export':
        # 数据导出模式
        monitor.export_data(args.days)

if __name__ == "__main__":
    main()