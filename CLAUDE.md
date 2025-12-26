# CLAUDE.md

本文档为 Claude Code (claude.ai/code) 在此代码库中工作时提供指导。

## 项目概述

这是一个 Python 3 命令行工具，用于解析带时间标记的二进制日志帧。解析器处理特定的二进制格式，其中帧以 `0x7E` 开始和结束，并包含一个2字节的长度字段（大端序）。时间帧为8字节，以 `0xAA 0xAA` 开始。

## 架构

### 核心组件

1. **`log_parser.py`** - 主解析器实现
   - `LogParser` 类：核心解析逻辑与缓冲区管理
   - 帧格式：`0x7E` + [2字节长度] + [载荷] + `0x7E`
   - 时间帧：`0xAA 0xAA` + [6字节时间戳]
   - 功能：长度字段验证、错误恢复、统计跟踪
   - 输入模式：文件、十六进制字符串、标准输入
   - 输出格式：文本、十六进制、原始二进制

2. **`generate_test_data.py`** - 测试数据生成器
   - 创建各种测试场景（有效帧、错误长度字段、不完整帧、时间帧）
   - 在 `tests/` 目录中生成匹配的 `.bin` 和 `.hex` 文件

### 目录结构
```
.
├── log_parser.py              # 主解析器
├── generate_test_data.py      # 测试数据生成器
└── tests/                     # 测试数据目录
    ├── *.bin                  # 二进制测试文件
    └── *.hex                  # 十六进制表示文件
```

## 常用命令

### 运行解析器
```bash
# 解析二进制文件
python3 log_parser.py -f tests/test_simple_valid.bin

# 解析十六进制输入
python3 log_parser.py -x "7e000548656c6c6f7e"

# 从标准输入读取（二进制）
cat tests/test_simple_valid.bin | python3 log_parser.py

# 从标准输入读取十六进制
echo "7e000548656c6c6f7e" | python3 log_parser.py -x

# 禁用长度验证
python3 log_parser.py -f tests/test_mixed_bad_frames.bin --no-validate

# 详细输出带统计信息
python3 log_parser.py -f tests/test_simple_valid.bin -v

# 以十六进制格式输出
python3 log_parser.py -f tests/test_simple_valid.bin -o hex

# 输出原始二进制
python3 log_parser.py -f tests/test_simple_valid.bin -o raw > output.bin
```

### 生成测试数据
```bash
# 重新生成所有测试文件
python3 generate_test_data.py
```

### 检查二进制文件
```bash
# 查看二进制文件的十六进制转储（需要 xxd 权限）
xxd tests/test_simple_valid.bin

# 比较二进制和十六进制文件
xxd -r -p tests/test_simple_valid.hex | xxd
```

## 开发说明

### 权限
Claude 有权运行：
- `Bash(mkdir:*)` - 创建目录
- `Bash(python3:*)` - 执行 Python 脚本
- `Bash(xxd:*)` - 使用 xxd 进行十六进制转储操作

### 测试策略
- 测试文件通过 `generate_test_data.py` 程序化生成
- 每个测试用例都有 `.bin`（二进制）和 `.hex`（十六进制字符串）两个版本
- 测试场景包括：简单有效帧、带时间标记的帧、混合错误帧、不完整帧
- 未使用正式测试框架；通过手动执行进行测试

### 关键设计模式
1. **流处理**：解析器使用基于缓冲区的方法处理不完整数据
2. **错误恢复**：无效帧被检测并优雅处理
3. **统计跟踪**：统计帧数、时间帧数、无效帧数和处理的字节数
4. **灵活的I/O**：支持文件、十六进制字符串和标准输入，多种输出格式

### 帧格式详情
- **常规帧**：开始 `0x7E`，2字节长度（大端序），载荷，结束 `0x7E`
- **时间帧**：`0xAA 0xAA` 后跟6字节时间戳
- **长度验证**：可通过 `--no-validate` 标志禁用，用于损坏的日志
- **十六进制输入**：接受带可选 `0x` 前缀、空格或冒号的十六进制字符串

### 代码风格
- 使用 Python 类型提示（`typing` 模块）
- 全面的文档字符串
- 清晰的关注点分离（解析逻辑 vs. CLI 接口）
- 除 Python 标准库外无外部依赖