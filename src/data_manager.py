#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据管理模块
负责交易数据存储、历史记录管理、数据分析
"""

import pandas as pd
import numpy as np
import os
import json
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from loguru import logger
import sqlite3
from pathlib import Path

class DataManager:
    """数据管理器"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.data_config = config.get('data', {})
        
        # 创建数据目录
        self.data_dir = Path('data')
        self.logs_dir = Path('logs')
        self.data_dir.mkdir(exist_ok=True)
        self.logs_dir.mkdir(exist_ok=True)
        
        # 数据文件路径
        self.trades_file = self.data_dir / 'trades.csv'
        self.klines_file = self.data_dir / 'klines.csv'
        self.signals_file = self.data_dir / 'signals.csv'
        self.performance_file = self.data_dir / 'performance.json'
        self.db_file = self.data_dir / 'trading_bot.db'
        
        # 初始化数据库
        self._init_database()
        
        logger.info("数据管理器初始化完成")
    
    def _init_database(self):
        """初始化SQLite数据库"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            # 创建交易记录表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    amount REAL NOT NULL,
                    price REAL NOT NULL,
                    value REAL NOT NULL,
                    fee REAL DEFAULT 0,
                    pnl REAL DEFAULT 0,
                    signal_type TEXT,
                    order_id TEXT,
                    status TEXT DEFAULT 'completed'
                )
            ''')
            
            # 创建K线数据表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS klines (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume REAL NOT NULL,
                    UNIQUE(timestamp, symbol, timeframe)
                )
            ''')
            
            # 创建信号记录表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    signal_type TEXT NOT NULL,
                    price REAL NOT NULL,
                    confidence REAL DEFAULT 0,
                    indicators TEXT,
                    executed BOOLEAN DEFAULT FALSE
                )
            ''')
            
            # 创建性能统计表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS performance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL UNIQUE,
                    total_trades INTEGER DEFAULT 0,
                    winning_trades INTEGER DEFAULT 0,
                    losing_trades INTEGER DEFAULT 0,
                    total_pnl REAL DEFAULT 0,
                    max_drawdown REAL DEFAULT 0,
                    sharpe_ratio REAL DEFAULT 0,
                    win_rate REAL DEFAULT 0
                )
            ''')
            
            conn.commit()
            conn.close()
            
            logger.info("数据库初始化完成")
            
        except Exception as e:
            logger.error(f"数据库初始化失败: {e}")
            raise
    
    def save_trade(self, trade_data: Dict):
        """保存交易记录"""
        try:
            # 保存到数据库
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO trades (
                    timestamp, symbol, side, amount, price, value, 
                    fee, pnl, signal_type, order_id, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                trade_data.get('timestamp', datetime.now().isoformat()),
                trade_data.get('symbol', ''),
                trade_data.get('side', ''),
                trade_data.get('amount', 0),
                trade_data.get('price', 0),
                trade_data.get('value', 0),
                trade_data.get('fee', 0),
                trade_data.get('pnl', 0),
                trade_data.get('signal_type', ''),
                trade_data.get('order_id', ''),
                trade_data.get('status', 'completed')
            ))
            
            conn.commit()
            conn.close()
            
            # 保存到CSV文件(如果配置启用)
            if self.data_config.get('save_trades', True):
                self._save_to_csv(trade_data, self.trades_file)
            
            logger.info(f"交易记录保存成功: {trade_data.get('side')} {trade_data.get('amount')} @ {trade_data.get('price')}")
            
        except Exception as e:
            logger.error(f"保存交易记录失败: {e}")
    
    def save_klines(self, klines_data: pd.DataFrame, symbol: str, timeframe: str):
        """保存K线数据"""
        try:
            # 保存到数据库
            conn = sqlite3.connect(self.db_file)
            
            for index, row in klines_data.iterrows():
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO klines (
                        timestamp, symbol, timeframe, open, high, low, close, volume
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    index.isoformat() if hasattr(index, 'isoformat') else str(index),
                    symbol,
                    timeframe,
                    float(row['open']),
                    float(row['high']),
                    float(row['low']),
                    float(row['close']),
                    float(row['volume'])
                ))
            
            conn.commit()
            conn.close()
            
            # 保存到CSV文件(如果配置启用)
            if self.data_config.get('save_klines', True):
                klines_data.to_csv(self.klines_file, mode='a', header=not self.klines_file.exists())
            
            logger.debug(f"K线数据保存成功: {len(klines_data)}条记录")
            
        except Exception as e:
            logger.error(f"保存K线数据失败: {e}")
    
    def save_signal(self, signal_data: Dict):
        """保存交易信号"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO signals (
                    timestamp, symbol, signal_type, price, confidence, indicators, executed
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                signal_data.get('timestamp', datetime.now().isoformat()),
                signal_data.get('symbol', ''),
                signal_data.get('signal_type', ''),
                signal_data.get('price', 0),
                signal_data.get('confidence', 0),
                json.dumps(signal_data.get('indicators', {})),
                signal_data.get('executed', False)
            ))
            
            conn.commit()
            conn.close()
            
            logger.debug(f"交易信号保存到数据库成功: {signal_data.get('signal_type')} @ {signal_data.get('price')}")
            
            # 保存到CSV文件(如果配置启用)
            if self.data_config.get('save_signals', True):
                # self._save_to_csv(trade_data, self.trades_file)
                self._save_to_csv(signal_data, self.signals_file)
            
            logger.debug(f"signal数据保存到csv成功: {len(signal_data)}条记录")

        except Exception as e:
            logger.error(f"保存交易信号失败: {e}")
    
    def _save_to_csv(self, data: Dict, file_path: Path):
        """保存数据到CSV文件"""
        try:
            df = pd.DataFrame([data])
            df.to_csv(file_path, mode='a', header=not file_path.exists(), index=False)
            
        except Exception as e:
            logger.error(f"保存CSV文件失败: {e}")
    
    def load_trades(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> pd.DataFrame:
        """加载交易记录"""
        try:
            conn = sqlite3.connect(self.db_file)
            
            query = "SELECT * FROM trades"
            params = []
            
            if start_date or end_date:
                query += " WHERE"
                conditions = []
                
                if start_date:
                    conditions.append(" timestamp >= ?")
                    params.append(start_date)
                
                if end_date:
                    conditions.append(" timestamp <= ?")
                    params.append(end_date)
                
                query += " AND".join(conditions)
            
            query += " ORDER BY timestamp DESC"
            
            df = pd.read_sql_query(query, conn, params=params)
            conn.close()
            
            if not df.empty:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
            
            logger.debug(f"加载交易记录: {len(df)}条")
            return df
            
        except Exception as e:
            logger.error(f"加载交易记录失败: {e}")
            return pd.DataFrame()
    
    def load_klines(self, symbol: str, timeframe: str, limit: int = 1000) -> pd.DataFrame:
        """加载K线数据"""
        try:
            conn = sqlite3.connect(self.db_file)
            
            query = '''
                SELECT timestamp, open, high, low, close, volume 
                FROM klines 
                WHERE symbol = ? AND timeframe = ? 
                ORDER BY timestamp DESC 
                LIMIT ?
            '''
            
            df = pd.read_sql_query(query, conn, params=[symbol, timeframe, limit])
            conn.close()
            
            if not df.empty:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df.set_index('timestamp', inplace=True)
                df = df.sort_index()  # 按时间正序排列
            
            logger.debug(f"加载K线数据: {len(df)}条")
            return df
            
        except Exception as e:
            logger.error(f"加载K线数据失败: {e}")
            return pd.DataFrame()
    
    def load_signals(self, start_date: Optional[str] = None, limit: int = 100) -> pd.DataFrame:
        """加载交易信号"""
        try:
            conn = sqlite3.connect(self.db_file)
            
            query = "SELECT * FROM signals"
            params = []
            
            if start_date:
                query += " WHERE timestamp >= ?"
                params.append(start_date)
            
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            
            df = pd.read_sql_query(query, conn, params=params)
            conn.close()
            
            if not df.empty:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
            
            logger.debug(f"加载交易信号: {len(df)}条")
            return df
            
        except Exception as e:
            logger.error(f"加载交易信号失败: {e}")
            return pd.DataFrame()
    
    def calculate_performance_metrics(self, trades_df: pd.DataFrame) -> Dict:
        """计算性能指标"""
        try:
            if trades_df.empty:
                return {}
            
            # 基础统计
            total_trades = len(trades_df)
            winning_trades = len(trades_df[trades_df['pnl'] > 0])
            losing_trades = len(trades_df[trades_df['pnl'] < 0])
            
            # 盈亏统计
            total_pnl = trades_df['pnl'].sum()
            avg_pnl = trades_df['pnl'].mean()
            max_profit = trades_df['pnl'].max()
            max_loss = trades_df['pnl'].min()
            
            # 胜率
            win_rate = winning_trades / total_trades * 100 if total_trades > 0 else 0
            
            # 盈亏比
            avg_profit = trades_df[trades_df['pnl'] > 0]['pnl'].mean() if winning_trades > 0 else 0
            avg_loss = abs(trades_df[trades_df['pnl'] < 0]['pnl'].mean()) if losing_trades > 0 else 0
            profit_loss_ratio = avg_profit / avg_loss if avg_loss > 0 else 0
            
            # 最大回撤
            cumulative_pnl = trades_df['pnl'].cumsum()
            running_max = cumulative_pnl.expanding().max()
            drawdown = (running_max - cumulative_pnl) / running_max * 100
            max_drawdown = drawdown.max() if not drawdown.empty else 0
            
            # 夏普比率(简化计算)
            if trades_df['pnl'].std() > 0:
                sharpe_ratio = avg_pnl / trades_df['pnl'].std() * np.sqrt(252)  # 年化
            else:
                sharpe_ratio = 0
            
            metrics = {
                'total_trades': total_trades,
                'winning_trades': winning_trades,
                'losing_trades': losing_trades,
                'win_rate': round(win_rate, 2),
                'total_pnl': round(total_pnl, 4),
                'avg_pnl': round(avg_pnl, 4),
                'max_profit': round(max_profit, 4),
                'max_loss': round(max_loss, 4),
                'profit_loss_ratio': round(profit_loss_ratio, 2),
                'max_drawdown': round(max_drawdown, 2),
                'sharpe_ratio': round(sharpe_ratio, 2)
            }
            
            logger.info(f"性能指标计算完成: 胜率={win_rate:.1f}%, 总盈亏={total_pnl:.4f}")
            return metrics
            
        except Exception as e:
            logger.error(f"计算性能指标失败: {e}")
            return {}
    
    def save_performance_metrics(self, metrics: Dict, date: str = None):
        """保存性能指标"""
        try:
            if date is None:
                date = datetime.now().date().isoformat()
            
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO performance (
                    date, total_trades, winning_trades, losing_trades, 
                    total_pnl, max_drawdown, sharpe_ratio, win_rate
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                date,
                metrics.get('total_trades', 0),
                metrics.get('winning_trades', 0),
                metrics.get('losing_trades', 0),
                metrics.get('total_pnl', 0),
                metrics.get('max_drawdown', 0),
                metrics.get('sharpe_ratio', 0),
                metrics.get('win_rate', 0)
            ))
            
            conn.commit()
            conn.close()
            
            # 同时保存到JSON文件
            with open(self.performance_file, 'w') as f:
                json.dump(metrics, f, indent=2)
            
            logger.info(f"性能指标保存成功: {date}")
            
        except Exception as e:
            logger.error(f"保存性能指标失败: {e}")
    
    def get_daily_summary(self, date: str = None) -> Dict:
        """获取每日交易摘要"""
        try:
            if date is None:
                date = datetime.now().date().isoformat()
            
            start_date = f"{date} 00:00:00"
            end_date = f"{date} 23:59:59"
            
            trades_df = self.load_trades(start_date, end_date)
            
            if trades_df.empty:
                return {'date': date, 'no_trades': True}
            
            metrics = self.calculate_performance_metrics(trades_df)
            metrics['date'] = date
            
            return metrics
            
        except Exception as e:
            logger.error(f"获取每日摘要失败: {e}")
            return {}
    
    def cleanup_old_data(self, days_to_keep: int = 30):
        """清理旧数据"""
        try:
            cutoff_date = (datetime.now() - timedelta(days=days_to_keep)).isoformat()
            
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            # 清理旧的K线数据
            cursor.execute("DELETE FROM klines WHERE timestamp < ?", (cutoff_date,))
            
            # 清理旧的信号数据
            cursor.execute("DELETE FROM signals WHERE timestamp < ?", (cutoff_date,))
            
            conn.commit()
            conn.close()
            
            logger.info(f"清理{days_to_keep}天前的旧数据完成")
            
        except Exception as e:
            logger.error(f"清理旧数据失败: {e}")
    
    def export_data(self, export_type: str = 'csv', date_range: Optional[tuple[str, str]] = None):
        """导出数据"""
        try:
            export_dir = self.data_dir / 'exports'
            export_dir.mkdir(exist_ok=True)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            
            if export_type == 'csv':
                # 导出交易记录
                trades_df = self.load_trades(
                    date_range[0] if date_range else None,
                    date_range[1] if date_range else None
                )
                if not trades_df.empty:
                    trades_df.to_csv(export_dir / f'trades_{timestamp}.csv', index=False)
                
                # 导出信号记录
                signals_df = self.load_signals(
                    date_range[0] if date_range else None
                )
                if not signals_df.empty:
                    signals_df.to_csv(export_dir / f'signals_{timestamp}.csv', index=False)
            
            logger.info(f"数据导出完成: {export_dir}")
            
        except Exception as e:
            logger.error(f"数据导出失败: {e}")