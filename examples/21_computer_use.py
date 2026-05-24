"""Drive Anthropic Computer-Use against the live screen.

Requires:

* ``pip install je_auto_control[agent]`` (or just ``anthropic``);
* ``ANTHROPIC_API_KEY`` in the environment.

The single :func:`run_computer_use` call wires together:

* :class:`ComputerUseAgentBackend` — Anthropic's official
  ``computer_20250124`` tool with proper system prompt and screenshot
  attachment, so the model uses its trained behaviour;
* :class:`AgentLoop` — observe → decide → execute → loop, with budget
  guards so a runaway call can't drain the API;
* the standard AC_* tool dispatch — every action the model issues is
  translated to the matching wrapper call and executed locally.

For programmatic use the same wrapper is also exposed as the
``AC_computer_use`` executor command (JSON action files / scheduler /
triggers / REST) and the ``ac_computer_use`` MCP tool (Claude Desktop
/ Claude Code).
"""
import os

from je_auto_control import run_computer_use


def main() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY not set — skipping live run.")
        return

    result = run_computer_use(
        "open the Calculator app, compute 12 * 7, then take a screenshot",
        max_steps=15,
        wall_seconds=120.0,
    )
    print(f"succeeded={result.succeeded} steps={len(result.steps)}"
          f" elapsed={result.elapsed_s:.2f}s")
    print("final message:", result.final_message)
    for step in result.steps:
        head = f"  [{step.index}]"
        if step.tool:
            print(f"{head} {step.tool}({step.arguments})"
                  f"{' ! ' + step.error if step.error else ''}")
        else:
            print(f"{head} stop: {step.stop_reason}")


if __name__ == "__main__":
    main()
