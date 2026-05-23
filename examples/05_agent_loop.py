"""Drive AutoControl's closed-loop agent against a scripted fake backend.

To use a real LLM, replace ``FakeAgentBackend`` with one of the production
backends — see ``je_auto_control.utils.agent.backends`` for the
Anthropic and OpenAI implementations. Both need their respective SDK
plus an API key in the environment.
"""
from je_auto_control.utils.agent.agent_loop import (
    AgentBudget, AgentLoop, FakeAgentBackend,
)


def main() -> None:
    # Each dict is one decision in the agent's observe→act loop.
    # The last entry must include ``stop`` or the loop runs to ``max_steps``.
    backend = FakeAgentBackend([
        {"tool": "AC_screenshot", "input": {"file_path": "step1.png"}},
        {"tool": "AC_click_mouse", "input": {
            "mouse_keycode": "mouse_left", "x": 100, "y": 200,
        }},
        {"stop": True, "message": "done — closed the dialog"},
    ])

    # Trivial tool runner that prints what the agent decided. In real
    # usage, omit ``tool_runner=`` and the executor's AC_* dispatch is
    # used.
    def runner(tool, args):
        print(f"  → {tool}({args})")
        return {"ok": True}

    loop = AgentLoop(
        backend,
        tool_runner=runner,
        screenshot_fn=lambda: None,
        budget=AgentBudget(max_steps=10, wall_seconds=30.0),
    )
    result = loop.run("close the modal and take a screenshot")
    print(f"succeeded={result.succeeded} steps={len(result.steps)} "
          f"elapsed={result.elapsed_s:.2f}s message={result.final_message!r}")


if __name__ == "__main__":
    main()
