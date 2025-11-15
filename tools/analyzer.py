#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
交易策略性能分析工具
分析交易记录，生成详细的性能报告和图表
"""

import sys
import os
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import sqlite3
import yaml
import warnings
warnings.filterwarnings('ignore')

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

# 添加src目录到Python路径
src_path = Path(__file__).parent.parent / 'src'
sys.path.insert(0, str(src_path))

class PerformanceAnalyzer:
    """性能分析器"""
    
    def __init__(self, config_path: str = 'config.yaml'):
        self.config = self._load_config(config_path)
        self.db_path = Path('../data/trading_bot.db')
        self.output_dir = Path('../analysis')
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 分析参数
        self.risk_free_rate = 0.02  # 无风险利率
        self.trading_days_per_year = 252
        
    def _load_config(self, config_path: str) -> Dict:
        """加载配置文件"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"配置文件加载失败: {e}")
            return {}
    
    def load_data(self, days: int = 30) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """加载数据"""
        if not self.db_path.exists():
            raise FileNotFoundError("数据库文件不存在")
        
        conn = sqlite3.connect(self.db_path)
        
        # 计算开始日期
        start_date = (datetime.now() - timedelta(days=days)).isoformat()
        
        # 加载交易记录
        trades_query = """
            SELECT * FROM trades 
            WHERE timestamp >= ? 
            ORDER BY timestamp
        """
        trades_df = pd.read_sql_query(trades_query, conn, params=[start_date])
        
        # 加载信号记录
        signals_query = """
            SELECT * FROM signals 
            WHERE timestamp >= ? 
            ORDER BY timestamp
        """
        signals_df = pd.read_sql_query(signals_query, conn, params=[start_date])
        
        # 加载K线数据
        klines_query = """
            SELECT * FROM klines 
            WHERE timestamp >= ? 
            ORDER BY timestamp
        """
        klines_df = pd.read_sql_query(klines_query, conn, params=[start_date])
        
        conn.close()
        
        # 数据预处理
        if not trades_df.empty:
            trades_df['timestamp'] = pd.to_datetime(trades_df['timestamp'])
            trades_df['date'] = trades_df['timestamp'].dt.date
        
        if not signals_df.empty:
            signals_df['timestamp'] = pd.to_datetime(signals_df['timestamp'])
            signals_df['date'] = signals_df['timestamp'].dt.date
        
        if not klines_df.empty:
            klines_df['timestamp'] = pd.to_datetime(klines_df['timestamp'])
            klines_df['date'] = klines_df['timestamp'].dt.date
        
        return trades_df, signals_df, klines_df
    
    def calculate_basic_metrics(self, trades_df: pd.DataFrame) -> Dict:
        """计算基础指标"""
        if trades_df.empty:
            return {}
        
        # 基础统计
        total_trades = len(trades_df)
        winning_trades = len(trades_df[trades_df['pnl'] > 0])
        losing_trades = len(trades_df[trades_df['pnl'] < 0])
        
        # 盈亏统计
        total_pnl = trades_df['pnl'].sum()
        avg_pnl = trades_df['pnl'].mean()
        avg_win = trades_df[trades_df['pnl'] > 0]['pnl'].mean() if winning_trades > 0 else 0
        avg_loss = trades_df[trades_df['pnl'] < 0]['pnl'].mean() if losing_trades > 0 else 0
        
        # 胜率和盈亏比
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        profit_loss_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else 0
        
        # 最大单笔盈利和亏损
        max_win = trades_df['pnl'].max() if not trades_df.empty else 0
        max_loss = trades_df['pnl'].min() if not trades_df.empty else 0
        
        return {
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'avg_pnl': avg_pnl,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_loss_ratio': profit_loss_ratio,
            'max_win': max_win,
            'max_loss': max_loss
        }
    
    def calculate_risk_metrics(self, trades_df: pd.DataFrame) -> Dict:
        """计算风险指标"""
        if trades_df.empty:
            return {}
        
        # 累计收益曲线
        trades_df = trades_df.copy()
        trades_df['cumulative_pnl'] = trades_df['pnl'].cumsum()
        
        # 最大回撤
        peak = trades_df['cumulative_pnl'].expanding().max()
        drawdown = peak - trades_df['cumulative_pnl']
        max_drawdown = drawdown.max()
        max_drawdown_pct = (max_drawdown / peak.max() * 100) if peak.max() > 0 else 0
        
        # 回撤持续时间
        drawdown_periods = []
        in_drawdown = False
        start_idx = 0
        
        for i, dd in enumerate(drawdown):
            if dd > 0 and not in_drawdown:
                in_drawdown = True
                start_idx = i
            elif dd == 0 and in_drawdown:
                in_drawdown = False
                drawdown_periods.append(i - start_idx)
        
        max_drawdown_duration = max(drawdown_periods) if drawdown_periods else 0
        
        # 夏普比率
        returns = trades_df['pnl']
        if returns.std() > 0:
            sharpe_ratio = (returns.mean() * self.trading_days_per_year - self.risk_free_rate) / (returns.std() * np.sqrt(self.trading_days_per_year))
        else:
            sharpe_ratio = 0
        
        # 索提诺比率(只考虑下行风险)
        negative_returns = returns[returns < 0]
        if len(negative_returns) > 0 and negative_returns.std() > 0:
            sortino_ratio = (returns.mean() * self.trading_days_per_year - self.risk_free_rate) / (negative_returns.std() * np.sqrt(self.trading_days_per_year))
        else:
            sortino_ratio = 0
        
        # 卡尔马比率
        if max_drawdown_pct > 0:
            calmar_ratio = (returns.mean() * self.trading_days_per_year) / (max_drawdown_pct / 100)
        else:
            calmar_ratio = 0
        
        # 连续亏损分析
        trades_df['is_loss'] = trades_df['pnl'] < 0
        trades_df['loss_group'] = (trades_df['is_loss'] != trades_df['is_loss'].shift()).cumsum()
        loss_streaks = trades_df[trades_df['is_loss']].groupby('loss_group').size()
        max_consecutive_losses = loss_streaks.max() if not loss_streaks.empty else 0
        
        # 连续盈利分析
        trades_df['is_win'] = trades_df['pnl'] > 0
        trades_df['win_group'] = (trades_df['is_win'] != trades_df['is_win'].shift()).cumsum()
        win_streaks = trades_df[trades_df['is_win']].groupby('win_group').size()
        max_consecutive_wins = win_streaks.max() if not win_streaks.empty else 0
        
        return {
            'max_drawdown': max_drawdown,
            'max_drawdown_pct': max_drawdown_pct,
            'max_drawdown_duration': max_drawdown_duration,
            'sharpe_ratio': sharpe_ratio,
            'sortino_ratio': sortino_ratio,
            'calmar_ratio': calmar_ratio,
            'max_consecutive_losses': max_consecutive_losses,
            'max_consecutive_wins': max_consecutive_wins
        }
    
    def analyze_signal_performance(self, trades_df: pd.DataFrame, signals_df: pd.DataFrame) -> Dict:
        """分析信号表现"""
        if signals_df.empty:
            return {}
        
        # 信号统计
        signal_counts = signals_df['signal_type'].value_counts().to_dict()
        
        # 信号准确率(如果有对应的交易记录)
        signal_accuracy = {}
        if not trades_df.empty:
            # 简化分析：假设信号和交易在时间上相近
            for signal_type in signals_df['signal_type'].unique():
                signal_trades = []
                signal_data = signals_df[signals_df['signal_type'] == signal_type]
                
                for _, signal in signal_data.iterrows():
                    # 查找信号后1小时内的交易
                    signal_time = signal['timestamp']
                    nearby_trades = trades_df[
                        (trades_df['timestamp'] >= signal_time) & 
                        (trades_df['timestamp'] <= signal_time + timedelta(hours=1))
                    ]
                    
                    if not nearby_trades.empty:
                        signal_trades.extend(nearby_trades['pnl'].tolist())
                
                if signal_trades:
                    profitable_signals = len([pnl for pnl in signal_trades if pnl > 0])
                    signal_accuracy[signal_type] = {
                        'total': len(signal_trades),
                        'profitable': profitable_signals,
                        'accuracy': profitable_signals / len(signal_trades) * 100,
                        'avg_pnl': np.mean(signal_trades)
                    }
        
        return {
            'signal_counts': signal_counts,
            'signal_accuracy': signal_accuracy
        }
    
    def generate_charts(self, trades_df: pd.DataFrame, klines_df: pd.DataFrame, signals_df: pd.DataFrame):
        """生成图表"""
        if trades_df.empty:
            print("无交易数据，跳过图表生成")
            return
        
        # 设置图表样式
        plt.style.use('seaborn-v0_8')
        fig = plt.figure(figsize=(20, 24))
        
        # 1. 累计收益曲线
        ax1 = plt.subplot(4, 2, 1)
        trades_df_copy = trades_df.copy()
        trades_df_copy['cumulative_pnl'] = trades_df_copy['pnl'].cumsum()
        plt.plot(trades_df_copy['timestamp'], trades_df_copy['cumulative_pnl'], 'b-', linewidth=2)
        plt.title('累计收益曲线', fontsize=14, fontweight='bold')
        plt.xlabel('时间')
        plt.ylabel('累计盈亏')
        plt.grid(True, alpha=0.3)
        plt.xticks(rotation=45)
        
        # 2. 回撤曲线
        ax2 = plt.subplot(4, 2, 2)
        peak = trades_df_copy['cumulative_pnl'].expanding().max()
        drawdown = (peak - trades_df_copy['cumulative_pnl']) / peak * 100
        plt.fill_between(trades_df_copy['timestamp'], 0, -drawdown, color='red', alpha=0.3)
        plt.plot(trades_df_copy['timestamp'], -drawdown, 'r-', linewidth=1)
        plt.title('回撤曲线', fontsize=14, fontweight='bold')
        plt.xlabel('时间')
        plt.ylabel('回撤 (%)')
        plt.grid(True, alpha=0.3)
        plt.xticks(rotation=45)
        
        # 3. 每日盈亏分布
        ax3 = plt.subplot(4, 2, 3)
        daily_pnl = trades_df.groupby('date')['pnl'].sum()
        colors = ['green' if x > 0 else 'red' for x in daily_pnl]
        plt.bar(range(len(daily_pnl)), daily_pnl, color=colors, alpha=0.7)
        plt.title('每日盈亏分布', fontsize=14, fontweight='bold')
        plt.xlabel('交易日')
        plt.ylabel('每日盈亏')
        plt.grid(True, alpha=0.3)
        plt.axhline(y=0, color='black', linestyle='-', alpha=0.5)
        
        # 4. 盈亏分布直方图
        ax4 = plt.subplot(4, 2, 4)
        plt.hist(trades_df['pnl'], bins=30, alpha=0.7, color='skyblue', edgecolor='black')
        plt.axvline(trades_df['pnl'].mean(), color='red', linestyle='--', label=f'平均值: {trades_df["pnl"].mean():.4f}')
        plt.title('单笔交易盈亏分布', fontsize=14, fontweight='bold')
        plt.xlabel('盈亏')
        plt.ylabel('频次')
        plt.legend()
        plt.grid(True, alpha=0.3)
        
        # 5. 交易量分析
        ax5 = plt.subplot(4, 2, 5)
        if not klines_df.empty:
            plt.plot(klines_df['timestamp'], klines_df['close'], 'b-', alpha=0.7, label='价格')
            
            # 标记交易点
            buy_trades = trades_df[trades_df['side'] == 'buy']
            sell_trades = trades_df[trades_df['side'] == 'sell']
            
            if not buy_trades.empty:
                plt.scatter(buy_trades['timestamp'], buy_trades['price'], 
                           color='green', marker='^', s=50, label='买入', alpha=0.8)
            
            if not sell_trades.empty:
                plt.scatter(sell_trades['timestamp'], sell_trades['price'], 
                           color='red', marker='v', s=50, label='卖出', alpha=0.8)
            
            plt.title('价格走势与交易点', fontsize=14, fontweight='bold')
            plt.xlabel('时间')
            plt.ylabel('价格')
            plt.legend()
            plt.grid(True, alpha=0.3)
            plt.xticks(rotation=45)
        
        # 6. 信号分析
        ax6 = plt.subplot(4, 2, 6)
        if not signals_df.empty:
            signal_counts = signals_df['signal_type'].value_counts()
            plt.pie(signal_counts.values, labels=signal_counts.index, autopct='%1.1f%%')
            plt.title('信号类型分布', fontsize=14, fontweight='bold')
        
        # 7. 月度表现
        ax7 = plt.subplot(4, 2, 7)
        trades_df_copy['month'] = trades_df_copy['timestamp'].dt.to_period('M')
        monthly_pnl = trades_df_copy.groupby('month')['pnl'].sum()
        colors = ['green' if x > 0 else 'red' for x in monthly_pnl]
        plt.bar(range(len(monthly_pnl)), monthly_pnl, color=colors, alpha=0.7)
        plt.title('月度盈亏', fontsize=14, fontweight='bold')
        plt.xlabel('月份')
        plt.ylabel('月度盈亏')
        plt.grid(True, alpha=0.3)
        plt.axhline(y=0, color='black', linestyle='-', alpha=0.5)
        
        # 8. 胜率分析
        ax8 = plt.subplot(4, 2, 8)
        win_loss_data = ['盈利', '亏损']
        win_loss_counts = [len(trades_df[trades_df['pnl'] > 0]), len(trades_df[trades_df['pnl'] < 0])]
        colors = ['green', 'red']
        plt.pie(win_loss_counts, labels=win_loss_data, colors=colors, autopct='%1.1f%%')
        plt.title('盈亏比例', fontsize=14, fontweight='bold')
        
        plt.tight_layout()
        
        # 保存图表
        chart_path = self.output_dir / f'performance_analysis_{datetime.now().strftime("%Y%m%d_%H%M%S")}.png'
        plt.savefig(chart_path, dpi=300, bbox_inches='tight')
        print(f"图表已保存: {chart_path}")
        
        plt.show()
    
    def generate_report(self, days: int = 30) -> str:
        """生成完整分析报告"""
        try:
            # 加载数据
            trades_df, signals_df, klines_df = self.load_data(days)
            
            if trades_df.empty:
                return "无交易数据可分析"
            
            # 计算指标
            basic_metrics = self.calculate_basic_metrics(trades_df)
            risk_metrics = self.calculate_risk_metrics(trades_df)
            signal_metrics = self.analyze_signal_performance(trades_df, signals_df)
            
            # 生成报告
            report = f"""
╔══════════════════════════════════════════════════════════════════════════════════════╗
║                                交易策略性能分析报告                                    ║
╠══════════════════════════════════════════════════════════════════════════════════════╣
║ 分析期间: {(datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')} 至 {datetime.now().strftime('%Y-%m-%d')} (共 {days} 天)                     ║
║ 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}                                                    ║
╠══════════════════════════════════════════════════════════════════════════════════════╣
║ 基础指标                                                                             ║
║ • 总交易次数:     {basic_metrics.get('total_trades', 0):>6}                                                ║
║ • 盈利交易:       {basic_metrics.get('winning_trades', 0):>6}                                                ║
║ • 亏损交易:       {basic_metrics.get('losing_trades', 0):>6}                                                ║
║ • 胜率:           {basic_metrics.get('win_rate', 0):>6.2f}%                                              ║
║ • 总盈亏:         {basic_metrics.get('total_pnl', 0):>10.4f}                                          ║
║ • 平均盈亏:       {basic_metrics.get('avg_pnl', 0):>10.4f}                                          ║
║ • 平均盈利:       {basic_metrics.get('avg_win', 0):>10.4f}                                          ║
║ • 平均亏损:       {basic_metrics.get('avg_loss', 0):>10.4f}                                          ║
║ • 盈亏比:         {basic_metrics.get('profit_loss_ratio', 0):>6.2f}                                              ║
║ • 最大单笔盈利:   {basic_metrics.get('max_win', 0):>10.4f}                                          ║
║ • 最大单笔亏损:   {basic_metrics.get('max_loss', 0):>10.4f}                                          ║
╠══════════════════════════════════════════════════════════════════════════════════════╣
║ 风险指标                                                                             ║
║ • 最大回撤:       {risk_metrics.get('max_drawdown', 0):>10.4f}                                          ║
║ • 最大回撤率:     {risk_metrics.get('max_drawdown_pct', 0):>6.2f}%                                              ║
║ • 回撤持续期:     {risk_metrics.get('max_drawdown_duration', 0):>6} 笔交易                                        ║
║ • 夏普比率:       {risk_metrics.get('sharpe_ratio', 0):>6.2f}                                              ║
║ • 索提诺比率:     {risk_metrics.get('sortino_ratio', 0):>6.2f}                                              ║
║ • 卡尔马比率:     {risk_metrics.get('calmar_ratio', 0):>6.2f}                                              ║
║ • 最大连续亏损:   {risk_metrics.get('max_consecutive_losses', 0):>6} 笔                                            ║
║ • 最大连续盈利:   {risk_metrics.get('max_consecutive_wins', 0):>6} 笔                                            ║
╠══════════════════════════════════════════════════════════════════════════════════════╣
"""
            
            # 添加信号分析
            if signal_metrics.get('signal_counts'):
                report += "║ 信号分析                                                                             ║\n"
                for signal_type, count in signal_metrics['signal_counts'].items():
                    report += f"║ • {signal_type:<12}: {count:>6} 次                                                        ║\n"
                
                if signal_metrics.get('signal_accuracy'):
                    report += "║                                                                                      ║\n"
                    report += "║ 信号准确率                                                                           ║\n"
                    for signal_type, accuracy in signal_metrics['signal_accuracy'].items():
                        report += f"║ • {signal_type:<12}: {accuracy['accuracy']:>6.2f}% ({accuracy['profitable']}/{accuracy['total']})                                    ║\n"
                
                report += "╠══════════════════════════════════════════════════════════════════════════════════════╣\n"
            
            # 添加评级
            score = self._calculate_strategy_score(basic_metrics, risk_metrics)
            rating = self._get_strategy_rating(score)
            
            report += f"""║ 策略评级                                                                             ║
║ • 综合得分:       {score:>6.1f}/100                                                        ║
║ • 策略评级:       {rating:>6}                                                            ║
╚══════════════════════════════════════════════════════════════════════════════════════╝
"""
            
            return report
            
        except Exception as e:
            return f"生成报告失败: {e}"
    
    def _calculate_strategy_score(self, basic_metrics: Dict, risk_metrics: Dict) -> float:
        """计算策略综合得分"""
        score = 0
        
        # 胜率得分 (30分)
        win_rate = basic_metrics.get('win_rate', 0)
        if win_rate >= 60:
            score += 30
        elif win_rate >= 50:
            score += 25
        elif win_rate >= 40:
            score += 20
        elif win_rate >= 30:
            score += 15
        else:
            score += 10
        
        # 盈亏比得分 (25分)
        profit_loss_ratio = basic_metrics.get('profit_loss_ratio', 0)
        if profit_loss_ratio >= 2.0:
            score += 25
        elif profit_loss_ratio >= 1.5:
            score += 20
        elif profit_loss_ratio >= 1.2:
            score += 15
        elif profit_loss_ratio >= 1.0:
            score += 10
        else:
            score += 5
        
        # 夏普比率得分 (25分)
        sharpe_ratio = risk_metrics.get('sharpe_ratio', 0)
        if sharpe_ratio >= 2.0:
            score += 25
        elif sharpe_ratio >= 1.5:
            score += 20
        elif sharpe_ratio >= 1.0:
            score += 15
        elif sharpe_ratio >= 0.5:
            score += 10
        else:
            score += 5
        
        # 最大回撤得分 (20分)
        max_drawdown_pct = risk_metrics.get('max_drawdown_pct', 100)
        if max_drawdown_pct <= 5:
            score += 20
        elif max_drawdown_pct <= 10:
            score += 15
        elif max_drawdown_pct <= 20:
            score += 10
        elif max_drawdown_pct <= 30:
            score += 5
        else:
            score += 0
        
        return min(score, 100)
    
    def _get_strategy_rating(self, score: float) -> str:
        """获取策略评级"""
        if score >= 90:
            return "优秀"
        elif score >= 80:
            return "良好"
        elif score >= 70:
            return "中等"
        elif score >= 60:
            return "及格"
        else:
            return "较差"
    
    def save_report(self, report: str, filename: str = None):
        """保存报告"""
        try:
            if filename is None:
                filename = f"performance_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            
            with open(self.output_dir / filename, 'w', encoding='utf-8') as f:
                f.write(report)
            
            print(f"报告已保存: {self.output_dir / filename}")
            
        except Exception as e:
            print(f"保存报告失败: {e}")
    
    def run_full_analysis(self, days: int = 30, save_charts: bool = True):
        """运行完整分析"""
        print(f"开始分析最近 {days} 天的交易数据...")
        
        try:
            # 加载数据
            trades_df, signals_df, klines_df = self.load_data(days)
            
            if trades_df.empty:
                print("无交易数据可分析")
                return
            
            # 生成报告
            report = self.generate_report(days)
            print(report)
            self.save_report(report)
            
            # 生成图表
            if save_charts:
                print("\n生成分析图表...")
                self.generate_charts(trades_df, klines_df, signals_df)
            
            print("\n分析完成!")
            
        except Exception as e:
            print(f"分析失败: {e}")

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='交易策略性能分析工具')
    parser.add_argument('--days', type=int, default=30, help='分析天数')
    parser.add_argument('--no-charts', action='store_true', help='不生成图表')
    parser.add_argument('--report-only', action='store_true', help='仅生成报告')
    
    args = parser.parse_args()
    
    # 创建分析器
    analyzer = PerformanceAnalyzer()
    
    if args.report_only:
        # 仅生成报告
        report = analyzer.generate_report(args.days)
        print(report)
        analyzer.save_report(report)
    else:
        # 运行完整分析
        analyzer.run_full_analysis(args.days, not args.no_charts)

if __name__ == "__main__":
    main()