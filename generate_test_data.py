#!/usr/bin/env python3
"""
生成日志解析器的测试数据。
使用与log_parser相同的帧格式配置。
"""
import random
import struct
import sys
from typing import List

# 导入log_parser中的帧格式配置
import log_parser
DEFAULT_FORMAT = log_parser.DEFAULT_FORMAT

def create_frame(payload: bytes, length_field_correct: bool = True) -> bytes:
    """
    使用给定的载荷创建帧。
    如果 length_field_correct 为 False，将长度字段设置为错误值。
    """
    fmt = DEFAULT_FORMAT
    payload_len = len(payload)

    if length_field_correct:
        length = payload_len
    else:
        # 设置错误长度：更短或更长
        if random.choice([True, False]):
            wrong_len = max(0, payload_len - random.randint(1, 5))
        else:
            wrong_len = payload_len + random.randint(1, 5)
        length = wrong_len

    # 根据帧格式配置生成长度字段字节
    if fmt.LENGTH_FIELD_SIZE == 1:
        length_bytes = struct.pack('B', length & 0xFF)
    elif fmt.LENGTH_FIELD_SIZE == 2:
        if fmt.LENGTH_FIELD_BIG_ENDIAN:
            length_bytes = struct.pack('>H', length)
        else:
            length_bytes = struct.pack('<H', length)
    elif fmt.LENGTH_FIELD_SIZE == 4:
        if fmt.LENGTH_FIELD_BIG_ENDIAN:
            length_bytes = struct.pack('>I', length)
        else:
            length_bytes = struct.pack('<I', length)
    else:
        # 处理其他大小的长度字段
        result = bytearray(fmt.LENGTH_FIELD_SIZE)
        if fmt.LENGTH_FIELD_BIG_ENDIAN:
            for i in range(fmt.LENGTH_FIELD_SIZE):
                shift = (fmt.LENGTH_FIELD_SIZE - 1 - i) * 8
                result[i] = (length >> shift) & 0xFF
        else:
            for i in range(fmt.LENGTH_FIELD_SIZE):
                shift = i * 8
                result[i] = (length >> shift) & 0xFF
        length_bytes = bytes(result)

    # 构建帧：起始标记 + 其他信息（如果有）+ 长度字段 + 载荷 + 结束标记
    # 注意：如果LENGTH_FIELD_OFFSET > len(FRAME_START)，需要在起始标记和长度字段之间填充其他信息
    frame_parts = []
    frame_parts.append(fmt.FRAME_START)

    # 如果长度字段有偏移，添加填充字节（这里用0x00填充，实际使用时可以修改）
    if fmt.LENGTH_FIELD_OFFSET > len(fmt.FRAME_START):
        padding_size = fmt.LENGTH_FIELD_OFFSET - len(fmt.FRAME_START)
        frame_parts.append(b'\x00' * padding_size)

    frame_parts.append(length_bytes)
    frame_parts.append(payload)
    frame_parts.append(fmt.FRAME_END)

    return b''.join(frame_parts)

def create_time_frame(timestamp: int = None) -> bytes:
    """创建时间帧。"""
    fmt = DEFAULT_FORMAT
    if timestamp is None:
        # 生成随机时间戳，适应时间戳大小
        max_ts = (1 << (fmt.time_timestamp_size * 8)) - 1
        timestamp = random.randint(0, max_ts)

    # 根据时间戳大小生成长度合适的字节
    if fmt.time_timestamp_size == 6:
        # 6字节时间戳：使用8字节打包然后取后6字节
        time_bytes = struct.pack('>Q', timestamp)[8 - fmt.time_timestamp_size:]
    elif fmt.time_timestamp_size == 4:
        time_bytes = struct.pack('>I', timestamp)
    elif fmt.time_timestamp_size == 8:
        time_bytes = struct.pack('>Q', timestamp)
    else:
        # 其他大小：手动构造大端字节
        result = bytearray(fmt.time_timestamp_size)
        for i in range(fmt.time_timestamp_size):
            shift = (fmt.time_timestamp_size - 1 - i) * 8
            result[i] = (timestamp >> shift) & 0xFF
        time_bytes = bytes(result)

    return fmt.TIME_MARKER + time_bytes

