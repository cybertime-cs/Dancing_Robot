# 蜂后 FengHou

## 从 GitHub 克隆与补全模型

```bash
git clone --single-branch --branch fenghou https://github.com/cybertime-cs/Dancing_Robot.git FENGHOU
cd FENGHOU
bash scripts/pi_setup.sh
```

仓库保留程序、配置、剧本和音频，不包含 `.onnx` 模型权重、虚拟环境、缓存或现场录音。首次在树莓派联网执行上述安装脚本，会安装依赖，并通过 `scripts/prepare_sherpa_models.py` 下载 KWS 唤醒词模型、SenseVoice 识别模型及 Silero VAD，恢复到 `models/kws/`、`models/sensevoice/` 和 `models/vad/`；之后语音识别可离线运行。已有依赖时，也可只执行 `.venv/bin/python scripts/prepare_sherpa_models.py` 补全模型。项目自定义的唤醒词配置保留在仓库中，请勿将下载后的模型再次提交到 Git。

**异形机器人蜂后的语音交互与动作编排程序。**

本分支保存蜂后 FengHou 独立机器人项目，代码、依赖说明、剧本和运行音频均位于分支根目录。

MorphBot-Control 面向采用树莓派作为上位机、串口动作控制器作为下位机的异形机器人，把语音台词、配音、音乐和动作串成可排练的演出流程。当前实现案例为 **蜂后 FengHou**，主题剧本为《蜂后觉醒——生态守护者》。

项目目前包含蜂后的动作配置和五幕剧本。用于其他机器人时，需要适配动作文件、串口协议、剧本和音频素材；目前没有提供通用舵机编辑器或多机器人管理功能。

## 功能

- **单个动作排练**：18 个入口，包括 13 个基础动作和 5 段舞蹈，支持模拟、只播放配乐和实际执行。
- **剧本编排**：15 个状态节点、11 句交互台词，由当前台词触发配音、动作和状态转移，支持从指定节点开始。
- **语音交互**：说“蜂后”唤醒一次，随后持续等待台词；播放音频和执行动作期间暂停录音。
- **收音提示**：启动就绪进入唤醒等待时响一次约 0.49 秒的 ding；上一段配音或音乐完成、开始等待下一句台词时响一次。同一台词的识别重试、噪声丢弃和收音结束均不响；提示结束并留出 0.12 秒尾音间隔再开麦。
- **响应准备**：启动时加载并预热语音识别模型，就绪后才等待唤醒；后续台词复用模型，关麦后直接识别并匹配当前台词。
- **台词容错**：无声调拼音匹配处理同音误识别，较长台词加入保守的编辑距离匹配，只匹配当前状态。
- **巡查独立调用（本地开发版）**：唤醒后，在其他台词等待阶段说“前往目标区域”或其完整剧本台词，执行第二幕舞蹈与配乐后返回原等待位置；正常流程轮到巡查时照常推进。跨流程仅接受完整同音匹配，不使用泛关键词和近似猜测。此项尚未部署树莓派。
- **分句与日志**：Silero 人声检测和静音断句；显示识别文字、匹配、动作、串口结果及音频总时长和实际播放耗时。

句尾停顿现为 0.9 秒，避免自然停顿过早切断长台词；日志增加录音片段时长及判定句尾静音，现场问题与回放验证见[台词断句与轮次提示](docs/台词断句与轮次提示-2026-10-16.md)。

当前运行程序只包含动作、剧本和语音交互。第二幕采用定时表演，不进行摄像头视觉识别。

2026-10-16 收音提示音与响应优化已同步到 `pi@10.87.80.207`，后台完成预热并等待唤醒。验证结果见[本次部署记录](docs/部署记录-2026-10-16.md)。

## 工作流程

```text
等待“蜂后”唤醒
    ↓
持续监听 → 人声分句 → 语音转文字 → 匹配当前台词
    ↑                                  ↓
    └──── 音频与动作完成 ← 配音 / 音乐 / 串口动作
                                       ↓
                                  转到下一节点
```

