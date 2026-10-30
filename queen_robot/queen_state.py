"""同步调度及巡查独立调用：音频/动作期间不收音，失败不重发。"""
from .line_match import match_line, match_standalone_travel
from runtime_log import event


class QueenState:
    def __init__(self, script, actions, start_state=None):
        self.script = script
        self.actions = actions
        self.state = start_state or script['initial']
        if self.state not in script['states']:
            raise ValueError('未知起始节点：%s' % self.state)
        self.failed_state = None
        self.busy = False
        self.started = False

    @property
    def finished(self):
        return self.state in ('ENDING', 'ERROR')

    @property
    def prompt(self):
        return self.script['states'][self.state]['prompt'] if self.state != 'ERROR' else '演出已中止'

    def _steps(self, steps):
        for step in steps:
            if 'wait_setting' in step:
                step = {'wait': self.script['timing'][step['wait_setting']]}
            self.actions.execute(step)

    def _advance(self):
        while True:
            event('步骤', '%s | %s' % (self.state, self.prompt))
            node = self.script['states'][self.state]
            self._steps(node['steps'])
            self.state = node['next']
            if self.state == 'ENDING' or not self.script['states'][self.state].get('auto'):
                return

    def _fail(self):
        self.failed_state = self.state
        self.state = 'ERROR'

    def start(self):
        if self.started:
            return
        self.started = True
        try:
            if self.state == self.script['initial']:
                self._steps(self.script.get('startup', []))
            if self.script['states'][self.state].get('auto'):
                self._advance()
        except BaseException:
            self._fail()
            raise

    def handle(self, text):
        if self.finished or self.busy:
            return False
        node = self.script['states'][self.state]
        result = match_line(text, node)
        standalone = False
        travel = self.script['states'].get('TRAVEL')
        if (not result.accepted and travel and not node.get('auto')
                and self.state not in (self.script['initial'], 'TRAVEL')):
            result = match_standalone_travel(text, travel)
            standalone = result.accepted
        if not result.accepted:
            event('忽略', result.reason, debug=True)
            return False
        event('匹配', '%s | 相似度 %.0f%% | %s' % (result.method, result.score * 100, result.target))
        self.busy = True
        try:
            if standalone:
                event('独立调用', 'TRAVEL | 完成后返回 %s：%s' % (self.state, self.prompt))
                # 不调用 _advance，避免改变原等待位置或连带执行后续剧情。
                self._steps(travel['steps'])
                event('返回等待', '%s：%s' % (self.state, self.prompt))
            else:
                self._advance()
        except BaseException:
            if standalone:
                self.failed_state = 'TRAVEL'
                self.state = 'ERROR'
            else:
                self._fail()
            raise
        finally:
            self.busy = False
        return True
