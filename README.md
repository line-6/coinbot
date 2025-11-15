# coinbot

# 轻量级数字货币交易机器人

基于ccxt的量化交易机器人，实现了基础的趋势跟踪策略，支持现货和合约交易，可定制化二次开发。

## 安装配置

### 1. 环境要求

- Python 3.10+
- 币安API账户

### 2. 安装项目所需依赖

```bash
pip install -r requirements.txt
```

### 3. 配置设置

编辑 `config.yaml` 文件，配置您的币安API密钥：

```yaml
binance:
  apiKey: "your_api_key_here"
  secretKey: "your_secret_key_here"
  sandbox: true  # 测试环境，正式交易请设为false
```

**注**: 
- 若启用测试环境，请将相应的apiKey和secretKey设置为 [testnet的API密钥](https://developers.binance.com/docs/binance-spot-api-docs/faqs/testnet)。
- 若启用正式交易，请将相应的apiKey和secretKey设置为正式账号的[API密钥](https://www.binance.com/en/binance-api)。
- 建议先在测试环境中运行

## 4. 基础策略说明

### 趋势识别指标

1. **EMA (指数移动平均线)**
   - 快线: 12周期
   - 慢线: 26周期
   - 用于判断价格趋势方向

2. **MACD (移动平均收敛发散)**
   - 参数: (12, 26, 9)
   - 识别趋势转换点

3. **ADX (平均趋向指数)**
   - 周期: 14
   - 衡量趋势强度

4. **布林带 (Bollinger Bands)**
   - 周期: 20
   - 标准差: 2
   - 识别超买超卖

5. **RSI (相对强弱指数)**
   - 周期: 14
   - 辅助确认信号

### 交易信号逻辑

#### 买入/做多信号
- EMA金叉 + MACD金叉
- ADX > 25 (趋势强劲)
- RSI < 70 (非超买)
- 价格突破布林带中轨

#### 卖出/做空信号
- EMA死叉 + MACD死叉
- ADX > 25 (趋势强劲)
- RSI > 30 (非超卖)
- 价格跌破布林带中轨

#### 平仓信号
- 趋势反转确认
- 止损止盈触发
- ADX < 20 (趋势减弱)

### 风险管理

- **止损**: 2% (可配置)
- **止盈**: 4% (可配置)
- **最大持仓**: 账户资金的10%
- **每日交易限制**: 10笔
- **最大回撤控制**: 10%

## 🚀 使用方法

### 1. 启动交易机器人

```bash
python main.py
```

### 2. 实时监控

```bash
# 实时监控模式
python tools/monitor.py --mode monitor

# 生成监控报告
python tools/monitor.py --mode report

# 导出数据
python tools/monitor.py --mode export --days 7
```

### 3. 性能分析

```bash
# 完整性能分析
python tools/analyzer.py --days 30

# 仅生成报告
python tools/analyzer.py --report-only --days 30

# 不生成图表
python tools/analyzer.py --no-charts --days 30
```

### 4. 策略回测

```bash
python tools/backtest.py
```

## 回测结果示例

```
╔══════════════════════════════════════════════════════════════╗
║                    回测结果报告                              ║
╠══════════════════════════════════════════════════════════════╣
║ 回测期间: 2024-01-01 至 2024-01-31                          ║
║ 总交易次数: 45                                               ║
║ 胜率: 62.22%                                                 ║
║ 总收益率: 15.67%                                             ║
║ 最大回撤: 3.45%                                              ║
║ 夏普比率: 1.85                                               ║
║ 盈亏比: 1.45                                                 ║
╚══════════════════════════════════════════════════════════════╝
```

### 自定义策略

1. 继承 `TrendFollowingStrategy` 类
2. 重写 `generate_signals()` 方法
3. 实现自定义的信号逻辑
4. 更新配置文件

## 许可证

MIT License

## 贡献

欢迎提交Issue和Pull Request来改进项目。

---

**免责声明**: 本项目仅供学习和研究使用，不构成投资建议。使用者需自行承担交易风险。