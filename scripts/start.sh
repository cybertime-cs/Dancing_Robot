cd /home/pi/Desktop/dancing_robot
source /home/pi/myenv/bin/activate

sudo bluetoothctl power on
sleep 5
sudo bluetoothctl connect 41:42:E1:8D:A7:63
sudo bluetoothctl trust 41:42:E1:8D:A7:63
sudo bluetoothctl exit

python /home/pi/Desktop/dancing_robot/main.py

# 进入 bluetoothctl 交互模式
# bluetoothctl

# 在 bluetoothctl 中执行以下命令
# devices                # 显示所有已知设备
# paired-devices         # 显示已配对的设备
# connected-devices      # 显示已连接的设备

# 查看特定设备的详细信息（包括MAC地址）
# info [MAC地址]

# 退出 bluetoothctl
# exit