"""
LangGraph ReAct 最小 Demo —— 带计算器的 Agent

完整演示标准 ReAct 循环：
    思考 Reason -> 行动 Act(调用工具) -> 观察 Observe -> 循环 -> 最终答案

运行：
    .venv/bin/python react_agent.py

说明：
    默认使用「脚本化假模型」离线运行，无需任何 API Key，直接跑通整个循环。
    要接真实大模型（OpenAI 兼容接口），见文件末尾的替换说明。
"""
from typing import Annotated

import math
from typing_extensions import TypedDict

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

# ============================================================
# 1. 工具：一个安全的计算器
# ============================================================
_SAFE_NS = {
    "__builtins__": {},
    "abs": abs, "round": round, "min": min, "max": max,
    "pow": pow, "sum": sum,
    "sqrt": math.sqrt, "sin": math.sin, "cos": math.cos,
    "tan": math.tan, "log": math.log, "pi": math.pi, "e": math.e,
}


@tool
def calculator(expression: str) -> str:
    """计算一个数学表达式，例如 '3 * (4 + 5)' 或 'sqrt(16) * 2'。

    Args:
        expression: 合法的数学表达式字符串。
    """
    try:
        result = eval(expression, _SAFE_NS, {})
        return f"{expression} = {result}"
    except Exception as e:
        return f"表达式 '{expression}' 计算失败：{e}"


# ============================================================
# 2. State：共享状态，messages 用 add_messages 自动累积
# ============================================================
class State(TypedDict):
    messages: Annotated[list, add_messages]


# ============================================================
# 3. 模型：离线用「脚本化假模型」，模拟 LLM 的两轮推理
#    - 第 1 轮：思考后决定调用计算器
#    - 第 2 轮：看到观察结果后给出最终答案
# ============================================================
model = FakeMessagesListChatModel(responses=[
    AIMessage(
        content="",
        tool_calls=[{
            "name": "calculator",
            "args": {"expression": "3 * (4 + 5)"},
            "id": "call_1",
            "type": "tool_call",
        }],
    ),
    AIMessage(content="3 * (4 + 5) = 27，结果是 27。"),
])


# ============================================================
# 4. 节点：思考 + 行动/观察
# ============================================================
def agent_node(state: State):
    """思考节点：让模型决定调用工具 or 给出最终答案。"""
    return {"messages": [model.invoke(state["messages"])]}


# tools 节点：LangGraph 内置 ToolNode，自动执行 tool_calls 并返回观察结果
tools_node = ToolNode([calculator])


# ============================================================
# 5. 条件边：有 tool_calls -> 继续调工具；否则 -> 结束
# ============================================================
def route(state: State) -> str:
    last = state["messages"][-1]
    return "tools" if getattr(last, "tool_calls", None) else END


# ============================================================
# 6. 组装图
# ============================================================
builder = StateGraph(State)
builder.add_node("agent", agent_node)
builder.add_node("tools", tools_node)
builder.add_edge(START, "agent")
builder.add_conditional_edges("agent", route, {"tools": "tools", END: END})
builder.add_edge("tools", "agent")   # 观察完 -> 回到思考，形成循环
graph = builder.compile()


# ============================================================
# 7. 运行
# ============================================================
if __name__ == "__main__":
    question = "帮我算一下 3 * (4 + 5) 等于多少？"
    result = graph.invoke({"messages": [HumanMessage(content=question)]})

    print("=" * 46)
    print("ReAct 完整轨迹")
    print("=" * 46)
    for m in result["messages"]:
        if isinstance(m, HumanMessage):
            print(f"\n[用户]         {m.content}")
        elif isinstance(m, AIMessage):
            if m.tool_calls:
                tc = m.tool_calls[0]
                print(f"\n[思考→行动]   调用工具 {tc['name']}({tc['args']})")
            else:
                print(f"\n[思考→答案]   {m.content}")
        elif isinstance(m, ToolMessage):
            print(f"[观察]        {m.content}")
    print()
