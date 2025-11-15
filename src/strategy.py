#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
趋势跟踪量化交易策略
作者: AI Assistant
日期: 2024
"""

import pandas as pd
import warnings
import numpy as np
import ta
from typing import Dict, List, Optional, Tuple
from enum import Enum
from loguru import logger

class SignalType(Enum):
    """交易信号类型"""
    BUY = "BUY"
    SELL = "SELL"
    LONG = "LONG"    # 做多(合约)
    SHORT = "SHORT"  # 做空(合约)
    CLOSE_LONG = "CLOSE_LONG"   # 平多仓
    CLOSE_SHORT = "CLOSE_SHORT" # 平空仓
    HOLD = "HOLD"

class TrendDirection(Enum):
    """趋势方向"""
    UP = "UP"
    DOWN = "DOWN"
    SIDEWAYS = "SIDEWAYS"

class TrendFollowingStrategy:
    """趋势跟踪策略类"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.strategy_config = config['strategy']
        self.indicators_config = self.strategy_config['indicators']
        self.signals_config = self.strategy_config['signals']
        self.risk_config = self.strategy_config['risk_management']
        
        # 策略状态
        self.current_position = 0  # 当前持仓
        self.last_signal = SignalType.HOLD
        self.entry_price = 0
        self.trend_direction = TrendDirection.SIDEWAYS
        
        logger.info(f"趋势跟踪策略初始化完成: {self.strategy_config['name']}")
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算技术指标"""
        try:
          # with warnings.catch_warnings():
            # warnings.simplefilter("error", category=RuntimeWarning)
            # EMA指标
            df['ema_fast'] = ta.trend.EMAIndicator(
                df['close'], window=self.indicators_config['ema_fast']
            ).ema_indicator()
            
            df['ema_slow'] = ta.trend.EMAIndicator(
                df['close'], window=self.indicators_config['ema_slow']
            ).ema_indicator()
            
            # MACD指标
            macd = ta.trend.MACD(
                df['close'],
                window_fast=self.indicators_config['macd_fast'],
                window_slow=self.indicators_config['macd_slow'],
                window_sign=self.indicators_config['macd_signal']
            )
            df['macd'] = macd.macd()
            df['macd_signal'] = macd.macd_signal()
            df['macd_histogram'] = macd.macd_diff()
            
            # ADX趋势强度指标
            adx = ta.trend.ADXIndicator(
                df['high'], df['low'], df['close'],
                window=self.indicators_config['adx_period']
            )
            df['adx'] = adx.adx()
            df['adx_pos'] = adx.adx_pos()
            df['adx_neg'] = adx.adx_neg()
            
            # 布林带
            bb = ta.volatility.BollingerBands(
                df['close'],
                window=self.indicators_config['bb_period'],
                window_dev=self.indicators_config['bb_std']
            )
            df['bb_upper'] = bb.bollinger_hband()
            df['bb_middle'] = bb.bollinger_mavg()
            df['bb_lower'] = bb.bollinger_lband()
            df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_middle']
            
            # RSI
            df['rsi'] = ta.momentum.RSIIndicator(
                df['close'], window=self.indicators_config['rsi_period']
            ).rsi()
            
            # 成交量指标
            df['volume_sma'] = df['volume'].rolling(window=20).mean()
            df['volume_ratio'] = df['volume'] / df['volume_sma']
            
            # 价格变化率
            df['price_change'] = df['close'].pct_change()
            df['price_change_sma'] = df['price_change'].rolling(window=5).mean()
            
            logger.debug("技术指标计算完成")
            return df
        # except RuntimeWarning as e:
        #     logger.error(f"捕获到 RuntimeWarning 异常: {e}")
        #     raise

        except Exception as e:
            logger.error(f"计算技术指标时出错: {e}")
            raise
    
    def detect_trend(self, df: pd.DataFrame) -> TrendDirection:
        """检测趋势方向"""
        try:
            latest = df.iloc[-1]
            prev = df.iloc[-2] if len(df) > 1 else latest
            
            # 多重趋势确认条件
            conditions = {
                'ema_trend': latest['ema_fast'] > latest['ema_slow'],
                'macd_trend': latest['macd'] > latest['macd_signal'],
                'adx_strong': latest['adx'] > self.indicators_config['adx_threshold'],
                'price_above_bb_mid': latest['close'] > latest['bb_middle'],
                'adx_direction': latest['adx_pos'] > latest['adx_neg']
            }
            
            # 上涨趋势判断
            uptrend_score = sum([
                conditions['ema_trend'],
                conditions['macd_trend'],
                conditions['adx_strong'] and conditions['adx_direction'],
                conditions['price_above_bb_mid'],
                latest['close'] > prev['close']
            ])
            
            # 下跌趋势判断
            downtrend_score = sum([
                not conditions['ema_trend'],
                not conditions['macd_trend'],
                conditions['adx_strong'] and not conditions['adx_direction'],
                not conditions['price_above_bb_mid'],
                latest['close'] < prev['close']
            ])
            
            if uptrend_score >= 3:
                trend = TrendDirection.UP
            elif downtrend_score >= 3:
                trend = TrendDirection.DOWN
            else:
                trend = TrendDirection.SIDEWAYS
            
            logger.debug(f"趋势检测: {trend.value}, 上涨得分: {uptrend_score}, 下跌得分: {downtrend_score}")
            return trend
            
        except Exception as e:
            logger.error(f"趋势检测时出错: {e}")
            return TrendDirection.SIDEWAYS
    
    def generate_signal(self, df: pd.DataFrame) -> SignalType:
        """生成交易信号"""
        try:
            if len(df) < max(self.indicators_config.values()):
                return SignalType.HOLD
            
            latest = df.iloc[-1]
            prev = df.iloc[-2]
            
            # 检测趋势
            current_trend = self.detect_trend(df)
            self.trend_direction = current_trend
            
            # 成交量确认
            volume_confirmed = latest['volume_ratio'] > self.signals_config['volume_threshold']
            
            # 信号生成逻辑
            signal = SignalType.HOLD
            
            # 现货交易信号
            if self.config['trading']['trade_type'] == 'spot':
                # 买入信号
                if (current_trend == TrendDirection.UP and 
                    latest['ema_fast'] > latest['ema_slow'] and
                    latest['macd'] > latest['macd_signal'] and
                    latest['macd_histogram'] > prev['macd_histogram'] and
                    latest['rsi'] < self.indicators_config['rsi_overbought'] and
                    volume_confirmed and
                    self.current_position <= 0):
                    signal = SignalType.BUY
                
                # 卖出信号
                elif (current_trend == TrendDirection.DOWN and
                      latest['ema_fast'] < latest['ema_slow'] and
                      latest['macd'] < latest['macd_signal'] and
                      latest['macd_histogram'] < prev['macd_histogram'] and
                      latest['rsi'] > self.indicators_config['rsi_oversold'] and
                      volume_confirmed and
                      self.current_position > 0):
                    signal = SignalType.SELL
            
            # 合约交易信号
            elif self.config['trading']['trade_type'] == 'futures':
                # 做多信号
                if (current_trend == TrendDirection.UP and
                    latest['ema_fast'] > latest['ema_slow'] and
                    latest['macd'] > latest['macd_signal'] and
                    latest['close'] > latest['bb_middle'] and
                    volume_confirmed and
                    self.current_position <= 0):
                    signal = SignalType.LONG
                
                # 做空信号
                elif (current_trend == TrendDirection.DOWN and
                      latest['ema_fast'] < latest['ema_slow'] and
                      latest['macd'] < latest['macd_signal'] and
                      latest['close'] < latest['bb_middle'] and
                      volume_confirmed and
                      self.current_position >= 0):
                    signal = SignalType.SHORT
                
                # 平多仓信号
                elif (self.current_position > 0 and
                      (current_trend == TrendDirection.DOWN or
                       latest['ema_fast'] < latest['ema_slow'] or
                       latest['macd'] < latest['macd_signal'])):
                    signal = SignalType.CLOSE_LONG
                
                # 平空仓信号
                elif (self.current_position < 0 and
                      (current_trend == TrendDirection.UP or
                       latest['ema_fast'] > latest['ema_slow'] or
                       latest['macd'] > latest['macd_signal'])):
                    signal = SignalType.CLOSE_SHORT
            
            # 记录信号生成日志
            if signal != SignalType.HOLD:
                logger.info(f"生成交易信号: {signal.value}, 趋势: {current_trend.value}, "
                           f"价格: {latest['close']:.4f}, 成交量倍数: {latest['volume_ratio']:.2f}")
            
            self.last_signal = signal
            return signal
            
        except Exception as e:
            logger.error(f"生成交易信号时出错: {e}")
            return SignalType.HOLD
    
    def calculate_stop_loss_take_profit(self, entry_price: float, signal_type: SignalType) -> Tuple[float, float]:
        """计算止损止盈价格"""
        try:
          with warnings.catch_warnings():
            warnings.simplefilter("error", category=RuntimeWarning)
            stop_loss_pct = self.risk_config['stop_loss_pct'] / 100
            take_profit_pct = self.risk_config['take_profit_pct'] / 100
            
            if signal_type in [SignalType.BUY, SignalType.LONG]:
                stop_loss = entry_price * (1 - stop_loss_pct)
                take_profit = entry_price * (1 + take_profit_pct)
            elif signal_type in [SignalType.SELL, SignalType.SHORT]:
                stop_loss = entry_price * (1 + stop_loss_pct)
                take_profit = entry_price * (1 - take_profit_pct)
            else:
                stop_loss = take_profit = 0
            
            logger.debug(f"止损止盈计算: 入场价格={entry_price:.4f}, 止损={stop_loss:.4f}, 止盈={take_profit:.4f}")
            return stop_loss, take_profit
        except RuntimeWarning as e:
            logger.error(f"捕获到 RuntimeWarning 异常: {e}")

        except Exception as e:
            logger.error(f"计算止损止盈时出错: {e}")
            return 0, 0
    
    def update_position(self, signal_type: SignalType, amount: float, price: float):
        """更新持仓状态"""
        try:
            if signal_type in [SignalType.BUY, SignalType.LONG]:
                self.current_position += amount
                self.entry_price = price
            elif signal_type in [SignalType.SELL, SignalType.SHORT]:
                self.current_position -= amount
                self.entry_price = price
            elif signal_type in [SignalType.CLOSE_LONG, SignalType.CLOSE_SHORT]:
                self.current_position = 0
                self.entry_price = 0
            
            logger.info(f"持仓更新: 信号={signal_type.value}, 数量={amount}, 价格={price:.4f}, 当前持仓={self.current_position}")
            
        except Exception as e:
            logger.error(f"更新持仓时出错: {e}")
    
    def get_strategy_status(self) -> Dict:
        """获取策略状态"""
        return {
            'current_position': self.current_position,
            'last_signal': self.last_signal.value,
            'entry_price': self.entry_price,
            'trend_direction': self.trend_direction.value,
            'strategy_name': self.strategy_config['name']
        }