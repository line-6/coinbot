#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
交易所接口封装
支持币安现货和合约交易
"""

import ccxt
import pandas as pd
import time
from typing import Dict, List, Optional, Tuple
from loguru import logger
from datetime import datetime, timedelta

class ExchangeInterface:
    """交易所接口类"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.exchange_config = config['exchange']
        self.trading_config = config['trading']
        
        # 初始化交易所
        self.exchange = self._init_exchange()
        self.symbol = self.trading_config['symbol']
        self.timeframe = self.trading_config['timeframe']
        
        # 交易状态
        # self.is_connected = False
        self.last_price = 0
        
        logger.info(f"交易所接口初始化: {self.exchange_config['name']}")
    
    def _init_exchange(self) -> ccxt.Exchange:
        """初始化交易所连接"""
        try:
            exchange = ccxt.binance({
                "apiKey": self.exchange_config['apiKey'],
                "secret": self.exchange_config['secretKey'],
                "enableRateLimit": True,
                'rateLimit': self.exchange_config.get('rateLimit', 1200),
                'enableRateLimit': self.exchange_config.get('enableRateLimit', True),
                'options': {
                    'defaultType': 'spot' if self.trading_config['trade_type'] == 'spot' else 'future'
                }
            })
            exchange.set_sandbox_mode(True)
            # exchange_class = getattr(ccxt, self.exchange_config['name'])
            # exchange = exchange_class({
            #     'apiKey': self.exchange_config['apiKey'],
            #     'secret': self.exchange_config['secretKey'],
            #     'sandbox': self.exchange_config.get('sandbox', False),
            #     'rateLimit': self.exchange_config.get('rateLimit', 1200),
            #     'enableRateLimit': self.exchange_config.get('enableRateLimit', True),
            #     'options': {
            #         'defaultType': 'spot' if self.trading_config['trade_type'] == 'spot' else 'future'
            #     }
            # })
            #print(exchange)
            # 测试连接
            exchange.load_markets()
            self.is_connected = True
            logger.info(f"交易所连接成功: {exchange.name}")
            return exchange
            
        except Exception as e:
            logger.error(f"交易所连接失败: {e}")
            raise
    
    def get_klines(self, limit: int = 100) -> pd.DataFrame:
        """获取K线数据"""
        try:
            # 获取OHLCV数据
            ohlcv = self.exchange.fetch_ohlcv(
                symbol=self.symbol,
                timeframe=self.timeframe,
                limit=limit
            )
            
            # 转换为DataFrame
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            
            # 数据类型转换
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            self.last_price = float(df['close'].iloc[-1])
            logger.debug(f"获取K线数据成功: {len(df)}条, 最新价格: {self.last_price:.4f}")
            return df
            
        except Exception as e:
            logger.error(f"获取K线数据失败: {e}")
            raise
    
    def get_ticker(self) -> Dict:
        """获取实时价格信息"""
        try:
            ticker = self.exchange.fetch_ticker(self.symbol)
            self.last_price = float(ticker['last'])
            
            logger.debug(f"获取实时价格: {self.last_price:.4f}")
            return ticker
            
        except Exception as e:
            logger.error(f"获取实时价格失败: {e}")
            raise
    
    def get_balance(self) -> Dict:
        """获取账户余额"""
        try:
            balance = self.exchange.fetch_balance()
            
            # 提取相关币种余额
            base_currency = self.trading_config['base_currency']
            quote_currency = self.trading_config['quote_currency']
            
            result = {
                base_currency: {
                    'free': balance.get(base_currency, {}).get('free', 0),
                    'used': balance.get(base_currency, {}).get('used', 0),
                    'total': balance.get(base_currency, {}).get('total', 0)
                },
                quote_currency: {
                    'free': balance.get(quote_currency, {}).get('free', 0),
                    'used': balance.get(quote_currency, {}).get('used', 0),
                    'total': balance.get(quote_currency, {}).get('total', 0)
                }
            }
            
            logger.debug(f"账户余额: {base_currency}={result[base_currency]['total']:.4f}, "
                        f"{quote_currency}={result[quote_currency]['total']:.4f}")
            return result
            
        except Exception as e:
            logger.error(f"获取账户余额失败: {e}")
            raise
    
    def place_market_order(self, side: str, amount: float, price: Optional[float] = None) -> Dict:
        """下市价单"""
        try:
            # 参数验证
            if side not in ['buy', 'sell']:
                raise ValueError(f"无效的交易方向: {side}")
            
            if amount <= 0:
                raise ValueError(f"无效的交易数量: {amount}")
            
            # 下单
            order = self.exchange.create_market_order(
                symbol=self.symbol,
                side=side,
                amount=amount
            )
            
            logger.info(f"市价单下单成功: {side} {amount} {self.symbol}, 订单ID: {order['id']}")
            return order
            
        except Exception as e:
            logger.error(f"市价单下单失败: {e}")
            raise
    
    def place_limit_order(self, side: str, amount: float, price: float) -> Dict:
        """下限价单"""
        try:
            # 参数验证
            if side not in ['buy', 'sell']:
                raise ValueError(f"无效的交易方向: {side}")
            
            if amount <= 0 or price <= 0:
                raise ValueError(f"无效的交易参数: amount={amount}, price={price}")
            
            # 下单
            order = self.exchange.create_limit_order(
                symbol=self.symbol,
                side=side,
                amount=amount,
                price=price
            )
            
            logger.info(f"限价单下单成功: {side} {amount} {self.symbol} @ {price:.4f}, 订单ID: {order['id']}")
            return order
            
        except Exception as e:
            logger.error(f"限价单下单失败: {e}")
            raise
    
    def place_stop_order(self, side: str, amount: float, stop_price: float, limit_price: Optional[float] = None) -> Dict:
        """下止损单"""
        try:
            # 参数验证
            if side not in ['buy', 'sell']:
                raise ValueError(f"无效的交易方向: {side}")
            
            if amount <= 0 or stop_price <= 0:
                raise ValueError(f"无效的止损参数: amount={amount}, stop_price={stop_price}")
            
            # 构建止损单参数
            params = {
                'stopPrice': stop_price,
                'type': 'STOP_LOSS_LIMIT' if limit_price else 'STOP_LOSS'
            }
            
            if limit_price:
                params['price'] = limit_price
                order = self.exchange.create_order(
                    symbol=self.symbol,
                    type='limit',
                    side=side,
                    amount=amount,
                    price=limit_price,
                    params=params
                )
            else:
                order = self.exchange.create_order(
                    symbol=self.symbol,
                    type='market',
                    side=side,
                    amount=amount,
                    params=params
                )
            
            logger.info(f"止损单下单成功: {side} {amount} {self.symbol}, 止损价: {stop_price:.4f}, 订单ID: {order['id']}")
            return order
            
        except Exception as e:
            logger.error(f"止损单下单失败: {e}")
            raise
    
    def cancel_order(self, order_id: str) -> Dict:
        """取消订单"""
        try:
            result = self.exchange.cancel_order(order_id, self.symbol)
            logger.info(f"订单取消成功: {order_id}")
            return result
            
        except Exception as e:
            logger.error(f"订单取消失败: {e}")
            raise
    
    def get_order_status(self, order_id: str) -> Dict:
        """查询订单状态"""
        try:
            order = self.exchange.fetch_order(order_id, self.symbol)
            logger.debug(f"订单状态查询: {order_id} - {order['status']}")
            return order
            
        except Exception as e:
            logger.error(f"查询订单状态失败: {e}")
            raise
    
    def get_open_orders(self) -> List[Dict]:
        """获取未成交订单"""
        try:
            orders = self.exchange.fetch_open_orders(self.symbol)
            logger.debug(f"未成交订单数量: {len(orders)}")
            return orders
            
        except Exception as e:
            logger.error(f"获取未成交订单失败: {e}")
            raise
    
    def get_trade_history(self, limit: int = 50) -> List[Dict]:
        """获取交易历史"""
        try:
            trades = self.exchange.fetch_my_trades(self.symbol, limit=limit)
            logger.debug(f"交易历史记录数量: {len(trades)}")
            return trades
            
        except Exception as e:
            logger.error(f"获取交易历史失败: {e}")
            raise
    
    def get_position(self) -> Dict:
        """获取持仓信息(合约交易)"""
        try:
            if self.trading_config['trade_type'] != 'futures':
                return {'size': 0, 'side': 'none', 'unrealizedPnl': 0}
            
            positions = self.exchange.fetch_positions([self.symbol])
            position = positions[0] if positions else {}
            
            result = {
                'size': position.get('size', 0),
                'side': position.get('side', 'none'),
                'unrealizedPnl': position.get('unrealizedPnl', 0),
                'percentage': position.get('percentage', 0),
                'entryPrice': position.get('entryPrice', 0)
            }
            
            logger.debug(f"持仓信息: {result}")
            return result
            
        except Exception as e:
            logger.error(f"获取持仓信息失败: {e}")
            raise
    
    def close_position(self, side: str = 'auto') -> Dict:
        """平仓(合约交易)"""
        try:
            if self.trading_config['trade_type'] != 'futures':
                raise ValueError("平仓操作仅适用于合约交易")
            
            position = self.get_position()
            if position['size'] == 0:
                logger.warning("当前无持仓，无需平仓")
                return {}
            
            # 确定平仓方向
            if side == 'auto':
                close_side = 'sell' if position['side'] == 'long' else 'buy'
            else:
                close_side = side
            
            # 平仓
            order = self.place_market_order(close_side, abs(position['size']))
            logger.info(f"平仓成功: {close_side} {abs(position['size'])} {self.symbol}")
            return order
            
        except Exception as e:
            logger.error(f"平仓失败: {e}")
            raise
    
    def get_exchange_info(self) -> Dict:
        """获取交易所信息"""
        try:
            markets = self.exchange.load_markets()
            symbol_info = markets.get(self.symbol, {})
            
            result = {
                'symbol': self.symbol,
                'base': symbol_info.get('base', ''),
                'quote': symbol_info.get('quote', ''),
                'active': symbol_info.get('active', False),
                'precision': symbol_info.get('precision', {}),
                'limits': symbol_info.get('limits', {}),
                'fees': symbol_info.get('fees', {})
            }
            
            logger.debug(f"交易所信息: {result}")
            return result
            
        except Exception as e:
            logger.error(f"获取交易所信息失败: {e}")
            raise
    
    def is_market_open(self) -> bool:
        """检查市场是否开放"""
        try:
            # 加密货币市场24小时开放
            return True
            
        except Exception as e:
            logger.error(f"检查市场状态失败: {e}")
            return False