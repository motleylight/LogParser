#!/usr/bin/env python3
"""
日志解析器 - 解析带时间标记的二进制日志帧的工具。

帧格式可配置：帧起始标记、长度字段位置和大小、帧结束标记等。
"""
import argparse
import sys
import os
import select
import io
import json
import time
from typing import Optional, BinaryIO, Iterator, Tuple

# 尝试导入串口库，如果未安装则提供友好提示
try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False

class FrameFormat:
    """
    可配置的帧格式定义。
    要修改帧格式，请修改此类的属性。
    """

    # === 常规帧配置 ===
    FRAME_START = b'\x7e'                    # 帧起始标记
    FRAME_END = b'\x7e'                      # 帧结束标记

    # 长度字段配置
    LENGTH_FIELD_OFFSET = 1                  # 长度字段相对于帧起始的偏移（字节）
    LENGTH_FIELD_SIZE = 2                    # 长度字段的大小（字节）
    LENGTH_FIELD_BIG_ENDIAN = True           # True=大端序，False=小端序

    # === 时间帧配置 ===
    TIME_MARKER = b'\xaa\xaa'                # 时间帧起始标记
    TIME_FRAME_LENGTH = 8                    # 时间帧总长度（字节）
    # 时间帧结构：TIME_MARKER (2字节) + 时间戳 (6字节)

    # === 计算得到的属性 ===
    @property
    def min_frame_size(self) -> int:
        """最小帧大小：起始 + 长度字段 + 最小载荷(0) + 结束"""
        return (len(self.FRAME_START) +
                self.LENGTH_FIELD_SIZE +
                len(self.FRAME_END))

    @property
    def length_field_end(self) -> int:
        """长度字段结束位置（相对于帧起始）"""
        return self.LENGTH_FIELD_OFFSET + self.LENGTH_FIELD_SIZE

    @property
    def time_timestamp_size(self) -> int:
        """时间帧中时间戳部分的大小"""
        return self.TIME_FRAME_LENGTH - len(self.TIME_MARKER)

    def parse_length(self, length_bytes: bytes) -> int:
        """解析长度字段字节"""
        if self.LENGTH_FIELD_SIZE == 2:
            if self.LENGTH_FIELD_BIG_ENDIAN:
                return (length_bytes[0] << 8) | length_bytes[1]
            else:
                return (length_bytes[1] << 8) | length_bytes[0]
        elif self.LENGTH_FIELD_SIZE == 4:
            if self.LENGTH_FIELD_BIG_ENDIAN:
                return (length_bytes[0] << 24) | (length_bytes[1] << 16) | \
                       (length_bytes[2] << 8) | length_bytes[3]
            else:
                return (length_bytes[3] << 24) | (length_bytes[2] << 16) | \
                       (length_bytes[1] << 8) | length_bytes[0]
        else:
            # 处理1字节或3字节等不常见情况
            result = 0
            if self.LENGTH_FIELD_BIG_ENDIAN:
                for i, byte in enumerate(length_bytes):
                    result = (result << 8) | byte
            else:
                for i, byte in enumerate(reversed(length_bytes)):
                    result = (result << 8) | byte
            return result

    def extract_length_field(self, data: bytearray) -> Tuple[int, bytes]:
        """
        从数据中提取长度字段。
        返回：(长度值, 长度字段字节)
        """
        if len(data) < self.length_field_end:
            raise ValueError("数据不足，无法提取长度字段")

        start_idx = self.LENGTH_FIELD_OFFSET
        end_idx = self.length_field_end
        length_bytes = bytes(data[start_idx:end_idx])
        length = self.parse_length(length_bytes)
        return length, length_bytes

# 默认帧格式实例
DEFAULT_FORMAT = FrameFormat()

