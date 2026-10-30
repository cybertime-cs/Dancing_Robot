# 银河号表演机器人

## 从 GitHub 克隆与补全模型

```bash
git clone --single-branch --branch yinhe_pro https://github.com/cybertime-cs/Dancing_Robot.git yinhe_pro
cd yinhe_pro
bash install_offline_runtime.sh
```

仓库保留程序、配置、剧情文档和音频，不包含 `.onnx` 模型权重、虚拟环境、缓存或运行日志。首次在树莓派联网执行上述安装脚本，自动下载中文/英文流式 Zipformer ASR 与 Silero VAD，分别恢复到 `models/asr/` 和 `models/silero_vad.onnx`；之后识别可离线运行。模型下载地址和文件名见 `install_offline_runtime.sh`，运行时文件名见 `speech_train.json` 的 `asr` 配置。本目录已包含 `datapackage.py`。请勿将下载后的模型再次提交到 Git。

## yinhe_pro 实时识别版

本目录从 `Desktop/yinhe` 完整复制，原目录代码保持不变。`yinhe.service` 已切换为从本目录开机自启动，服务名仍是 `yinhe.service`。如需手动运行调试，先停止后台服务，避免两个程序同时控制机器人：

```bash
systemctl --user stop yinhe.service
cd /home/pi/Desktop/yinhe_pro
.venv/bin/python yinhe_robot.py
```

手动调试结束后，先按 Ctrl+C 停止程序，再运行 `systemctl --user start yinhe.service` 恢复新版后台运行。查看状态用 `systemctl --user status yinhe.service`，停止用 `systemctl --user stop yinhe.service`，重启用 `systemctl --user restart yinhe.service`。监听日志位于 `/home/pi/Desktop/yinhe_pro/logs/listener.log`，执行日志位于 `/home/pi/Desktop/yinhe_pro/logs/execution.log`。旧服务配置已备份到 `/home/pi/.config/systemd/user/yinhe.service.before-yinhe-pro-20261016`；该备份仍指向原目录，需回退时可恢复该文件并执行 `systemctl --user daemon-reload`、`systemctl --user restart yinhe.service`。

新版以约 32 ms 的小块持续读取 ALSA 音频，Silero VAD 一旦检测到说话，就将当前语音段新增的样本送入 Sherpa 流式解码，不再等一句话结束才开始识别。每次解码得到的新文本都立即检查当前允许的口令，命中就释放麦克风并进入原流程。等待期间不按 7 秒反复重启录音；未命中的话在句尾自动清空，继续同一次录音，避免把不同句子的词拼起来触发。

主唤醒门控、包含式匹配与冲突处理、播放顺序、音量增益、动作包及等待回包、最后流程重新锁定均保持原样。执行流程期间不录音，防止机器人自己的音频触发口令；流程结束重新监听，不执行录音积压的旧口令。`speech_train.py` 使用同一增量解码链路，但仍等完整句子再供人工确认，避免把中途识别文本存进训练词表。

`logs/listener.log` 会显示 `ASR 实时结果` 和 `实时口令命中`，播放和串口执行仍看 `logs/execution.log`。所谓立即触发是“流式识别结果出现匹配口令时”，仍受模型本身的分块、算力和识别准确率影响，不保证说出最后一个字时零延迟。当前 JSON 中很短的易错词（例如“隐形”“一定”）也会立即匹配，沿用原配置；如误触发，可在本副本的 `speech_train.json` 中删除相应短词。

离线回归测试（不打开麦克风、不播放、不发送动作）：`.venv/bin/python -m unittest discover -s tests -v`。

`yinhe_robot.py` 实现以下闭环：静默监听 → Silero VAD → sherpa-onnx 流式 ASR → 指令匹配 → FSM → 音频/串口动作包，流程结束自动回到静默监听。

每次程序启动后持续监听，但先只接受主唤醒词“星途已定，即刻启航”。主唤醒前，“银河银河”“启动反物质引擎”等所有剧情口令都会被忽略。识别到主唤醒词后播放 `resources/audio/就位.mp3`，播完再进入已解锁的静默监听，从下一句开始响应原有口令。主唤醒音频配置在 `speech_train.json` 的 `master_wake.steps`。中间流程结束保持解锁；最后一段“汇报任务完成情况”（`mission_report`）的全部步骤结束后，重新锁定并只响应主唤醒词。再次主唤醒仍会播放“就位.mp3”，随后可以开始下一轮表演。程序重启也会重新等待主唤醒。

最后流程在 `speech_train.json` 中通过 `"return_to_master_wake": true` 标记，不依赖配置中的排列顺序；只有该流程执行完毕后才重新锁定。

主唤醒词配置在 `speech_train.json` 的 `master_wake.phrases`，匹配时忽略空格、中英文逗号、句号和感叹号，要求包含完整词组。可在 `speech_train.py` 中选择最后一项“主唤醒（解锁表演）”，确认识别结果后添加对应的 ASR 易错写法。训练程序可以直接录制各口令，无需事先解锁。

