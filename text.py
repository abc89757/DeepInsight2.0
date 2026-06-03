from services.tool_call_store import load_tool_calls
from graph.nodes.ChartGeneratorNode import ChartGeneratorNode

state = {
    "task_id" : "b5c44a47efc949e2ae139f67acebfd0a"
}

ans = load_tool_calls(state.get("task_id"),"chart_generator")

for i in ans:
    print(i)

# print(ans)