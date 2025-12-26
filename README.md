# LogParser - 日志解析工具

一个 Python 3 命令行工具，用于解析带时间标记的二进制日志帧。

## 项目概述

本工具专门用于解析特定的二进制日志格式，其中帧以 `0x7E` 开始和结束，并包含一个2字节的长度字段（大端序）。时间帧为8字节，以 `0xAA 0xAA` 开始。

### 帧格式

- **常规帧**：`0x7E` + [2字节长度] + [载荷] + `0x7E`
- **时间帧**：`0xAA 0xAA` + [6字节时间戳]

## 功能特性

- ✅ **帧边界检测**：自动识别帧起始和结束标记
- ✅ **错误恢复**：优雅处理无效帧，继续解析后续数据
- ✅ **统计跟踪**：实时统计帧数、时间帧数、无效帧数和处理的字节数
- ✅ **灵活的I/O**：支持文件、十六进制字符串和标准输入
- ✅ **多种输出格式**：文本、十六进制、原始二进制、JSON
- ✅ **时间戳解析**：支持将时间帧时间戳解析为十进制整数
- ✅ **流式处理**：基于缓冲区的方法处理不完整数据

## 安装要求

- Python 3.6+
- 无外部依赖（仅使用Python标准库）

## 快速开始

### 1. 克隆仓库
```bash
git clone https://github.com/motleylight/LogParser.git
cd LogParser
```

### 2. 基本使用
```bash
# 解析二进制文件
python3 log_parser.py -f tests/test_simple_valid.bin

# 解析十六进制输入
python3 log_parser.py -x "7e000548656c6c6f7e"

# 从标准输入读取（二进制）
cat tests/test_simple_valid.bin | python3 log_parser.py

# 从标准输入读取十六进制
echo "7e000548656c6c6f7e" | python3 log_parser.py -x

# 详细输出带统计信息
python3 log_parser.py -f tests/test_simple_valid.bin -v

# 以十六进制格式输出
python3 log_parser.py -f tests/test_simple_valid.bin -o hex

# 输出原始二进制
python3 log_parser.py -f tests/test_simple_valid.bin -o raw > output.bin

# JSON格式输出
python3 log_parser.py -f tests/test_simple_valid.bin -o json

# 解析时间帧时间戳
python3 log_parser.py -f tests/test_with_time_frames.bin --parse-time
```

## 命令行参数

```
用法: log_parser.py [-h] [-f FILE | -x [HEX] | -s] [-v]
                   [-o {text,hex,raw,json}] [--parse-time]

可选参数:
  -h, --help            显示帮助信息并退出
  -f FILE, --file FILE  输入二进制文件
  -x [HEX], --hex [HEX] 十六进制字符串输入
  -s, --stdin           显式从标准输入读取二进制数据
  -v, --verbose         详细输出（显示统计信息）
  -o {text,hex,raw,json}, --output {text,hex,raw,json}
                        输出格式（默认：text）
  --parse-time          将时间帧时间戳解析为十进制整数
```

### 默认行为
无参数运行时显示帮助信息并提示输入bin文件路径。

## 项目结构

```
.
├── log_parser.py              # 主解析器
├── generate_test_data.py      # 测试数据生成器
├── README.md                  # 项目文档（本文件）
├── CLAUDE.md                  # Claude Code开发指导文档
└── tests/                     # 测试数据目录
    ├── *.bin                  # 二进制测试文件
    └── *.hex                  # 十六进制表示文件
```

## 核心组件

### 1. `log_parser.py` - 主解析器实现
- `LogParser` 类：核心解析逻辑与缓冲区管理
- `FrameFormat` 类：可配置的帧格式定义
- 支持多种输入模式和输出格式
- 内置错误恢复和统计跟踪机制

### 2. `generate_test_data.py` - 测试数据生成器
- 创建各种测试场景（有效帧、错误长度字段、不完整帧、时间帧）
- 在 `tests/` 目录中生成匹配的 `.bin` 和 `.hex` 文件

### 使用测试数据生成器
```bash
# 重新生成所有测试文件
python3 generate_test_data.py
```

## 输出示例

### 文本输出（默认）
```
FRAME: 7e000548656c6c6f7e
FRAME: 7e0005576f726c647e
TIME_FRAME: aaaa0123456789abcd
```

### JSON输出
```json
{"type": "frame", "hex": "7e000548656c6c6f7e", "length": 5}
{"type": "time_frame", "hex": "aaaa0123456789abcd", "timestamp": 81985529216486895}
```

### 详细输出（带统计）
```
FRAME: 7e000548656c6c6f7e
FRAME: 7e0005576f726c647e

Statistics:
  frames_found: 2
  time_frames_found: 0
  invalid_frames: 0
  bytes_processed: 18
```

## 十六进制输入格式

十六进制字符串支持多种格式：
- 带 `0x` 前缀：`0x7e000548656c6c6f7e`
- 不带前缀：`7e000548656c6c6f7e`
- 带空格分隔：`7e 00 05 48 65 6c 6c 6f 7e`
- 带冒号分隔：`7e:00:05:48:65:6c:6c:6f:7e`

## 开发说明

### 代码风格
- 使用 Python 类型提示（`typing` 模块）
- 全面的文档字符串
- 清晰的关注点分离（解析逻辑 vs. CLI 接口）
- 除 Python 标准库外无外部依赖

### 测试策略
- 测试文件通过 `generate_test_data.py` 程序化生成
- 每个测试用例都有 `.bin`（二进制）和 `.hex`（十六进制字符串）两个版本
- 测试场景包括：简单有效帧、带时间标记的帧、混合错误帧、不完整帧
- 未使用正式测试框架；通过手动执行进行测试

## 设计模式

1. **流处理**：解析器使用基于缓冲区的方法处理不完整数据
2. **错误恢复**：无效帧被检测并优雅处理
3. **统计跟踪**：统计帧数、时间帧数、无效帧数和处理的字节数
4. **灵活的I/O**：支持文件、十六进制字符串和标准输入，多种输出格式

## 检查二进制文件

```bash
# 查看二进制文件的十六进制转储（需要 xxd 权限）
xxd tests/test_simple_valid.bin

# 比较二进制和十六进制文件
xxd -r -p tests/test_simple_valid.hex | xxd
```

## 许可证

本项目采用开源许可证（具体许可证信息待添加）

## 贡献

欢迎提交 Issue 和 Pull Request！

1. Fork 本仓库
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 作者

- GitHub: [@motleylight](https://github.com/motleylight)

## 更新日志

- **2025-12-26**: 初始版本发布，包含完整的日志解析功能和测试数据生成器