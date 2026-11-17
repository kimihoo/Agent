#!/usr/bin/env python3
"""手写 ReAct Agent：3 个工具，零框架依赖。

运行方式：
    python3 react_agent.py                    # 跑 6 个自测用例（离线 mock 模型）
    python3 react_agent.py 北京天气如何        # 单次提问（离线 mock 模型）
    OPENAI_API_KEY=... python3 react_agent.py --live 北京天气如何   # 接真实模型

结构：
    tool()              工具注册表，从函数签名生成 schema
    parse_action()      解析 Thought / Action / Action Input
    ReActAgent.run()    主循环：推理 -> 解析 -> 执行 -> 回填 Observation
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from typing import Any, Callable, get_type_hints

# ---------------------------------------------------------------------------
# 1. 工具注册表：name -> {fn, spec}
# ---------------------------------------------------------------------------

TOOLS: dict[str, dict[str, Any]] = {}


def tool(fn: Callable) -> Callable:
    """把函数登记成工具，并用它的签名和 docstring 生成给模型看的说明。"""
    hints = get_type_hints(fn)
    hints.pop("return", None)
    type_map = {str: "string", int: "integer", float: "number", bool: "boolean"}
    props = {k: {"type": type_map.get(v, "string")} for k, v in hints.items()}

    TOOLS[fn.__name__] = {
        "fn": fn,
        "spec": {
            "name": fn.__name__,
            "description": (fn.__doc__ or "").strip().splitlines()[0],
            "parameters": {
                "type": "object",
                "properties": props,
                "required": list(hints),
            },
        },
    }
    return fn


_WEATHER = {"北京": "晴，18°C，北风 2 级", "上海": "多云，22°C，东南风 1 级"}
_TODOS: list[str] = []


@tool
def get_weather(city: str) -> str:
    """查询指定城市的当前天气与温度。"""
    if city not in _WEATHER:
        raise ValueError(f"没有 {city} 的天气数据")
    return _WEATHER[city]


@tool
def search_notes(query: str) -> str:
    """在个人笔记库中检索与关键词相关的片段。"""
    return (
        f"[命中 3 条] query={query}；"
        "1) 部署流程：先跑 migrate 再滚动重启；"
        "2) 部署失败回滚：保留上一版本镜像 tag；"
        "3) 遗留问题：预发环境缺少监控告警。"
    )


@tool
def create_todo(text: str) -> str:
    """新建一条待办事项，返回待办 id。"""
    _TODOS.append(text)
    return f"todo_{1000 + len(_TODOS)} created: {text}"


def build_system_prompt() -> str:
    lines = ["你可以使用以下工具："]
    for name, item in TOOLS.items():
        params = ", ".join(
            f"{k}: {v['type']}"
            for k, v in item["spec"]["parameters"]["properties"].items()
        )
        lines.append(f"- {name}({params}): {item['spec']['description']}")

    lines += [
        "",
        "严格按以下格式回复，每轮只输出一个 Action：",
        "Thought: 我还需要什么信息",
        "Action: 工具名",
        'Action Input: {"参数": "值"}',
        "",
        "当信息足够时，改为输出：",
        "Thought: 已有足够信息",
        "Final Answer: 最终回答",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 2. 解析与参数校验
# ---------------------------------------------------------------------------


class ParseError(Exception):
    pass


def parse_action(text: str) -> tuple[str, dict[str, Any]]:
    """从模型输出里取出 (工具名, 参数字典)。解析失败抛 ParseError。"""
    name_match = re.search(r"Action\s*[:：]\s*(\S+)", text)
    if not name_match:
        raise ParseError("缺少 Action 行")

    input_match = re.search(r"Action Input\s*[:：]\s*(\{.*\})", text, re.S)
    raw = input_match.group(1).strip() if input_match else "{}"

    try:
        args = json.loads(raw)
    except json.JSONDecodeError:
        try:  # 兜底：模型偶尔会用单引号
            args = json.loads(raw.replace("'", '"'))
        except json.JSONDecodeError as exc:
            raise ParseError(f"Action Input 不是合法 JSON：{exc}") from exc

    if not isinstance(args, dict):
        raise ParseError("Action Input 必须是 JSON 对象")
    return name_match.group(1).strip(), args


def coerce_args(fn: Callable, args: dict[str, Any]) -> dict[str, Any]:
    """按函数签名做缺参检查和简单类型转换，避免工具里抛 TypeError。"""
    hints = get_type_hints(fn)
    hints.pop("return", None)

    missing = [k for k in hints if k not in args]
    if missing:
        raise ValueError(f"缺少参数 {missing}")

    result = {}
    for key, value in args.items():
        if key not in hints:
            continue
        target = hints[key]
        result[key] = target(value) if target in (int, float, str) else value
    return result


# ---------------------------------------------------------------------------
# 3. 主循环
# ---------------------------------------------------------------------------


class ReActAgent:
    def __init__(self, llm: Callable[[list[dict]], str], max_steps: int = 6,
                 observation_limit: int = 2000) -> None:
        self.llm = llm
        self.max_steps = max_steps
        self.observation_limit = observation_limit

    def run(self, question: str) -> dict[str, Any]:
        messages: list[dict] = [
            {"role": "system", "content": build_system_prompt()},
            {"role": "user", "content": question},
        ]
        steps: list[dict] = []
        seen: set[tuple] = set()

        for index in range(1, self.max_steps + 1):
            output = self.llm(messages)
            messages.append({"role": "assistant", "content": output})

            step = {
                "step": index,
                "thought": _extract_thought(output),
                "action": None,
                "input": None,
                "observation": None,
                "final": None,
            }

            # 停止条件 1：拿到最终答案
            if "Final Answer:" in output:
                answer = output.split("Final Answer:", 1)[1].strip()
                step["final"] = answer
                steps.append(step)
                return {"answer": answer, "steps": steps, "stopped": "final"}

            # 解析失败：把错误变成一次 Observation 让模型自己纠
            try:
                name, args = parse_action(output)
            except ParseError as exc:
                observation = f"格式错误（{exc}）。请严格按 Thought/Action/Action Input 格式重试。"
                step["observation"] = observation
                steps.append(step)
                messages.append({"role": "user", "content": f"Observation: {observation}"})
                continue

            step["action"] = name
            step["input"] = args
            key = (name, json.dumps(args, sort_keys=True, ensure_ascii=False))

            # 停止条件 2：同一动作重复，提示换思路
            if key in seen:
                observation = "你重复了同一个动作，请换一个思路，或直接给出 Final Answer。"
            elif name not in TOOLS:
                observation = f"未知工具 {name}，可用工具：{', '.join(TOOLS)}"
            else:
                # 执行工具；异常转成字符串，交给模型决定下一步
                try:
                    raw = TOOLS[name]["fn"](**coerce_args(TOOLS[name]["fn"], args))
                    observation = str(raw)
                except Exception as exc:  # noqa: BLE001 - 故意兜住所有工具异常
                    observation = f"工具执行失败：{type(exc).__name__}: {exc}"
                seen.add(key)
                observation = observation[: self.observation_limit]

            step["observation"] = observation
            steps.append(step)
            messages.append({"role": "user", "content": f"Observation: {observation}"})

        # 停止条件 3：步数上限
        return {
            "answer": "已达到步数上限，未能得出最终答案。",
            "steps": steps,
            "stopped": "max_steps",
        }


def _extract_thought(output: str) -> str:
    match = re.search(r"Thought\s*[:：]\s*(.+)", output)
    if match:
        return match.group(1).strip()
    return output.strip().splitlines()[0][:80] if output.strip() else ""


# ---------------------------------------------------------------------------
# 4. 两个 LLM 后端：离线 mock / OpenAI 兼容接口
# ---------------------------------------------------------------------------


class MockLLM:
    """规则驱动的假模型，只负责按 ReAct 格式吐文本，用于离线跑通循环。"""

    def __init__(self, faults: dict[int, str] | None = None, loop: bool = False) -> None:
        self.faults = faults or {}  # 第 N 轮注入格式错误
        self.loop = loop            # 每轮都调用同一工具，用于验证 max_steps
        self.turn = 0

    def __call__(self, messages: list[dict]) -> str:
        self.turn += 1
        if self.turn in self.faults:
            return "让我先想一想这个问题。"

        if self.loop:
            return 'Thought: 再检索一次。\nAction: search_notes\nAction Input: {"query": "部署"}'

        question = next(m["content"] for m in messages if m["role"] == "user")
        observations = [
            m["content"][len("Observation: "):]
            for m in messages
            if m["role"] == "user"
            and m["content"].startswith("Observation: ")
            and not m["content"].startswith("Observation: 格式错误")
            and not m["content"].startswith("Observation: 你重复")
        ]

        if "你好" in question and not observations:
            return (
                "Thought: 简单问候，不需要工具。\n"
                "Final Answer: 你好，我是手写版 ReAct Agent，"
                "现在支持天气查询、笔记检索和新建待办三个工具。"
            )

        if "天气" in question:
            if not observations:
                city = next((c for c in ("北京", "上海", "火星") if c in question), "北京")
                return (
                    f"Thought: 需要查询{city}的实时天气。\n"
                    f'Action: get_weather\nAction Input: {{"city": "{city}"}}'
                )
            return f"Thought: 已拿到天气结果，可以作答。\nFinal Answer: {observations[0]}"

        if "笔记" in question or "部署" in question:
            if not observations:
                return (
                    'Thought: 先在笔记库里检索与部署相关的内容。\n'
                    'Action: search_notes\nAction Input: {"query": "部署"}'
                )
            if len(observations) == 1:
                return (
                    'Thought: 检索到了记录，再建一条跟进待办。\n'
                    'Action: create_todo\nAction Input: {"text": "跟进部署记录中的遗留问题"}'
                )
            return (
                "Thought: 检索和待办都已完成。\n"
                f"Final Answer: {observations[0]}\n待办已创建：{observations[1]}"
            )

        if not observations:
            return (
                f'Thought: 先检索一下笔记。\nAction: search_notes\n'
                f'Action Input: {{"query": "{question[:10]}"}}'
            )
        return f"Thought: 已有信息。\nFinal Answer: {observations[-1]}"


class OpenAICompatLLM:
    """可选后端：任何兼容 /chat/completions 的服务（OpenAI、DeepSeek、本地 vLLM 等）。"""

    def __init__(self) -> None:
        self.key = os.environ["OPENAI_API_KEY"]
        self.model = os.getenv("LLM_MODEL", "gpt-4o-mini")
        self.base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")

    def __call__(self, messages: list[dict]) -> str:
        payload = json.dumps(
            {"model": self.model, "messages": messages, "temperature": 0}
        ).encode()
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.key}",
            },
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.load(response)["choices"][0]["message"]["content"]


# ---------------------------------------------------------------------------
# 5. 轨迹打印与自测
# ---------------------------------------------------------------------------


def print_result(question: str, result: dict[str, Any]) -> None:
    print(f"Q: {question}")
    for item in result["steps"]:
        head = f"  [{item['step']}]"
        if item["action"]:
            args = json.dumps(item["input"], ensure_ascii=False)
            print(f"{head} Action      {item['action']}({args})")
            print(f"      Observation {item['observation']}")
        elif item["final"] is not None:
            print(f"{head} Answer      {item['final']}")
        else:
            print(f"{head} 纠正        {item['observation']}")
    print()


def _check(name: str, passed: bool) -> bool:
    print(f"[{'PASS' if passed else 'FAIL'}] {name}")
    return passed


def self_test() -> int:
    print("=" * 70)
    print("用例 1：无需工具，直接回答")
    print("=" * 70)
    result = ReActAgent(MockLLM()).run("你好")
    print_result("你好", result)
    checks = [
        _check("无需工具直接回答",
               result["stopped"] == "final" and all(s["action"] is None for s in result["steps"]))
    ]

    print("=" * 70)
    print("用例 2：单工具单步")
    print("=" * 70)
    result = ReActAgent(MockLLM()).run("北京天气如何")
    print_result("北京天气如何", result)
    actions = [s["action"] for s in result["steps"] if s["action"]]
    checks.append(_check("单工具单步", actions == ["get_weather"] and result["stopped"] == "final"))

    print("=" * 70)
    print("用例 3：两个工具串联（检索 -> 建待办）")
    print("=" * 70)
    result = ReActAgent(MockLLM()).run("查一下笔记里关于部署的记录，再建个待办")
    print_result("查一下笔记里关于部署的记录，再建个待办", result)
    actions = [s["action"] for s in result["steps"] if s["action"]]
    checks.append(_check("两工具串联",
                         actions == ["search_notes", "create_todo"] and result["stopped"] == "final"))

    print("=" * 70)
    print("用例 4：工具抛异常，模型自行处理")
    print("=" * 70)
    result = ReActAgent(MockLLM()).run("火星天气怎么样")
    print_result("火星天气怎么样", result)
    checks.append(_check("工具报错可自愈",
                         result["stopped"] == "final" and "失败" in result["answer"]))

    print("=" * 70)
    print("用例 5：模型输出格式错误，靠纠正消息恢复")
    print("=" * 70)
    result = ReActAgent(MockLLM(faults={1: "malformed"})).run("北京天气如何")
    print_result("北京天气如何（第 1 轮注入格式错误）", result)
    checks.append(_check("格式错误可恢复",
                         any(s["action"] == "get_weather" for s in result["steps"])
                         and result["stopped"] == "final"))

    print("=" * 70)
    print("用例 6：陷入重复循环，被 max_steps 终止")
    print("=" * 70)
    result = ReActAgent(MockLLM(loop=True), max_steps=4).run("北京天气如何")
    print_result("北京天气如何（模型只会重复同一动作）", result)
    checks.append(_check("循环可被上限终止",
                         result["stopped"] == "max_steps" and len(result["steps"]) == 4))

    print("=" * 70)
    print(f"{sum(checks)}/{len(checks)} 用例通过")
    return 0 if all(checks) else 1


def main(argv: list[str]) -> int:
    live = "--live" in argv
    args = [item for item in argv[1:] if not item.startswith("--")]

    if not args:
        return self_test()

    question = " ".join(args)
    if live:
        if not os.getenv("OPENAI_API_KEY"):
            print("使用 --live 前需要设置 OPENAI_API_KEY", file=sys.stderr)
            return 2
        llm: Callable[[list[dict]], str] = OpenAICompatLLM()
    else:
        llm = MockLLM()

    print_result(question, ReActAgent(llm).run(question))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
