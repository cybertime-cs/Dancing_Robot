# datapackage.py
"""把动作文件名转成下位机认识的串口数据帧（本项目唯一的协议出口）。

一帧的字节结构（见 string_to_hex_array）：

    下标    0      1      2      3      4       5          6          7..7+n-1      末字节
         ┌──────┬──────┬──────┬──────┬──────┬──────────┬──────────┬─────────────┬────────┐
         │ 0xff │ 0x00 │ 0x05 │ 0x05 │ 0x00 │ 文件名长度 │ 类型字节  │ 文件名字节   │ 校验和  │
         └──────┴──────┴──────┴──────┴──────┴──────────┴──────────┴─────────────┴────────┘

    类型字节：.bin → 0x09（普通单动作）；.odr → 0x0e（动作序列，下位机执行更久）
    校验和  ：帧内除校验和以外的所有字节求和，对 255 取余

例：

    DataPackageConverter("turn_left.bin").hex_output
    # [0xff, 0x00, 0x05, 0x05, 0x00, 13, 0x09] + "turn_left.bin" 的各字符 ASCII + [校验和]

注意：这里传的是**文件名**而不是动作名。下位机拿着这个名字去自己的存储里找动作文件，
所以 actions.json 中配置的文件名必须与下位机里的一致。
"""

# 固定帧头
FRAME_HEADER = [0xFF, 0x00, 0x05, 0x05, 0x00]
# 按文件后缀决定的“类型字节”
TYPE_BYTE_BIN = 0x09   # .bin —— 普通单动作
TYPE_BYTE_ODR = 0x0E   # .odr —— 动作序列（移动 / 舞蹈，执行时间更长）
# 校验和取模基数
CHECKSUM_MOD = 255
# 后缀不合法时的提示文案（保持不变：有测试依赖这个字符串）
INVALID_TYPE_MSG = "Invalid file type"


class DataPackageConverter:
    """把一个动作文件名（"xxx.bin" / "xxx.odr"）转成串口数据帧。

    属性：
        hex_output   最终字节列表（十进制整数），可直接交给 serial 发送
        warning_msg  构造失败的原因；正常时为空字符串
        x            类型字节（0x09 / 0x0e），名字沿用历史写法，含义见模块文档
    """

    def __init__(self, input_str):
        self.input_str = input_str
        self.x = 0x00
        self.warning_msg = ""
        self.hex_output = []
        self.set_input_str(self.input_str)

    def set_input_str(self, input_str):
        """按后缀设置类型字节并生成数据帧；后缀不合法时只置 warning_msg，不抛异常。"""
        if input_str.endswith(".bin"):
            self.x = TYPE_BYTE_BIN
        elif input_str.endswith(".odr"):
            self.x = TYPE_BYTE_ODR
        else:
            self.warning_msg = INVALID_TYPE_MSG
            return
        self.string_to_hex_array(input_str, self.x)

    def string_to_hex_array(self, input_str, x):  # 事实上是十进制，函数名没改
        """拼出完整数据帧：帧头 + 长度 + 类型字节 + 文件名字节 + 校验和。"""
        hex_arr = [ord(char) for char in input_str]
        sum_val = sum(hex_arr) + sum(FRAME_HEADER) + len(input_str) + x
        checksum = sum_val % CHECKSUM_MOD

        # 返回实际的列表，而不是字符串
        self.hex_output = FRAME_HEADER + [len(input_str), x] + hex_arr + [checksum]
        return self.hex_output

    def get_hex_output_formatted(self):
        """返回格式化的十六进制列表字符串，便于打印和查看"""
        hex_formatted = [f"0x{x:02x}" for x in self.hex_output]
        return hex_formatted

    def __str__(self):
        """返回十六进制格式的字符串表示，便于打印对象"""
        hex_formatted = self.get_hex_output_formatted()
        return f"[{', '.join(hex_formatted)}]"


if __name__ == "__main__":
    converter = DataPackageConverter("turn_left.bin")
    # 打印十进制格式
    print("十进制格式:", converter.hex_output)

    # 打印十六进制格式
    print("十六进制格式:", converter.get_hex_output_formatted())

    # 直接打印对象（会调用__str__方法）
    print("对象字符串表示:", converter)