def generate_test_data() -> bytes:
    """生成包含各种场景的测试数据。"""
    data_parts = []

    # 1. 一些有效帧
    print("Generating valid frames...")
    for i in range(5):
        payload = f"Frame {i}: Test payload".encode('ascii')
        frame = create_frame(payload, length_field_correct=True)
        data_parts.append(frame)

    # 2. 长度字段错误的帧
    print("Generating frames with incorrect length field...")
    for i in range(3):
        payload = f"Bad length frame {i}".encode('ascii')
        frame = create_frame(payload, length_field_correct=False)
        data_parts.append(frame)

    # 3. 不完整帧（缺少结束标记）
    print("Generating incomplete frames...")
    fmt = DEFAULT_FORMAT
    for i in range(2):
        payload = f"Incomplete frame {i}".encode('ascii')
        # 使用正确的长度字段生成
        frame = create_frame(payload, length_field_correct=True)
        # 移除结束标记使其不完整
        incomplete = frame[:-len(fmt.FRAME_END)]
        data_parts.append(incomplete)

    # 4. 在随机位置插入时间帧
    print("Inserting time frames...")
    for i in range(4):
        time_frame = create_time_frame(i * 1000)
        data_parts.append(time_frame)

    # 5. 帧之间的随机垃圾字节
    print("Adding garbage bytes...")
    garbage = bytes([random.randint(0, 255) for _ in range(random.randint(1, 10))])
    data_parts.append(garbage)

    # 打乱部分以混合所有内容
    random.shuffle(data_parts)

    # 合并所有部分
    return b''.join(data_parts)

def generate_large_complex() -> bytes:
    """
    生成一个复杂的测试用例，包含：
    - 开头的垃圾数据
    - 10个以上的帧
    - 帧之间夹杂垃圾数据
    - 帧内穿插时间帧（时间帧作为载荷的一部分）
    - 帧间穿插时间帧
    - 错帧，长度字段为最大值（全1）
    """
    data_parts = []
    fmt = DEFAULT_FORMAT

    # 1. 开头的垃圾数据（约100字节）
    print("生成开头垃圾数据...")
    garbage_start = bytes([random.randint(0, 255) for _ in range(100)])
    data_parts.append(garbage_start)

    # 2. 生成至少10个常规帧，帧之间夹杂垃圾数据和独立的时间帧
    print("生成常规帧...")
    for i in range(15):  # 15个帧
        # 随机决定是否在载荷中包含时间帧
        if random.choice([True, False]):
            # 帧内穿插时间帧：在载荷中插入时间帧字节
            payload = f"Frame {i} with time marker inside".encode('ascii')
            # 随机插入时间帧的字节（完整的时间帧）
            time_frame = create_time_frame(i * 1000)
            # 将时间帧字节插入到载荷的随机位置
            pos = random.randint(0, len(payload))
            payload = payload[:pos] + time_frame + payload[pos:]
        else:
            payload = f"Frame {i} normal".encode('ascii')

        # 随机决定是否创建错帧（长度字段为最大值）
        if random.choice([True, False]) and i % 3 == 0:  # 大约1/3的帧为错帧
            # 错帧：长度字段设置为最大值（全1）
            max_length = (1 << (fmt.LENGTH_FIELD_SIZE * 8)) - 1
            # 生成长度字段字节
            if fmt.LENGTH_FIELD_SIZE == 1:
                length_bytes = struct.pack('B', max_length)
            elif fmt.LENGTH_FIELD_SIZE == 2:
                if fmt.LENGTH_FIELD_BIG_ENDIAN:
                    length_bytes = struct.pack('>H', max_length)
                else:
                    length_bytes = struct.pack('<H', max_length)
            elif fmt.LENGTH_FIELD_SIZE == 4:
                if fmt.LENGTH_FIELD_BIG_ENDIAN:
                    length_bytes = struct.pack('>I', max_length)
                else:
                    length_bytes = struct.pack('<I', max_length)
            else:
                # 手动构造
                length_bytes = bytes([0xFF] * fmt.LENGTH_FIELD_SIZE)

            # 构建错帧
            frame_parts = []
            frame_parts.append(fmt.FRAME_START)
            if fmt.LENGTH_FIELD_OFFSET > len(fmt.FRAME_START):
                padding_size = fmt.LENGTH_FIELD_OFFSET - len(fmt.FRAME_START)
                frame_parts.append(b'\x00' * padding_size)
            frame_parts.append(length_bytes)
            frame_parts.append(payload)
            frame_parts.append(fmt.FRAME_END)
            frame = b''.join(frame_parts)

            hex_length = length_bytes.hex()
            print(f"  创建错帧 {i}，长度字段={hex_length}")
        else:
            # 正常帧
            frame = create_frame(payload, length_field_correct=True)

        data_parts.append(frame)

        # 随机在帧后添加垃圾数据（1-20字节）
        if random.choice([True, False]):
            garbage = bytes([random.randint(0, 255) for _ in range(random.randint(1, 20))])
            data_parts.append(garbage)
            print(f"  添加{len(garbage)}字节垃圾数据")

        # 随机在帧后添加独立的时间帧
        if random.choice([True, False]):
            time_frame = create_time_frame(i * 500)
            data_parts.append(time_frame)
            print(f"  添加独立时间帧")

    # 3. 在末尾再添加一些垃圾数据
    print("生成末尾垃圾数据...")
    garbage_end = bytes([random.randint(0, 255) for _ in range(50)])
    data_parts.append(garbage_end)

    # 不打乱顺序，保持结构
    return b''.join(data_parts)

