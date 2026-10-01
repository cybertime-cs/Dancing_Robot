import importlib.util
import json
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parents[1]

for name in ("interaction_zh.py", "action_neo.py", "speech_recog.py", "snowboydecoder.py"):
    compile((ROOT / name).read_text(encoding="utf-8"), name, "exec")
with (ROOT / "speech_train.json").open(encoding="utf-8") as stream:
    assert json.load(stream)["交互模式"]["name"] == "interaction_mode"
print("STATIC: Python syntax and interaction routing JSON passed")

class FakeClient:
    chunks = []

    def __init__(self, **kwargs):
        assert kwargs["host"] == "http://127.0.0.1:11434"

    def chat(self, **kwargs):
        assert kwargs["model"] == "qwen:0.5b"
        assert kwargs["stream"] is True
        assert kwargs["messages"] == [{"role": "user", "content": "测试"}]
        return iter(self.chunks)

sys.modules["ollama"] = types.SimpleNamespace(Client=FakeClient)
spec = importlib.util.spec_from_file_location("interaction_under_test", ROOT / "interaction_zh.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
spoken = []
module.speak = spoken.append

FakeClient.chunks = [
    {"message": {"content": "你好*。"}},
    {"message": {"content": "继续#说"}},
]
actual = module.robust_offline_query("测试")
assert actual == "你好*。继续#说", actual
assert spoken == ["你好。", "继续说"], spoken
print("STUB: streaming text accumulation, punctuation flush and final flush passed")

spoken.clear()
class BrokenStream:
    def __iter__(self):
        yield {"message": {"content": "前半句"}}
        raise RuntimeError("stream interrupted")

FakeClient.chunks = BrokenStream()
actual = module.robust_offline_query("测试")
assert actual == "前半句", actual
assert spoken == ["前半句"], spoken
print("STUB: stream interruption returns partial text and speaks buffered text")
