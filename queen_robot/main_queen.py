"""python -m queen_robot.main_queen --dry-run --demo"""
import argparse
import sys
from pathlib import Path

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from queen_robot.queen_actions import QueenActions
from queen_robot.queen_script import load_script
from queen_robot.queen_state import QueenState


def run_dialog(engine, listen, wake=None):
    if wake is not None:
        wake()  # 返回前已关闭唤醒麦克风，后续播放和录音不会抢设备。
    engine.start()
    if wake is not None:
        if engine.state == 'BOOT':
            engine.handle('蜂后')
    new_turn = True
    while not engine.finished:
        print('[queen] 等待 %s：%s' % (engine.state, engine.prompt), flush=True)
        # 只在上一段播放结束后提示；当前台词的识别重试不重新鸣响。
        text = listen(cue=new_turn)
        print('[queen] 输入：%s' % text, flush=True)
        new_turn = engine.handle(text)
        if not new_turn:
            print('[queen] 未匹配当前台词，请重说；状态不变', flush=True)
    print('[queen] %s：%s' % (engine.state, engine.prompt), flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description='蜂后五幕演出：台词驱动，第二幕自动计时演示')
    parser.add_argument('--script', type=Path, help='自定义剧本 JSON')
    parser.add_argument('--check', action='store_true', help='只检查配置及素材，不打开硬件')
    parser.add_argument('--dry-run', action='store_true', help='仅打印，不播音、不录音、不发串口、不等待')
    parser.add_argument('--demo', action='store_true', help='自动输入完整五幕台词；必须搭配 --dry-run')
    parser.add_argument('--text', action='store_true', help='键盘台词输入；仍会播放音频并执行动作')
    parser.add_argument('--silent-actions', action='store_true', help='保留真实音频与时间，但不发串口')
    parser.add_argument('--start-state', help='从指定节点继续排练（该节点的动作会重新执行）')
    parser.add_argument('--action', help='单独排练一个动作（编号或中文名）；会播放配乐并下发动作')
    parser.add_argument('--list-actions', action='store_true', help='列出可单独排练的动作')
    parser.add_argument('--repeat', action='store_true', help='完整演出结束后重新等待唤醒，连续多轮')
    args = parser.parse_args(argv)
    if args.repeat and (args.action or args.demo or args.text or args.dry_run or args.check or args.list_actions or args.start_state):
        parser.error('--repeat 只用于从开头开始的语音演出，可搭配 --silent-actions')
    if args.list_actions:
        from action_catalog import load_actions
        for item in load_actions():
            print('%-18s %s → %s' % (item['id'], item['label'], item['file']))
        return 0
    if args.action and (args.demo or args.start_state or args.text or args.check):
        parser.error('--action 只可搭配 --dry-run、--silent-actions 或 --script')
    if args.demo and (not args.dry_run or args.start_state):
        parser.error('--demo 必须搭配 --dry-run，且从完整剧本开头运行')
    actions = None
    engine = None
    try:
        script = load_script(args.script)
        if args.check:
            from action_catalog import load_actions
            catalog = load_actions()
            print('[queen] 配置与音频检查通过：%d 个节点、%d 个独立动作，第二幕自动计时；未检测硬件' % (len(script['states']), len(catalog)))
            return 0
        actions = QueenActions(script, args.dry_run, args.silent_actions)
        if args.action:
            from action_catalog import get_action
            actions.run_action(get_action(args.action))
            print('[queen] 单动作排练完成')
            return 0
        engine = QueenState(script, actions, args.start_state)
        wake = None
        if args.demo:
            lines = iter(script['demo_inputs'])
            def listen(cue=True):
                try:
                    return next(lines)
                except StopIteration as exc:
                    raise RuntimeError('模拟台词已用完，但演出尚未结束') from exc
        elif args.text or args.dry_run:
            def listen(cue=True):
                return input('台词（Ctrl+C 退出）> ')
        else:
            from speech_recog import listen_for_line, backend_summary, prepare_listening
            from wake import wait_for_wake
            prepare_listening()
            wake = wait_for_wake
            print('[queen] 连续语音识别：%s；播放期间不录音' % backend_summary(), flush=True)
            def listen(cue=True):
                return listen_for_line(script.get('listening'), cue=cue)
        while True:
            run_dialog(engine, listen, wake=wake)
            if not args.repeat:
                break
            actions.close()
            print('[queen] 本轮演出结束，重新等待“蜂后”唤醒。', flush=True)
            actions = QueenActions(script, args.dry_run, args.silent_actions)
            engine = QueenState(script, actions)
        return 0
    except (KeyboardInterrupt, EOFError):
        print('\n[queen] 已退出调度。已下发的实体动作请通过下位机控制停止。', flush=True)
        return 130
    except Exception as exc:
        state = engine.failed_state or engine.state if engine else '启动'
        print('[queen] 中止于 %s：%s' % (state, exc), file=sys.stderr)
        return 1
    finally:
        if actions is not None:
            actions.close()


if __name__ == '__main__':
    raise SystemExit(main())