def write_test_files():
    """将测试数据写入文件。"""
    fmt = DEFAULT_FORMAT
    # 生成各种测试用例
    test_cases = {
        'simple_valid': b''.join([
            create_frame(b"Hello"),
            create_frame(b"World"),
        ]),
        'with_time_frames': b''.join([
            create_frame(b"Frame1"),
            create_time_frame(1000),
            create_frame(b"Frame2"),
            create_time_frame(2000),
        ]),
        'mixed_bad_frames': generate_test_data(),
        'incomplete_at_end': b''.join([
            create_frame(b"Complete"),
            create_frame(b"start", length_field_correct=True)[:-len(fmt.FRAME_END)],
        ]),
        'hex_input_example': b'7e000548656c6c6f7e',  # 包含'Hello'的帧的十六进制表示
        # 额外测试用例
        'large_frame': create_frame(b"X" * 1000),
        'zero_length_frame': create_frame(b""),
        'time_frame_series': b''.join([create_time_frame(i * 1000) for i in range(5)]),
        'garbage_only': bytes([random.randint(0, 255) for _ in range(50)]),
        'empty_input': b'',
        'unicode_payload': create_frame("测试".encode('utf-8')),
        'multiple_time_frames_contiguous': b''.join([create_time_frame(0x123456 + i) for i in range(3)]),
        'time_frame_inside_frame': create_frame(b"Hello" + fmt.TIME_MARKER + b"World", length_field_correct=True),
        'large_complex': generate_large_complex(),
    }

    for name, data in test_cases.items():
        filename = f"tests/test_{name}.bin"
        with open(filename, 'wb') as f:
            f.write(data)
        print(f"Written {len(data)} bytes to {filename}")

        # 同时创建十六进制表示文件用于十六进制输入测试
        hex_filename = f"tests/test_{name}.hex"
        with open(hex_filename, 'w') as f:
            f.write(data.hex())
        print(f"Written hex to {hex_filename}")

if __name__ == '__main__':
    write_test_files()