class LogParser:
    def __init__(self, frame_format: FrameFormat = None):
        self.frame_format = frame_format or DEFAULT_FORMAT
        self.buffer = bytearray()
        self.stats = {
            'frames_found': 0,
            'time_frames_found': 0,
            'invalid_frames': 0,
            'bytes_processed': 0,
        }

    def process_data(self, data: bytes):
        """处理传入的二进制数据。"""
        self.buffer.extend(data)
        self.stats['bytes_processed'] += len(data)

    def find_next_frame(self) -> Optional[bytes]:
        """从缓冲区查找并提取下一帧，移除已处理的字节。
        返回帧字节，如果没有找到完整帧则返回None。
        """
        fmt = self.frame_format

        # 查找时间标记或帧起始的最早出现位置
        time_frame_idx = self.buffer.find(fmt.TIME_MARKER)
        frame_start_idx = self.buffer.find(fmt.FRAME_START)

        # 确定哪个标记最先出现（将-1视为未找到）
        candidates = []
        if time_frame_idx != -1:
            candidates.append(('time', time_frame_idx))
        if frame_start_idx != -1:
            candidates.append(('frame', frame_start_idx))

        if not candidates:
            # 未找到标记，清空缓冲区
            self.buffer.clear()
            return None

        # 按位置排序
        candidates.sort(key=lambda x: x[1])
        marker_type, marker_idx = candidates[0]

        # 移除第一个标记之前的任何数据
        if marker_idx > 0:
            del self.buffer[:marker_idx]

        if marker_type == 'time':
            # 检查是否有足够的数据构成完整的时间帧
            if len(self.buffer) >= fmt.TIME_FRAME_LENGTH:
                time_frame = bytes(self.buffer[:fmt.TIME_FRAME_LENGTH])
                del self.buffer[:fmt.TIME_FRAME_LENGTH]
                self.stats['time_frames_found'] += 1
                return time_frame
            # 数据不足，无法构成时间帧
            return None
        else:
            # marker_type == 'frame'
            # 检查是否有最小帧所需的数据
            if len(self.buffer) < fmt.min_frame_size:
                return None

            try:
                # 提取长度字段
                length, _ = fmt.extract_length_field(self.buffer)
            except (ValueError, IndexError):
                # 数据不足以提取长度字段，或者长度字段解析错误
                # 尝试查找帧结束标记以恢复
                end_idx = self.buffer.find(fmt.FRAME_END, len(fmt.FRAME_START))
                if end_idx == -1:
                    # 未找到结束标记，等待更多数据
                    return None
                # 提取到结束标记的帧
                frame_end_idx = end_idx + len(fmt.FRAME_END)
                frame_bytes = bytes(self.buffer[:frame_end_idx])
                del self.buffer[:frame_end_idx]
                self.stats['invalid_frames'] += 1
                return frame_bytes

            # 计算预期帧大小
            # length_field_end 已经包含从帧开始到长度字段结束的所有字节
            # 所以只需要：长度字段结束位置 + 载荷长度 + 帧结束标记长度
            expected_frame_size = (
                fmt.length_field_end +
                length +
                len(fmt.FRAME_END)
            )

            if len(self.buffer) < expected_frame_size:
                # 根据长度字段，数据不足以构成完整帧
                # 这可能是由于错误的长度字段或不完整的帧
                # 尝试查找帧结束标记以恢复
                end_idx = self.buffer.find(fmt.FRAME_END, fmt.length_field_end)
                if end_idx == -1:
                    # 未找到结束标记，等待更多数据
                    return None
                # 提取到结束标记的帧
                frame_end_idx = end_idx + len(fmt.FRAME_END)
                frame_bytes = bytes(self.buffer[:frame_end_idx])
                del self.buffer[:frame_end_idx]
                self.stats['invalid_frames'] += 1
                return frame_bytes

            # 检查帧是否在预期位置以正确的结束标记结束
            frame_end_start = expected_frame_size - len(fmt.FRAME_END)
            actual_end = bytes(self.buffer[frame_end_start:expected_frame_size])
            if actual_end != fmt.FRAME_END:
                # 在预期位置未找到正确的帧结束标记
                # 这可能是由于长度字段错误
                # 尝试查找下一个帧结束标记
                end_idx = self.buffer.find(fmt.FRAME_END, fmt.length_field_end)
                if end_idx == -1:
                    # 未找到结束标记，等待更多数据
                    return None
                # 提取到结束标记的帧
                frame_end_idx = end_idx + len(fmt.FRAME_END)
                frame_bytes = bytes(self.buffer[:frame_end_idx])
                del self.buffer[:frame_end_idx]
                self.stats['invalid_frames'] += 1
                return frame_bytes

            # 找到完整帧
            frame_bytes = bytes(self.buffer[:expected_frame_size])
            del self.buffer[:expected_frame_size]
            self.stats['frames_found'] += 1
            return frame_bytes

    def process_stream(self, input_stream: BinaryIO) -> Iterator[bytes]:
        """处理输入流并生成找到的帧。"""
        while True:
            data = input_stream.read(4096)
            if not data:
                break
            self.process_data(data)
            while True:
                frame = self.find_next_frame()
                if frame is None:
                    break
                yield frame

        # 处理缓冲区中剩余的数据
        while True:
            frame = self.find_next_frame()
            if frame is None:
                break
            yield frame