只有当前节点的台词可以推进剧情。未匹配时保持当前节点。本地开发版额外允许巡查独立调用，但调用完成不会改变原节点，详见[使用指南](使用指南.md#94-本地开发版前往目标区域独立调用)。普通手动运行完成一轮后退出；开机服务使用多轮模式，每轮结束后重新等待“蜂后”唤醒。

## 蜂后 FengHou 案例

当前使用 [2026-10-07 更新的新2剧本](docs/剧本-蜂后/蜂后机器人剧本_新2.docx)，现场已包含 2026-10-16 的提示音与响应优化，详见[最新部署记录](docs/部署记录-2026-10-16.md)。当前分支包含本地备份中的这一版代码。
第一幕任务台词为“蜂后，寻找生命，启动生态恢复”；第四幕从“谢谢你，让花海重新绽放”开始。
新版不再播放 `1-2`、`2-5`、`4-1`、`4-5`、`5-1`；这些素材保留供历史排练使用。
新2剧本进一步取消 `2-6`、`3-2`、`4-4`、`4-6`、`5-2`，不再等待对应的五句台词。
第二、三、四幕舞蹈完成后直接播放 `bgm2`、`bgm3`、`bgm4`，随后等待下一幕台词。
第一、二幕动作音频已替换，总时长分别为 55.98 秒和 61.75 秒；下位机动作文件名沿用 `act1.odr`、`act2.odr`。
更新记录见 [CHANGELOG](CHANGELOG.md)。

| 幕 | 内容 | 下位机舞蹈文件 |
|---|---|---|
| 第一幕 | 唤醒、机体自检、接受生态恢复任务 | `act1.odr` |
| 第二幕 | 定时环境分析、前往目标区域 | `act2.odr` |
| 第三幕 | 授粉、生态恢复 | `act3.odr` |
| 第四幕 | 守护花海对话、生命之舞 | `act4.odr` |
| 第五幕 | 花海巡礼、任务完成 | `act5.odr` |

第二幕按“荒漠 → 裸露土地 → 花海”演示，三段等待均为 2 秒，从上一段音频结束后计时。三段环境音效内部的长静音已压缩，工作人员可配合展示舞台图片。调整记录见[语音响应与第二幕衔接优化](docs/语音响应与第二幕衔接优化-2026-10-16.md)。

## 硬件与环境

- 树莓派，使用带音频支持的 64 位 Linux 系统。
- C270 麦克风或其他 PyAudio 可用输入设备。
- 喇叭及系统可用音频输出。
- 支持当前协议、保存所需动作文件的串口动作控制器。
- Python、NumPy、PyAudio、pyserial、sherpa-onnx、pypinyin，以及 mplayer 或 ffplay。

蜂后现场使用 C270 输入、树莓派调试串口 `/dev/serial0`、115200 波特率。其他机型需确认实际串口映射、接线和权限。

实际 `.odr` / `.bin` 动作文件存放在下位机。本项目发送文件名执行命令，不包含下位机固件或动作文件本体。

## 安装

以下命令在树莓派执行。Windows 用户先通过 SSH 登录，再执行同样的命令。

```bash
git clone --single-branch --branch fenghou https://github.com/cybertime-cs/Dancing_Robot.git FENGHOU
cd FENGHOU
bash scripts/pi_setup.sh
```

已有现场部署目录仍使用 `/home/pi/queen_robot`，无需因仓库目录调整而重新安装。

现场机器的手动运行命令：

```bash
systemctl --user stop fenghou.service
cd /home/pi/queen_robot
bash scripts/pi_run.sh
```

手动排练结束后，使用 `systemctl --user start fenghou.service` 恢复开机服务。

安装脚本准备系统依赖、独立虚拟环境和语音模型，并运行软件检查。国内 PyPI 镜像方式：

```bash
bash scripts/pi_setup.sh --cn-mirror
```

模型权重不提交到 Git，由 `scripts/prepare_sherpa_models.py` 准备。离线部署可指定现有模型目录：

```bash
bash scripts/pi_setup.sh --models-from /path/to/models
```

## 机器配置

在 `FENGHOU/` 创建机器专属配置：

```bash
cp runtime.env.example runtime.env
nano runtime.env
```

蜂后示例：

```bash
MIC_DEVICE_NAME=C270
PI_SERIAL_PORT=/dev/serial0
PI_SERIAL_BAUD=115200
```

`scripts/pi_run.sh` 自动加载此文件并使用 `.venv`。`runtime.env` 不进入版本管理。

如果使用 UART，开启串口硬件、关闭占用该接口的串口登录，并确保用户有读写权限。首次接线后检查：

```bash
set -a
source runtime.env
set +a
.venv/bin/python scripts/pi_doctor.py --hardware
```

该检查打开麦克风、检查串口设备权限，不发送动作。串口通信和实际动作仍需分别测试。

## 运行与分项测试

所有命令在 `FENGHOU/` 执行，一次只运行一种模式。手动排练前先执行 `systemctl --user stop fenghou.service`，结束后用 `systemctl --user start fenghou.service` 恢复。

| 目的 | 命令 | 实体动作 |
|---|---|---|
| 配置与素材检查 | `bash scripts/pi_run.sh --check` | 无 |
| 五幕纯模拟，无声音和等待 | `bash scripts/pi_run.sh --dry-run --demo` | 无 |
| 完整语音排练，正常配音 | `bash scripts/pi_run.sh --silent-actions` | 无 |
| 键盘输入排练，正常配音 | `bash scripts/pi_run.sh --text --silent-actions` | 无 |
| 查看动作清单 | `bash scripts/pi_run.sh --list-actions` | 无 |
| 第一幕舞蹈模拟 | `bash scripts/pi_run.sh --action act1 --dry-run` | 无 |
| 只播放第一幕配乐 | `bash scripts/pi_run.sh --action act1 --silent-actions` | 无 |
| 实际执行前进 | `bash scripts/pi_run.sh --action forward` | 有 |
| 第一幕舞蹈与配乐 | `bash scripts/pi_run.sh --action act1` | 有 |
| 正式五幕演出 | `bash scripts/pi_run.sh` | 有 |

正式运行后，先说“蜂后”，听完回复再说“执行机体自检”。后续按终端当前台词推进，等待音频与动作完成后再说下一句。

从第三幕开始无动作排练：

```bash
bash scripts/pi_run.sh --start-state RESTORE --silent-actions
```

仍需先唤醒，再说第三幕台词。指定节点是起点，程序会继续后续剧情，不会自动在该幕结束时停止。只测一段舞蹈用 `--action act1` 至 `--action act5`。

**逐项测试的完整命令、预期结果、台词与故障排查见 [使用指南](使用指南.md)。** 推荐依次检查配置、音量、唤醒、单句识别、台词匹配，再测试实体动作。

## 日志与停止

显示实时输出并保存当天日志：

```bash
mkdir -p deployment_logs
set -o pipefail
bash scripts/pi_run.sh 2>&1 | tee -a "deployment_logs/$(TZ=Asia/Shanghai date +%F).log"
```

音频日志示例：

```text
[19:28:06] [音频] 1-1 | 开始 | 总时长 3.81 秒
[19:28:10] [音频] 1-1 | 完成 | 总时长 3.81 秒 | 实际耗时 4.22 秒
```

总时长来自素材索引，实际耗时包含播放器启动和退出，不包含后续串口等待。素材大小变化导致索引失效时显示“未知”。使用 `ROBOT_DEBUG=1` 查看详细诊断。

按 **Ctrl+C** 结束调度并回收资源。已经下发的实体动作需通过下位机停止。播放失败或串口应答超时会中止演出，不自动重发。

## 修改剧本与适配其他机器人

| 文件 | 用途 |
|---|---|
| `queen_robot/queen_dialog.json` | 台词、状态转移、音频顺序、等待和分句配置 |
| `actions.json` | 动作编号、下位机文件名、配乐和超时 |
| `models/kws/keywords_raw.txt` | 初始唤醒词来源 |
| `serial_link.py`、`datapackage.py` | 下位机通信与命令组包 |
| `resources/` | 配音、音效、舞蹈与背景音乐 |
| `audio_durations.json` | 音频时长和文件大小索引 |

适配其他机器人时，先核实下位机协议，再配置动作和剧本。替换音频后同步更新时长索引。修改唤醒词后运行 `.venv/bin/python scripts/make_keywords.py`。

默认 Silero 分句停顿为 0.4 秒、前置缓存 0.3 秒、最长连续语音 15 秒。长句近似匹配阈值为 86%，短词仅接受完整同音。匹配分数不是语音模型置信度。

## 测试与限制

无需外设的回归检查：

```bash
.venv/bin/python scripts/selftest.py
```

真实模型的离线分句检查：

```bash
.venv/bin/python scripts/smoke_listening.py
```

离线检查不能替代现场评估。人声检测不能区分演员与旁人；初始唤醒和后续台词识别是不同环节；串口应答是否表示动作完成取决于下位机协议。

已提供 systemd 用户服务，开机等待外设就绪后进入唤醒。服务运行多轮，每轮完成后重新等待唤醒；普通手动运行保持单轮。安装及管理见[自启动指南](自启动指南.md)。

## 目录

```text
FENGHOU/
├── README.md                 项目介绍与安装
├── CHANGELOG.md              更新记录
├── main.py                   统一入口
├── 使用指南.md                分项操作与测试
├── 自启动指南.md              开机服务安装与管理
├── runtime.env.example       机器配置模板
├── actions.json              动作清单
├── queen_robot/              状态机、剧本与执行
├── models/                   模型说明与唤醒词配置
├── resources/                必要演出音频
├── scripts/                  安装、检查与启动
├── services/                 开机服务模板
├── tests/                    回归检查
└── docs/
    ├── 串口排查记录.md         实际端口、回执与超时分析
    └── 剧本-蜂后/             原始与新版 Word 剧本、来源 BGM
```
