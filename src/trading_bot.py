#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
趋势跟踪量化交易机器人主程序
整合策略、交易所、风险管理等模块
"""

import yaml
import time
import signal
import sys
from typing import Dict, Optional
from datetime import datetime, timedelta, timezone
from loguru import logger
import schedule
import threading
from pathlib import Path

# 导入自定义模块
from strategy import TrendFollowingStrategy, SignalType
from exchange import ExchangeInterface
from risk_manager import RiskManager, RiskLevel
from data_manager import DataManager

class TradingBot:
    """量化交易机器人主类"""
    
    def __init__(self, config_path: str = '../config.yaml'):
        # 加载配置
        self.config = self._load_config(config_path)
        
        # 初始化各模块
        self.exchange = ExchangeInterface(self.config)
        self.strategy = TrendFollowingStrategy(self.config)
        self.risk_manager = RiskManager(self.config)
        self.data_manager = DataManager(self.config)
        
        # 机器人状态
        self.is_running = False
        self.is_trading_enabled = True
        self.last_signal_time = None
        self.current_position = 0
        self.entry_price = 0
        
        # 性能统计
        self.total_trades = 0
        self.successful_trades = 0
        self.total_pnl = 0
        
        # 设置日志
        self._setup_logging()
        
        logger.info("交易机器人初始化完成")
    
    def _load_config(self, config_path: str) -> Dict:
        """加载配置文件"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            datetime.now().astimezone().isoformat()
            logger.info(f"配置文件加载成功: {config_path}")
            return config
        except Exception as e:
            logger.error(f"配置文件加载失败: {e}")
            raise
    
    def _setup_logging(self):
        """设置日志配置"""
        try:
            datetime.now(timezone.utc).isoformat()
            log_config = self.config.get('logging', {})
            log_level = log_config.get('level', 'INFO')
            log_file = log_config.get('file', 'logs/trading_bot.log')
            
            # 确保日志目录存在
            Path(log_file).parent.mkdir(exist_ok=True)
            
            # 配置loguru
            logger.remove()  # 移除默认处理器
            
            # 添加控制台输出
            logger.add(
                sys.stdout,
                level=log_level,
                format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
            )
            
            # 添加文件输出
            logger.add(
                log_file,
                level=log_level,
                format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
                rotation=log_config.get('max_size', '10 MB'),
                retention=log_config.get('backup_count', 5),
                compression="zip"
            )
            
            logger.info("日志系统配置完成")
            
        except Exception as e:
            print(f"日志配置失败: {e}")
    
    def start(self):
        """启动交易机器人"""
        try:
            logger.info("=" * 50)
            logger.info("趋势跟踪量化交易机器人启动")
            logger.info(f"交易对: {self.config['trading']['symbol']}")
            logger.info(f"交易模式: {self.config['trading']['trade_type']}")
            logger.info(f"时间周期: {self.config['trading']['timeframe']}")
            logger.info("=" * 50)
            
            self.is_running = True
            
            # 设置信号处理
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)
            
            # 启动定时任务
            self._setup_scheduler()
            
            # 主循环
            self._main_loop()
            
        except Exception as e:
            logger.error(f"启动交易机器人失败: {e}")
            self.stop()
    
    def _setup_scheduler(self):
        """设置定时任务"""
        try:
            # 根据时间周期设置交易检查频率
            timeframe = self.config['trading']['timeframe']
            
            if timeframe == '1m':
                schedule.every(1).minutes.do(self._trading_cycle)
            elif timeframe == '5m':
                schedule.every(5).minutes.do(self._trading_cycle)
            elif timeframe == '15m':
                schedule.every(15).minutes.do(self._trading_cycle)
            elif timeframe == '1h':
                schedule.every().hour.do(self._trading_cycle)
            elif timeframe == '4h':
                schedule.every(4).hours.do(self._trading_cycle)
            elif timeframe == '1d':
                schedule.every().day.at("09:00").do(self._trading_cycle)
            else:
                # 默认每小时检查一次
                schedule.every().hour.do(self._trading_cycle)
            
            # 每日性能报告
            schedule.every().day.at("23:59").do(self._daily_report)
            
            # 每周数据清理
            schedule.every().sunday.at("02:00").do(self._weekly_cleanup)
            
            logger.info(f"定时任务设置完成: {timeframe}")
            
        except Exception as e:
            logger.error(f"设置定时任务失败: {e}")
    
    def _main_loop(self):
        """主循环"""
        try:
            while self.is_running:
                # 执行定时任务
                schedule.run_pending()
                
                # 检查系统状态
                self._health_check()
                
                # 短暂休眠
                time.sleep(1)
                
        except KeyboardInterrupt:
            logger.info("接收到停止信号")
        except Exception as e:
            logger.error(f"主循环异常: {e}")
        finally:
            self.stop()
    
    def _trading_cycle(self):
        """交易周期执行"""
        try:
            if not self.is_trading_enabled:
                logger.debug("交易已禁用，跳过本次周期")
                return
            
            logger.info("开始交易周期检查")
            
            # 1. 获取市场数据
            klines_df = self.exchange.get_klines(limit=200)
            if klines_df.empty:
                logger.warning("无法获取K线数据，跳过本次周期")
                return
            
            # 2. 保存K线数据
            self.data_manager.save_klines(
                klines_df, 
                self.config['trading']['symbol'], 
                self.config['trading']['timeframe']
            )
            
            # 3. 计算技术指标
            klines_df = self.strategy.calculate_indicators(klines_df)
            
            # 4. 生成交易信号
            signal = self.strategy.generate_signal(klines_df)
            current_price = float(klines_df['close'].iloc[-1])
            
            # 5. 保存信号
            signal_data = {
                'timestamp': datetime.now().isoformat(),
                'symbol': self.config['trading']['symbol'],
                'signal_type': signal.value,
                'price': current_price,
                'confidence': 0.8,  # 可以根据指标强度计算
                'indicators': {
                    'ema_fast': float(klines_df['ema_fast'].iloc[-1]),
                    'ema_slow': float(klines_df['ema_slow'].iloc[-1]),
                    'macd': float(klines_df['macd'].iloc[-1]),
                    'rsi': float(klines_df['rsi'].iloc[-1]),
                    'adx': float(klines_df['adx'].iloc[-1])
                }
            }
            self.data_manager.save_signal(signal_data)
            
            # 6. 风险检查
            if not self._risk_check(current_price):
                logger.warning("风险检查未通过，跳过交易")
                return
            
            # 7. 执行交易
            logger.info(f"当前交易信号：{signal}")
            if signal != SignalType.HOLD:
                self._execute_trade(signal, current_price)
            
            # 8. 检查止损止盈
            self._check_stop_conditions(current_price)
            
            logger.info(f"交易周期完成: 信号={signal.value}, 价格={current_price:.4f}")
            
        except Exception as e:
            logger.error(f"交易周期执行失败: {e}")
    
    def _risk_check(self, current_price: float) -> bool:
        """风险检查"""
        try:
            # 检查每日交易限制
            if not self.risk_manager.check_daily_limits():
                return False
            
            # 评估风险等级
            risk_level = self.risk_manager.assess_risk_level(
                self.total_pnl, self.current_position
            )
            
            # 检查是否应该停止交易
            if self.risk_manager.should_stop_trading(risk_level):
                self.is_trading_enabled = False
                logger.critical("风险过高，自动禁用交易")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"风险检查失败: {e}")
            return False
    
    def _execute_trade(self, signal: SignalType, current_price: float):
        """执行交易"""
        try:
            trade_amount = self.config['trading']['trade_amount']
            symbol = self.config['trading']['symbol']
            
            # 获取账户余额
            balance = self.exchange.get_balance()
            
            # 根据信号类型执行不同操作
            order = None
            
            if signal == SignalType.BUY and self.current_position <= 0:
                # 现货买入
                order = self.exchange.place_market_order('buy', trade_amount)
                if order:
                    self.current_position += trade_amount
                    self.entry_price = current_price
                    self.strategy.update_position(signal, trade_amount, current_price)
            
            elif signal == SignalType.SELL and self.current_position > 0:
                # 现货卖出
                sell_amount = min(trade_amount, self.current_position)
                order = self.exchange.place_market_order('sell', sell_amount)
                if order:
                    self.current_position -= sell_amount
                    if self.current_position <= 0:
                        self.entry_price = 0
                    self.strategy.update_position(signal, sell_amount, current_price)
            
            elif signal == SignalType.LONG and self.current_position <= 0:
                # 合约做多
                order = self.exchange.place_market_order('buy', trade_amount)
                if order:
                    self.current_position = trade_amount
                    self.entry_price = current_price
                    self.strategy.update_position(signal, trade_amount, current_price)
            
            elif signal == SignalType.SHORT and self.current_position >= 0:
                # 合约做空
                order = self.exchange.place_market_order('sell', trade_amount)
                if order:
                    self.current_position = -trade_amount
                    self.entry_price = current_price
                    self.strategy.update_position(signal, trade_amount, current_price)
            
            elif signal in [SignalType.CLOSE_LONG, SignalType.CLOSE_SHORT]:
                # 平仓
                if self.current_position != 0:
                    close_side = 'sell' if self.current_position > 0 else 'buy'
                    order = self.exchange.place_market_order(close_side, abs(self.current_position))
                    if order:
                        # 计算盈亏
                        pnl = self._calculate_pnl(current_price)
                        self.total_pnl += pnl
                        
                        self.current_position = 0
                        self.entry_price = 0
                        self.strategy.update_position(signal, 0, current_price)
            
            # 记录交易
            if order:
                self._record_trade(order, signal, current_price)
                
                # 设置止损止盈订单
                if signal in [SignalType.BUY, SignalType.LONG, SignalType.SELL, SignalType.SHORT]:
                    self._set_stop_orders(current_price, signal)
            
        except Exception as e:
            logger.error(f"执行交易失败: {e}")
    
    def _calculate_pnl(self, current_price: float) -> float:
        """计算盈亏"""
        try:
            if self.current_position == 0 or self.entry_price == 0:
                return 0
            
            if self.current_position > 0:  # 多头
                pnl = (current_price - self.entry_price) * self.current_position
            else:  # 空头
                pnl = (self.entry_price - current_price) * abs(self.current_position)
            
            return pnl
            
        except Exception as e:
            logger.error(f"计算盈亏失败: {e}")
            return 0
    
    def _set_stop_orders(self, entry_price: float, signal: SignalType):
        """设置止损止盈订单"""
        try:
            stop_loss, take_profit = self.strategy.calculate_stop_loss_take_profit(entry_price, signal)
            
            if stop_loss > 0 and take_profit > 0:
                # 这里可以设置实际的止损止盈订单
                # 由于不同交易所API差异，这里仅记录价格
                logger.info(f"止损止盈设置: 止损={stop_loss:.4f}, 止盈={take_profit:.4f}")
            
        except Exception as e:
            logger.error(f"设置止损止盈失败: {e}")
    
    def _check_stop_conditions(self, current_price: float):
        """检查止损止盈条件"""
        try:
            if self.current_position == 0 or self.entry_price == 0:
                return
            
            side = 'buy' if self.current_position > 0 else 'sell'
            
            # 检查止损
            if self.risk_manager.check_stop_loss_trigger(
                current_price, self.entry_price, side, self.current_position
            ):
                logger.warning("触发止损，执行平仓")
                self._execute_stop_loss(current_price)
            
            # 检查止盈
            elif self.risk_manager.check_take_profit_trigger(
                current_price, self.entry_price, side, self.current_position
            ):
                logger.info("触发止盈，执行平仓")
                self._execute_take_profit(current_price)
            
        except Exception as e:
            logger.error(f"检查止损止盈失败: {e}")
    
    def _execute_stop_loss(self, current_price: float):
        """执行止损"""
        try:
            if self.current_position == 0:
                return
            
            close_side = 'sell' if self.current_position > 0 else 'buy'
            order = self.exchange.place_market_order(close_side, abs(self.current_position))
            
            if order:
                pnl = self._calculate_pnl(current_price)
                self.total_pnl += pnl
                
                # 记录交易
                self._record_trade(order, SignalType.SELL, current_price, 'stop_loss')
                
                self.current_position = 0
                self.entry_price = 0
                
                logger.warning(f"止损执行完成: 盈亏={pnl:.4f}")
            
        except Exception as e:
            logger.error(f"执行止损失败: {e}")
    
    def _execute_take_profit(self, current_price: float):
        """执行止盈"""
        try:
            if self.current_position == 0:
                return
            
            close_side = 'sell' if self.current_position > 0 else 'buy'
            order = self.exchange.place_market_order(close_side, abs(self.current_position))
            
            if order:
                pnl = self._calculate_pnl(current_price)
                self.total_pnl += pnl
                
                # 记录交易
                self._record_trade(order, SignalType.SELL, current_price, 'take_profit')
                
                self.current_position = 0
                self.entry_price = 0
                
                logger.info(f"止盈执行完成: 盈亏={pnl:.4f}")
            
        except Exception as e:
            logger.error(f"执行止盈失败: {e}")
    
    def _record_trade(self, order: Dict, signal: SignalType, price: float, trade_type: str = 'normal'):
        """记录交易"""
        try:
            trade_data = {
                'timestamp': datetime.now().isoformat(),
                'symbol': order.get('symbol', ''),
                'side': order.get('side', ''),
                'amount': order.get('amount', 0),
                'price': price,
                'value': order.get('amount', 0) * price,
                'fee': order.get('fee', {}).get('cost', 0),
                'pnl': self._calculate_pnl(price) if trade_type in ['stop_loss', 'take_profit'] else 0,
                'signal_type': signal.value,
                'order_id': order.get('id', ''),
                'status': order.get('status', 'completed')
            }
            
            # 保存到数据管理器
            self.data_manager.save_trade(trade_data)
            
            # 更新统计
            self.total_trades += 1
            if trade_data['pnl'] > 0:
                self.successful_trades += 1
            
            # 记录到风险管理器
            self.risk_manager.record_trade(trade_data)
            
            logger.info(f"交易记录: {trade_data['side']} {trade_data['amount']} @ {price:.4f}")
            
        except Exception as e:
            logger.error(f"记录交易失败: {e}")
    
    def _health_check(self):
        """系统健康检查"""
        try:
            # 检查交易所连接
            if not self.exchange.is_connected:
                logger.warning("交易所连接异常")
                # 尝试重连
                self.exchange = ExchangeInterface(self.config)
            
            # 检查市场是否开放
            if not self.exchange.is_market_open():
                logger.info("市场未开放")
                self.is_trading_enabled = False
            else:
                self.is_trading_enabled = True
            
        except Exception as e:
            logger.error(f"健康检查失败: {e}")
    
    def _daily_report(self):
        """生成每日报告"""
        try:
            logger.info("生成每日交易报告")
            
            # 获取今日交易数据
            today = datetime.now().date().isoformat()
            summary = self.data_manager.get_daily_summary(today)
            
            if summary.get('no_trades'):
                logger.info("今日无交易记录")
                return
            
            # 生成报告
            report = f"""
            ==================== 每日交易报告 ====================
            日期: {today}
            总交易次数: {summary.get('total_trades', 0)}
            盈利交易: {summary.get('winning_trades', 0)}
            亏损交易: {summary.get('losing_trades', 0)}
            胜率: {summary.get('win_rate', 0):.2f}%
            总盈亏: {summary.get('total_pnl', 0):.4f}
            最大盈利: {summary.get('max_profit', 0):.4f}
            最大亏损: {summary.get('max_loss', 0):.4f}
            最大回撤: {summary.get('max_drawdown', 0):.2f}%
            夏普比率: {summary.get('sharpe_ratio', 0):.2f}
            ===================================================
            """
            
            logger.info(report)
            
            # 保存性能指标
            self.data_manager.save_performance_metrics(summary, today)
            
        except Exception as e:
            logger.error(f"生成每日报告失败: {e}")
    
    def _weekly_cleanup(self):
        """每周数据清理"""
        try:
            logger.info("执行每周数据清理")
            self.data_manager.cleanup_old_data(days_to_keep=30)
            
        except Exception as e:
            logger.error(f"数据清理失败: {e}")
    
    def _signal_handler(self, signum, frame):
        """信号处理器"""
        logger.info(f"接收到信号 {signum}，准备停止机器人")
        self.stop()
    
    def stop(self):
        """停止交易机器人"""
        try:
            logger.info("正在停止交易机器人...")
            
            self.is_running = False
            self.is_trading_enabled = False
            
            # 如果有持仓，询问是否平仓
            if self.current_position != 0:
                logger.warning(f"当前持仓: {self.current_position}")
                # 在实际应用中，可以选择自动平仓或手动处理
            
            # 生成最终报告
            self._generate_final_report()
            
            logger.info("交易机器人已停止")
            
        except Exception as e:
            logger.error(f"停止机器人失败: {e}")
    
    def _generate_final_report(self):
        """生成最终报告"""
        try:
            # 获取所有交易记录
            trades_df = self.data_manager.load_trades()
            
            if trades_df.empty:
                logger.info("无交易记录")
                return
            
            # 计算总体性能
            metrics = self.data_manager.calculate_performance_metrics(trades_df)
            
            report = f"""
            ==================== 最终交易报告 ====================
            运行时间: {datetime.now().isoformat()}
            总交易次数: {metrics.get('total_trades', 0)}
            盈利交易: {metrics.get('winning_trades', 0)}
            亏损交易: {metrics.get('losing_trades', 0)}
            胜率: {metrics.get('win_rate', 0):.2f}%
            总盈亏: {metrics.get('total_pnl', 0):.4f}
            平均盈亏: {metrics.get('avg_pnl', 0):.4f}
            盈亏比: {metrics.get('profit_loss_ratio', 0):.2f}
            最大回撤: {metrics.get('max_drawdown', 0):.2f}%
            夏普比率: {metrics.get('sharpe_ratio', 0):.2f}
            当前持仓: {self.current_position}
            ===================================================
            """
            
            logger.info(report)
            
        except Exception as e:
            logger.error(f"生成最终报告失败: {e}")
    
    def get_status(self) -> Dict:
        """获取机器人状态"""
        return {
            'is_running': self.is_running,
            'is_trading_enabled': self.is_trading_enabled,
            'current_position': self.current_position,
            'entry_price': self.entry_price,
            'total_trades': self.total_trades,
            'successful_trades': self.successful_trades,
            'total_pnl': self.total_pnl,
            'strategy_status': self.strategy.get_strategy_status(),
            'risk_report': self.risk_manager.get_risk_report()
        }

def main():
    """主函数"""
    try:
        # 创建交易机器人
        bot = TradingBot()
        
        # 启动机器人
        bot.start()
        
    except Exception as e:
        logger.error(f"程序异常退出: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()