“就位.mp3”在 `master_wake.steps` 中单独设置了 `"gain_db": 6`（播放时增加 6 dB）。设为 `0` 恢复原音量，设为 `3` 可减小增强幅度；该文件原始峰值约为 -7.6 dB，建议不要超过 6 dB，以免削波失真。其他音频未配置增益，仍使用原来的播放音量；原音频文件不变。修改配置后需重启程序。

## 现场只需改的位置

所有口令、ASR 易错写法、音频和动作文件名都在 `speech_train.json`。音频放入 `resources/audio/` 后修改相应 `file`、`music` 字段。动作文件存放在主控板，树莓派仅把 `action` 字段中的文件名（例如 `dongzuo1.odr`）封装后发给主控，不需要、也不会在树莓派查找该文件。动作文件名统一使用 `.odr`。

灯光、风扇、旁白等需要接入现场控制器的步骤以 `note` 保留在每一流程中，避免在无明确串口协议时误发控制包；拿到协议后在 `PerformanceFSM._run_step()` 增加对应步骤即可。

## 安装与运行

1. 首次联网安装可运行 `bash install_offline_runtime.sh`。它创建 `.venv`、安装依赖，并将中文流式 ASR 与 Silero VAD 模型放到程序读取的位置；安装完成后识别无需联网。
2. 将现有机器人 SDK 中的 `datapackage.py` 放到本目录（它提供 `DataPackageConverter`）。串口、音频与动作发送直接采用原版 `action_neo.py`：`mplayer -volume 100` 播放；动作包经 `DataPackageConverter(文件).hex_output` 转换，`send_serial_data()` 发送后等待原版的 `...18`/`...19` 回包或 10 秒超时。
3. 演练主唤醒和剧情而不接硬件：`.venv/bin/python yinhe_robot.py --dry-run --text "星途已定，即刻启航" --text "银河银河"`。可先加一项 `--text "银河银河"` 验证主唤醒前不会响应。
4. 现场运行：`.venv/bin/python yinhe_robot.py`。

开机自启动使用 `deployment/yinhe.service`。安装到用户级 systemd 后，服务名为 `yinhe.service`；可用 `systemctl --user status yinhe.service` 查看状态，用 `journalctl --user -u yinhe.service -f` 查看系统日志。

## 两个终端查看状态

主终端运行 `.venv/bin/python yinhe_robot.py`，只显示流程执行、音频播放、动作包发送与主控回包。另开一个终端执行 `tail -f logs/listener.log`，单独查看静默监听、麦克风和 ASR 识别结果。执行日志同时保存在 `logs/execution.log`；ALSA/PortAudio 的底层诊断写入 `logs/listener-alsa.log`。

独立训练同一 ASR/解析链路：`.venv/bin/python speech_train.py`。程序会先列出 11 条剧情指令及主唤醒词，选中后才开始录音；每次识别结果都要确认才会追加到该项的 `phrases`。麦克风通过 ALSA `arecord` 的 `pulse` 接口从 PipeWire 采集，允许与桌面音频服务共享 USB 麦克风，同时绕过 PortAudio 的错误设备枚举；Sherpa 与 Silero VAD 仍保持不变。文本联调可用：`.venv/bin/python speech_train.py --text "检测机体状态"`。

## Hiwonder 模块输入

照片中的 WonderEcho 类模块不是 ALSA 录音声卡。它在板载 CI1302 芯片中完成唤醒和离线命令词识别，树莓派通过 I2C 读取命令 ID。因此 Type-C 亮灯只证明模块已供电，不能证明树莓派能够取得麦克风 PCM 数据。

模块默认作为 I2C 从机使用：地址 `0x34`（新版也可能配置为 `0x33`），识别结果寄存器为 `0x64`，读取 1 字节；`0` 表示没有新结果，非零值是当前固件中命令词的 ID。请将模块的 SDA、SCL、GND（以及选择使用的 5V 供电）接到树莓派 I2C 引脚，并在树莓派设置中启用 I2C。

先运行 `.venv/bin/python hiwonder_module.py`，说出模块固件里的各条命令并记录终端显示的 ID。然后在 `hiwonder_module.json` 的 `command_ids` 中填写 ID 到现有流程名的映射，例如 `"17": "self_check"`。映射完成后运行 `.venv/bin/python hiwonder_module.py --run-flows`。模块监听日志保存在 `logs/module.log`，动作和音频仍显示在主终端并写入 `logs/execution.log`。

注意：模块只能识别烧录在其固件中的命令词，`speech_train.py` 只用于 Sherpa 音频识别，不能训练模块。若要让模块直接识别银河号剧本口令，需要在 Hiwonder 的固件制作工具中配置这些命令词和 ID 后重新烧录。
