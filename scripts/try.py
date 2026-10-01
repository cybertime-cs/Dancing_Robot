import serial
from datapackage import DataPackageConverter

def initialize_serial():
    try:
        ser = serial.Serial('/dev/ttyAMA0', 115200)
        if not ser.isOpen():
            ser.open()
        return ser
    except serial.SerialException:
        raise Exception("Failed to initialize serial connection.")
    
ser = initialize_serial()
movements = DataPackageConverter("choice.odr").hex_output
ser.write(bytearray(movements))