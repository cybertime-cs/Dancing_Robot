SHELL := /bin/bash
PY := $(shell if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi)
.DEFAULT_GOAL := help
.PHONY: help setup setup-fast setup-cn selftest doctor audio audio-fix models keywords run run-silent check demo actions action speech queen queen-check queen-demo queen-silent queen-test

help:
	@echo "run / run-silent：唤醒后完整演出 / 播音但不下发动作"
	@echo "check / demo：配置检查 / 五幕纯模拟"
	@echo "actions / action NAME=act1：动作清单 / 单动作排练（会下发动作）"
	@echo "action NAME=act1 FLAGS=--dry-run：单动作纯模拟"
	@echo "setup / setup-cn：部署 / 使用国内镜像"
	@echo "selftest / doctor / audio / audio-fix / models / keywords / speech"

setup setup-fast:
	bash scripts/pi_setup.sh
setup-cn:
	bash scripts/pi_setup.sh --cn-mirror
selftest queen-test:
	$(PY) scripts/selftest.py
doctor:
	$(PY) scripts/pi_doctor.py --hardware
audio:
	bash scripts/pi_audio_setup.sh
audio-fix:
	bash scripts/pi_audio_setup.sh --fix
models:
	$(PY) scripts/prepare_sherpa_models.py
keywords:
	$(PY) scripts/make_keywords.py
run queen:
	bash scripts/pi_run.sh
run-silent queen-silent:
	bash scripts/pi_run.sh --silent-actions
check queen-check:
	$(PY) main.py --check
demo queen-demo:
	$(PY) main.py --dry-run --demo
actions:
	$(PY) main.py --list-actions
action:
	$(PY) main.py --action "$(NAME)" $(FLAGS)
speech:
	$(PY) speech_recog.py
