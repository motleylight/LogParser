#!/usr/bin/env python3
"""
日志解析器 - 解析带时间标记的二进制日志帧的工具。

帧以0x7E开始和结束，开始后有一个2字节长度字段（大端序）。
时间帧为8字节，以0xAA 0xAA开头。
"""
import argparse
import sys
import os
import select
import io
import json
from typing import Optional, BinaryIO, Iterator

FRAME_START = b'\x7e'
FRAME_END = b'\x7e'
TIME_MARKER = b'\xaa\xaa'
TIME_FRAME_LENGTH = 8

class LogParser:
    def __init__(self, validate_length: bool = True):
        self.validate_length = validate_length
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
        # 查找时间标记或帧起始的最早出现位置
        time_frame_idx = self.buffer.find(TIME_MARKER)
        frame_start_idx = self.buffer.find(FRAME_START)

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
            if len(self.buffer) >= TIME_FRAME_LENGTH:
                time_frame = bytes(self.buffer[:TIME_FRAME_LENGTH])
                del self.buffer[:TIME_FRAME_LENGTH]
                self.stats['time_frames_found'] += 1
                return time_frame
            # 数据不足，无法构成时间帧
            return None
        else:
            # marker_type == 'frame'
            # 至少需要4字节：起始(1) + 长度(2) + 结束(1) 最小值
            if len(self.buffer) < 4:
                return None

            # 检查长度字段（起始后的2字节）
            length = (self.buffer[1] << 8) | self.buffer[2]

            # 计算预期帧大小：起始(1) + 长度(2) + 载荷(长度) + 结束(1)
            expected_frame_size = 1 + 2 + length + 1

            if len(self.buffer) < expected_frame_size:
                # 根据长度字段，数据不足以构成完整帧
                # 这可能是由于错误的长度字段或不完整的帧
                # 尝试查找FRAME_END以恢复
                end_idx = self.buffer.find(FRAME_END, 3)  # 在长度字段后开始搜索
                if end_idx == -1:
                    # 未找到结束标记，等待更多数据
                    return None
                # 提取到结束标记的帧
                frame_bytes = bytes(self.buffer[:end_idx + 1])
                del self.buffer[:end_idx + 1]
                self.stats['invalid_frames'] += 1
                return frame_bytes

            # 检查帧是否在预期位置以FRAME_END结束
            if self.buffer[expected_frame_size - 1] != 0x7e:
                # 在预期位置未找到帧结束标记
                # 这可能是由于长度字段错误
                # 尝试查找下一个FRAME_END
                end_idx = self.buffer.find(FRAME_END, 3)  # 在长度字段后开始搜索
                if end_idx == -1:
                    # 未找到结束标记，等待更多数据
                    return None

                # 提取到结束标记的帧
                frame_bytes = bytes(self.buffer[:end_idx + 1])
                del self.buffer[:end_idx + 1]
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
        """
    )

    input_group = parser.add_mutually_exclusive_group()
    input_group.add_argument('-f', '--file', help='输入二进制文件')
    input_group.add_argument('-x', '--hex', nargs='?', const='',
                           help='Input as hex string (read from stdin if no value provided)')
    input_group.add_argument('-s', '--stdin', action='store_true',
                           help='Explicitly read binary from stdin (default if no other input)')

    parser.add_argument('--no-validate', action='store_true',
                       help='Disable length field validation')
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Verbose output')
    parser.add_argument('-o', '--output', choices=['text', 'hex', 'raw', 'json'], default='text',
                       help='Output format (default: text)')
    parser.add_argument('--parse-time', action='store_true',
                       help='Parse time frame timestamps as decimal integers')

    args = parser.parse_args()

    # Determine input source
    input_data = None
    input_stream = None

    if args.file:
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
            print("Reading from stdin (binary)...", file=sys.stderr)
        input_stream = sys.stdin.buffer

    # Create parser
    parser_inst = LogParser(validate_length=not args.no_validate)

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
                    'type': 'time_frame' if frame.startswith(TIME_MARKER) else 'frame',
                    'hex': frame.hex(),
                    'length': len(frame)
                }
                if frame.startswith(TIME_MARKER) and args.parse_time:
                    # Parse 6-byte timestamp (big-endian)
                    timestamp = int.from_bytes(frame[2:], 'big')
                    frame_info['timestamp'] = timestamp
                print(json.dumps(frame_info))
            else:  # text output (default)
                if frame.startswith(TIME_MARKER):
                    if args.parse_time:
                        timestamp = int.from_bytes(frame[2:], 'big')
                        print(f"TIME_FRAME: {frame.hex()} (timestamp: {timestamp})")
                    else:
                        print(f"TIME_FRAME: {frame.hex()}")
                else:
                    print(f"FRAME: {frame.hex()}")
    except KeyboardInterrupt:
        pass
    finally:
        if args.file and input_stream:
            input_stream.close()

    # Print statistics if verbose
    if args.verbose:
        print("\nStatistics:", file=sys.stderr)
        for key, value in parser_inst.stats.items():
            print(f"  {key}: {value}", file=sys.stderr)

if __name__ == '__main__':
    main()