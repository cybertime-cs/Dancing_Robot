import serial
import time

# 根据你的设备调整波特率，常见 9600/115200/921600
ser = serial.Serial(
    port='/dev/ttyAMA10',
    baudrate=115200,      # ← 改成你的实际波特率
    bytesize=serial.EIGHTBITS,
    parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
    timeout=1
)

# 你的数据包：必须是 bytes 类型，不是字符串！
data = bytes([0xFF, 0x00, 0x05, 0x05, 0x00, 0x11, 0x09,
              0x64, 0x73, 0x5F, 0x4C, 0x65, 0x66, 0x74,
              0x48, 0x61, 0x6E, 0x64, 0x55, 0x70, 0x2E,
              0x62, 0x69, 0x6E, 0x92])

print(f"发送 {len(data)} 字节: {data.hex()}")
ser.write(data)
ser.flush()
time.sleep(0.5)
if ser.in_waiting:
    resp = ser.read(ser.in_waiting)
    print(f"收到回应: {resp.hex()}")

ser.close()
