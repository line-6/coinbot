#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
风险管理模块
负责止损止盈、资金管理、风险控制
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from loguru import logger
from enum import Enum

class RiskLevel(Enum):
    """风险等级"""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class RiskManager:
    """风险管理器"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.risk_config = config['strategy']['risk_management']
        self.trading_config = config['trading']
        
        # 风险状态
        self.daily_trades_count = 0
        self.daily_pnl = 0
        self.max_drawdown = 0
        self.current_drawdown = 0
        self.last_reset_date = datetime.now().date()
        
        # 交易记录
        self.trade_history = []
        self.active_stop_orders = {}
        
        logger.info("风险管理器初始化完成")
    
    def check_daily_limits(self) -> bool:
        """检查每日交易限制"""
        try:
            current_date = datetime.now().date()
            
            # 重置每日计数器
            if current_date != self.last_reset_date:
                self.daily_trades_count = 0
                self.daily_pnl = 0
                self.last_reset_date = current_date
                logger.info("每日风险计数器已重置")
            
            # 检查每日交易次数限制
            max_daily_trades = self.risk_config['max_daily_trades']
            if self.daily_trades_count >= max_daily_trades:
                logger.warning(f"已达到每日最大交易次数限制: {self.daily_trades_count}/{max_daily_trades}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"检查每日限制时出错: {e}")
            return False
    
    def check_position_size(self, amount: float, current_position: float = 0) -> bool:
        """检查持仓大小限制"""
        try:
            max_position = self.risk_config['max_position_size']
            new_position = abs(current_position + amount)
            
            if new_position > max_position:
                logger.warning(f"持仓大小超限: 新持仓={new_position:.4f}, 最大允许={max_position}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"检查持仓大小时出错: {e}")
            return False
    
    def calculate_position_size(self, account_balance: float, risk_per_trade: float = 0.02) -> float:
        """计算合适的持仓大小"""
        try:
            # 基于账户余额和风险比例计算
            base_amount = self.trading_config['trade_amount']
            
            # 风险调整
            risk_adjusted_amount = account_balance * risk_per_trade
            
            # 取较小值作为实际交易量
            calculated_amount = min(base_amount, risk_adjusted_amount)
            
            # 确保不超过最大持仓限制
            max_position = self.risk_config['max_position_size']
            final_amount = min(calculated_amount, max_position)
            
            logger.debug(f"持仓大小计算: 基础={base_amount}, 风险调整={risk_adjusted_amount:.4f}, "
                        f"最终={final_amount:.4f}")
            
            return final_amount
            
        except Exception as e:
            logger.error(f"计算持仓大小时出错: {e}")
            return self.trading_config['trade_amount']
    
    def calculate_stop_loss(self, entry_price: float, side: str, method: str = 'percentage') -> float:
        """计算止损价格"""
        try:
            stop_loss_pct = self.risk_config['stop_loss_pct'] / 100
            
            if method == 'percentage':
                if side.lower() in ['buy', 'long']:
                    stop_loss = entry_price * (1 - stop_loss_pct)
                else:  # sell, short
                    stop_loss = entry_price * (1 + stop_loss_pct)
            
            elif method == 'atr':
                # 基于ATR的动态止损(需要历史数据)
                # 这里使用固定百分比作为备选
                stop_loss = self.calculate_stop_loss(entry_price, side, 'percentage')
            
            else:
                raise ValueError(f"不支持的止损方法: {method}")
            
            logger.debug(f"止损计算: 入场价={entry_price:.4f}, 方向={side}, 止损价={stop_loss:.4f}")
            return stop_loss
            
        except Exception as e:
            logger.error(f"计算止损价格时出错: {e}")
            return 0
    
    def calculate_take_profit(self, entry_price: float, side: str, method: str = 'percentage') -> float:
        """计算止盈价格"""
        try:
            take_profit_pct = self.risk_config['take_profit_pct'] / 100
            
            if method == 'percentage':
                if side.lower() in ['buy', 'long']:
                    take_profit = entry_price * (1 + take_profit_pct)
                else:  # sell, short
                    take_profit = entry_price * (1 - take_profit_pct)
            
            elif method == 'risk_reward':
                # 基于风险回报比的止盈
                risk_reward_ratio = 2.0  # 1:2的风险回报比
                stop_loss = self.calculate_stop_loss(entry_price, side)
                
                if side.lower() in ['buy', 'long']:
                    risk_amount = entry_price - stop_loss
                    take_profit = entry_price + (risk_amount * risk_reward_ratio)
                else:
                    risk_amount = stop_loss - entry_price
                    take_profit = entry_price - (risk_amount * risk_reward_ratio)
            
            else:
                raise ValueError(f"不支持的止盈方法: {method}")
            
            logger.debug(f"止盈计算: 入场价={entry_price:.4f}, 方向={side}, 止盈价={take_profit:.4f}")
            return take_profit
            
        except Exception as e:
            logger.error(f"计算止盈价格时出错: {e}")
            return 0
    
    def check_stop_loss_trigger(self, current_price: float, entry_price: float, 
                               side: str, position_size: float) -> bool:
        """检查是否触发止损"""
        try:
            if position_size == 0:
                return False
            
            stop_loss_price = self.calculate_stop_loss(entry_price, side)
            
            # 检查止损触发条件
            if side.lower() in ['buy', 'long']:
                triggered = current_price <= stop_loss_price
            else:  # sell, short
                triggered = current_price >= stop_loss_price
            
            if triggered:
                loss_pct = abs(current_price - entry_price) / entry_price * 100
                logger.warning(f"止损触发: 当前价格={current_price:.4f}, 止损价={stop_loss_price:.4f}, "
                             f"亏损={loss_pct:.2f}%")
            
            return triggered
            
        except Exception as e:
            logger.error(f"检查止损触发时出错: {e}")
            return False
    
    def check_take_profit_trigger(self, current_price: float, entry_price: float, 
                                 side: str, position_size: float) -> bool:
        """检查是否触发止盈"""
        try:
            if position_size == 0:
                return False
            
            take_profit_price = self.calculate_take_profit(entry_price, side)
            
            # 检查止盈触发条件
            if side.lower() in ['buy', 'long']:
                triggered = current_price >= take_profit_price
            else:  # sell, short
                triggered = current_price <= take_profit_price
            
            if triggered:
                profit_pct = abs(current_price - entry_price) / entry_price * 100
                logger.info(f"止盈触发: 当前价格={current_price:.4f}, 止盈价={take_profit_price:.4f}, "
                           f"盈利={profit_pct:.2f}%")
            
            return triggered
            
        except Exception as e:
            logger.error(f"检查止盈触发时出错: {e}")
            return False
    
    def calculate_pnl(self, entry_price: float, current_price: float, 
                     position_size: float, side: str) -> float:
        """计算未实现盈亏"""
        try:
            if position_size == 0:
                return 0
            
            if side.lower() in ['buy', 'long']:
                pnl = (current_price - entry_price) * position_size
            else:  # sell, short
                pnl = (entry_price - current_price) * position_size
            
            return pnl
            
        except Exception as e:
            logger.error(f"计算盈亏时出错: {e}")
            return 0
    
    def update_drawdown(self, current_pnl: float, peak_value: float):
        """更新回撤统计"""
        try:
            # 计算当前回撤
            if peak_value > 0:
                self.current_drawdown = (peak_value - current_pnl) / peak_value * 100
            else:
                self.current_drawdown = 0
            
            # 更新最大回撤
            self.max_drawdown = max(self.max_drawdown, self.current_drawdown)
            
            logger.debug(f"回撤更新: 当前回撤={self.current_drawdown:.2f}%, "
                        f"最大回撤={self.max_drawdown:.2f}%")
            
        except Exception as e:
            logger.error(f"更新回撤时出错: {e}")
    
    def assess_risk_level(self, current_pnl: float, position_size: float, 
                         volatility: float = 0) -> RiskLevel:
        """评估当前风险等级"""
        try:
            risk_score = 0
            
            # 基于回撤的风险评分
            if self.current_drawdown > 15:
                risk_score += 3
            elif self.current_drawdown > 10:
                risk_score += 2
            elif self.current_drawdown > 5:
                risk_score += 1
            
            # 基于持仓大小的风险评分
            max_position = self.risk_config['max_position_size']
            position_ratio = abs(position_size) / max_position
            if position_ratio > 0.8:
                risk_score += 2
            elif position_ratio > 0.6:
                risk_score += 1
            
            # 基于每日交易次数的风险评分
            max_trades = self.risk_config['max_daily_trades']
            trade_ratio = self.daily_trades_count / max_trades
            if trade_ratio > 0.8:
                risk_score += 1
            
            # 确定风险等级
            if risk_score >= 5:
                risk_level = RiskLevel.CRITICAL
            elif risk_score >= 3:
                risk_level = RiskLevel.HIGH
            elif risk_score >= 1:
                risk_level = RiskLevel.MEDIUM
            else:
                risk_level = RiskLevel.LOW
            
            logger.debug(f"风险评估: 得分={risk_score}, 等级={risk_level.value}")
            return risk_level
            
        except Exception as e:
            logger.error(f"评估风险等级时出错: {e}")
            return RiskLevel.MEDIUM
    
    def should_reduce_position(self, risk_level: RiskLevel) -> bool:
        """判断是否应该减仓"""
        try:
            if risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
                logger.warning(f"风险等级过高({risk_level.value})，建议减仓")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"判断减仓时出错: {e}")
            return False
    
    def should_stop_trading(self, risk_level: RiskLevel) -> bool:
        """判断是否应该停止交易"""
        try:
            if risk_level == RiskLevel.CRITICAL:
                logger.critical("风险等级达到临界值，建议停止交易")
                return True
            
            # 检查每日亏损限制
            if self.daily_pnl < -1000:  # 可配置的每日亏损限制
                logger.warning(f"每日亏损过大({self.daily_pnl:.2f})，建议停止交易")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"判断停止交易时出错: {e}")
            return False
    
    def record_trade(self, trade_info: Dict):
        """记录交易信息"""
        try:
            trade_record = {
                'timestamp': datetime.now(),
                'symbol': trade_info.get('symbol', ''),
                'side': trade_info.get('side', ''),
                'amount': trade_info.get('amount', 0),
                'price': trade_info.get('price', 0),
                'pnl': trade_info.get('pnl', 0),
                'fee': trade_info.get('fee', 0)
            }
            
            self.trade_history.append(trade_record)
            self.daily_trades_count += 1
            self.daily_pnl += trade_record['pnl']
            
            logger.info(f"交易记录: {trade_record}")
            
        except Exception as e:
            logger.error(f"记录交易时出错: {e}")
    
    def get_risk_report(self) -> Dict:
        """生成风险报告"""
        try:
            report = {
                'daily_trades_count': self.daily_trades_count,
                'daily_pnl': self.daily_pnl,
                'max_drawdown': self.max_drawdown,
                'current_drawdown': self.current_drawdown,
                'total_trades': len(self.trade_history),
                'risk_limits': self.risk_config,
                'last_reset_date': self.last_reset_date.isoformat()
            }
            
            logger.debug(f"风险报告生成: {report}")
            return report
            
        except Exception as e:
            logger.error(f"生成风险报告时出错: {e}")
            return {}