def hex_to_bytes(hex_str: str) -> bytes:
    """将十六进制字符串转换为字节，处理空格和可选的0x前缀。"""
    hex_str = hex_str.strip()
    if hex_str.startswith('0x'):
        hex_str = hex_str[2:]
    # 移除所有空格或冒号
    hex_str = ''.join(hex_str.split())
    hex_str = hex_str.replace(':', '')
    try:
        return bytes.fromhex(hex_str)
    except ValueError as e:
        raise ValueError(f"Invalid hex string: {e}")

def main():
    parser = argparse.ArgumentParser(
        description='解析带时间标记的二进制日志帧。',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s -f logfile.bin
  cat logfile.bin | %(prog)s
  %(prog)s -x "7e000548656c6c6f7e"
  echo "7e000548656c6c6f7e" | %(prog)s -x
  %(prog)s -p /dev/ttyUSB0 --baud 115200
  %(prog)s -p COM3 --baud 9600 --parity E
  %(prog)s --list-ports
        """
    )

    input_group = parser.add_mutually_exclusive_group()
    input_group.add_argument('-f', '--file', help='输入二进制文件')
    input_group.add_argument('-x', '--hex', nargs='?', const='',
                           help='十六进制字符串输入')
    input_group.add_argument('-s', '--stdin', action='store_true',
                           help='显式从标准输入读取二进制数据')
    input_group.add_argument('-p', '--port',
                           help='串口设备路径（如 /dev/ttyUSB0 或 COM3）')

    # 串口参数（仅在指定 --port 时使用）
    parser.add_argument('--baud', type=int, default=115200,
                       help='串口波特率（默认：115200）')
    parser.add_argument('--bytesize', type=int, choices=[5, 6, 7, 8], default=8,
                       help='数据位（默认：8）')
    parser.add_argument('--parity', choices=['N', 'E', 'O', 'M', 'S'], default='N',
                       help='奇偶校验：N(无)、E(偶)、O(奇)、M(标记)、S(空格)（默认：N）')
    parser.add_argument('--stopbits', type=float, choices=[1, 1.5, 2], default=1.0,
                       help='停止位（默认：1）')
    parser.add_argument('--rtscts', action='store_true',
                       help='启用 RTS/CTS 硬件流控制')
    parser.add_argument('--timeout', type=float,
                       help='读取超时（秒），默认：None（阻塞读取）')
    parser.add_argument('--list-ports', action='store_true',
                       help='列出可用串口并退出')

    parser.add_argument('-v', '--verbose', action='store_true',
                       help='详细输出')
    parser.add_argument('-o', '--output', choices=['text', 'hex', 'raw', 'json'], default='text',
                       help='输出格式（默认：text）')
    parser.add_argument('--parse-time', action='store_true',
                       help='将时间帧时间戳解析为十进制整数')

    args = parser.parse_args()

    # 处理 --list-ports 选项
    if args.list_ports:
        if not SERIAL_AVAILABLE:
            print("错误：pyserial 库未安装，无法列出串口。", file=sys.stderr)
            print("请使用 pip install pyserial 安装。", file=sys.stderr)
            sys.exit(1)
        print("可用串口：")
        ports = serial.tools.list_ports.comports()
        if not ports:
            print("  未找到串口。")
        for port in ports:
            print(f"  {port.device}: {port.description} [{port.manufacturer}]")
        sys.exit(0)

    # 如果没有任何输入源且标准输入是终端，显示帮助并提示输入文件
    if (not args.file and args.hex is None and not args.stdin and args.port is None
            and sys.stdin.isatty()):
        parser.print_help()
        print("\n" + "="*60, file=sys.stderr)
        print("提示：未指定输入源", file=sys.stderr)
        file_path = input("请输入bin文件路径: ").strip()
        if not file_path:
            print("错误：未提供文件路径", file=sys.stderr)
            sys.exit(1)
        args.file = file_path

    # Determine input source
    input_data = None
    input_stream = None

    if args.port:
        # 串口输入
        if not SERIAL_AVAILABLE:
            print("错误：pyserial 库未安装，无法使用串口功能。", file=sys.stderr)
            print("请使用 pip install pyserial 安装。", file=sys.stderr)
            sys.exit(1)

        # 映射数据位到 serial 库常量
        bytesize_map = {
            5: serial.FIVEBITS,
            6: serial.SIXBITS,
            7: serial.SEVENBITS,
            8: serial.EIGHTBITS
        }

        # 映射奇偶校验字符到 serial 库常量
        parity_map = {
            'N': serial.PARITY_NONE,
            'E': serial.PARITY_EVEN,
            'O': serial.PARITY_ODD,
            'M': serial.PARITY_MARK,
            'S': serial.PARITY_SPACE
        }

        # 映射停止位
        stopbits_map = {
            1: serial.STOPBITS_ONE,
            1.5: serial.STOPBITS_ONE_POINT_FIVE,
            2: serial.STOPBITS_TWO
        }

        try:
            serial_port = serial.Serial(
                port=args.port,
                baudrate=args.baud,
                bytesize=bytesize_map[args.bytesize],
                parity=parity_map[args.parity],
                stopbits=stopbits_map[args.stopbits],
                rtscts=args.rtscts,
                timeout=args.timeout
            )
            input_stream = serial_port
            if args.verbose:
                print(f"已打开串口 {args.port}，波特率 {args.baud}", file=sys.stderr)
        except serial.SerialException as e:
            print(f"错误：无法打开串口 {args.port}: {e}", file=sys.stderr)
            sys.exit(1)
        except KeyError as e:
            print(f"错误：无效的串口参数: {e}", file=sys.stderr)
            sys.exit(1)
    elif args.file:
        try:
            input_stream = open(args.file, 'rb')
        except FileNotFoundError:
            print(f"Error: File not found: {args.file}", file=sys.stderr)
            sys.exit(1)
    elif args.hex is not None:
        # Hex input
        if args.hex == '':
            # Read hex from stdin
            hex_str = sys.stdin.read().strip()
        else:
            hex_str = args.hex
        try:
            input_data = hex_to_bytes(hex_str)
            input_stream = io.BytesIO(input_data)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # Default: read binary from stdin
        if sys.stdin.isatty():
            print("正在从标准输入读取（二进制）...", file=sys.stderr)
        input_stream = sys.stdin.buffer

    # Create parser
    parser_inst = LogParser()

    # Process input
    try:
        for frame in parser_inst.process_stream(input_stream):
            if args.output == 'raw':
                sys.stdout.buffer.write(frame)
            elif args.output == 'hex':
                print(frame.hex())
            elif args.output == 'json':
                # JSON output
                frame_info = {
                    'type': 'time_frame' if frame.startswith(DEFAULT_FORMAT.TIME_MARKER) else 'frame',
                    'hex': frame.hex(),
                    'length': len(frame)
                }
                if frame.startswith(DEFAULT_FORMAT.TIME_MARKER) and args.parse_time:
                    # Parse timestamp (big-endian)
                    timestamp_start = len(DEFAULT_FORMAT.TIME_MARKER)
                    timestamp_end = timestamp_start + DEFAULT_FORMAT.time_timestamp_size
                    timestamp = int.from_bytes(frame[timestamp_start:timestamp_end], 'big')
                    frame_info['timestamp'] = timestamp
                print(json.dumps(frame_info))
            else:  # text output (default)
                if frame.startswith(DEFAULT_FORMAT.TIME_MARKER):
                    if args.parse_time:
                        timestamp_start = len(DEFAULT_FORMAT.TIME_MARKER)
                        timestamp_end = timestamp_start + DEFAULT_FORMAT.time_timestamp_size
                        timestamp = int.from_bytes(frame[timestamp_start:timestamp_end], 'big')
                        print(f"TIME_FRAME: {frame.hex()} (timestamp: {timestamp})")
                    else:
                        print(f"TIME_FRAME: {frame.hex()}")
                else:
                    print(f"FRAME: {frame.hex()}")
    except KeyboardInterrupt:
        pass
    finally:
        if (args.file or args.port) and input_stream:
            input_stream.close()

    # Print statistics if verbose
    if args.verbose:
        print("\nStatistics:", file=sys.stderr)
        for key, value in parser_inst.stats.items():
            print(f"  {key}: {value}", file=sys.stderr)

if __name__ == '__main__':
    main()