import unittest
from queen_robot.line_match import match_line
from queen_robot.queen_script import load_script


class LineMatchingTests(unittest.TestCase):
    def setUp(self):
        self.states = load_script()['states']

    def test_homophones_match_initial_dialog_cue(self):
        for text in ('蜂后蜂后','丰后丰后','丰厚丰厚','风后','封后封后'):
            self.assertTrue(match_line(text,self.states['BOOT']).accepted, text)

    def test_every_script_cue_still_matches(self):
        for node in self.states.values():
            if node.get('keywords'):
                self.assertTrue(match_line(node['prompt'],node).accepted,node['prompt'])
                for keyword in node['keywords']:
                    self.assertTrue(match_line(keyword,node).accepted,keyword)

    def test_observed_cues_match_despite_name_transcription(self):
        for state,text in [('SELF_CHECK','丰后执行机体自检。'),
                           ('VISION_START','风厚启动视觉环境视觉识别系统，分析前方区域。'),
                           ('FINAL_CONFIRM','丰厚生态恢复任务完成。')]:
            self.assertTrue(match_line(text,self.states[state]).accepted,text)

    def test_long_phrase_can_tolerate_one_small_error(self):
        result=match_line('蜂后前往目标区域执行生态巡察任务',self.states['TRAVEL'])
        self.assertTrue(result.accepted)

    def test_background_talk_and_mixed_paragraph_rejected(self):
        for text in ('丰后这个名字挺好','我们刚才说蜂后但是没有在叫它','效果挺好模型效果挺好','9','。'):
            self.assertFalse(match_line(text,self.states['BOOT']).accepted,text)

    def test_revised_script_lines_match_current_states(self):
        for state, text in [('SELF_CHECK', '执行机体自检'),
                            ('SEARCH', '蜂后寻找生命启动生态恢复'),
                            ('TOGETHER_THANKS', '谢谢你让花海重新绽放'),
                            ('LIFE_DANCE', '蜂后请用你的舞蹈为重新归来的生命献上祝福'),
                            ('FINAL_CONFIRM', '蜂后生态恢复任务完成')]:
            self.assertTrue(match_line(text, self.states[state]).accepted, text)
        self.assertFalse(match_line('蜂后蜂后', self.states['TOGETHER_THANKS']).accepted)
        text='丰后前往目标区域执行生态巡查任务到时候放歌千万一定要放上那个师傅假设没放上还要再继续讨论其他事情'
        self.assertFalse(match_line(text,self.states['TRAVEL']).accepted)

    def test_negative_and_wrong_stage_remain_blocked(self):
        for text in ('不要执行机体自检','取消机体自检','不执行机体自检','蜂后报告生态恢复结果'):
            self.assertFalse(match_line(text,self.states['SELF_CHECK']).accepted,text)
