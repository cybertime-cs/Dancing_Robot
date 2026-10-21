# The code is used to convert string or odr files to hex array for data package.
class DataPackageConverter():
    def __init__(self, input_str):
        self.input_str = input_str
        self.x = 0x00
        self.warning_msg = ""
        self.hex_output = []
        self.set_input_str(self.input_str)

    def set_input_str(self, input_str):
        if input_str.endswith(".bin"):
            self.x = 0x09
        elif input_str.endswith(".odr"):
            self.x = 0x0e
        else:
            self.warning_msg = "Invalid file type"
            return
        self.string_to_hex_array(input_str, self.x)

    def string_to_hex_array(self, input_str, x): # 事实上是十进制，函数名没改
        hex_arr = [ord(char) for char in input_str]
        sum_val = sum(hex_arr) + 0xff + 0x00 + 0x05 + 0x05 + 0x00 + len(input_str) + x
        checksum = sum_val % 255

        # 返回实际的列表，而不是字符串
        self.hex_output = [0xff, 0x00, 0x05, 0x05, 0x00, len(input_str), x] + hex_arr + [checksum]
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
