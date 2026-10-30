#!/usr/bin/env python3
"""银河号口令训练：先选择目标指令，再录音、识别并确认写入。"""
import argparse
import json

from yinhe_robot import (
    CONFIG_FILE,
    CommandParser,
    MicrophoneUnavailable,
    SherpaStreamingRecognizer,
    load_config,
    matches_master_wake,
)


def save_config(config):
    with CONFIG_FILE.open("w", encoding="utf-8") as file:
        json.dump(config, file, ensure_ascii=False, indent=2)
        file.write("\n")


def select_command(config):
    commands = list(config["commands"].items())
    if "master_wake" in config:
        commands.append(("master_wake", config["master_wake"]))
    print("\n请选择要训练的指令：")
    print("0: 退出")
    for index, (command_id, command) in enumerate(commands, start=1):
        print(f"{index}: {command['title']}（标准口令：{command['phrases'][0]}）")
    while True:
        try:
            selected = int(input("请输入编号：").strip())
        except ValueError:
            print("请输入数字编号。")
            continue
        if selected == 0:
            return None, None
        if 1 <= selected <= len(commands):
            return commands[selected - 1]
        print("编号不存在，请重试。")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", help="只测试文本匹配，不打开麦克风")
    parser.add_argument("--count", type=int, default=5, help="每个选定指令最多录制次数，默认 5")
    args = parser.parse_args()
    config = load_config()
    matcher = CommandParser(config)

    if args.text:
        command_id, _ = matcher.match(args.text)
        print(json.dumps({
            "asr_text": args.text,
            "matched_command": command_id,
            "matched_master_wake": matches_master_wake(config, args.text),
        }, ensure_ascii=False))
        return

    recognizer = None
    while True:
        command_id, command = select_command(config)
        if command_id is None:
            return
        if recognizer is None:
            print("正在加载本地 Sherpa 模型……")
            recognizer = SherpaStreamingRecognizer(config["asr"])
        for attempt in range(1, args.count + 1):
            input(f"\n第 {attempt}/{args.count} 次。确认后请说“{command['phrases'][0]}”，按回车开始录音： ")
            try:
                text = recognizer.listen_once().replace(" ", "").strip()
            except MicrophoneUnavailable as exc:
                print(f"录音失败：{exc}")
                continue
            print(f"识别结果：{text or '（空）'}")
            if not text:
                continue
            owner, _ = matcher.match(text)
            if owner and owner != command_id:
                print(f"该结果已匹配到“{config['commands'][owner]['title']}”，为避免冲突不写入。")
                continue
            if text in command["phrases"]:
                print("该结果已存在，不重复添加。")
                continue
            if input(f"添加“{text}”到“{command['title']}”？[y/N] ").strip().lower() != "y":
                print("未添加。")
                continue
            command["phrases"].append(text)
            save_config(config)
            print(f"已保存：{text} -> {command['title']}")


if __name__ == "__main__":
    main()
