"""Explicit service entry point; no native target is operated during startup."""
import argparse

from je_auto_control.utils.agent_runtime.service import AgentRuntimeService


def main() -> None:
    """Run a local service until its process receives an explicit stop signal."""
    parser = argparse.ArgumentParser(description="AutoControl managed task runtime")
    parser.add_argument("command", choices=["serve"])
    parser.add_argument("--directory", required=True)
    arguments = parser.parse_args()
    service = AgentRuntimeService(arguments.directory)
    try:
        service.start()
        service.wait()
    except KeyboardInterrupt:
        pass
    finally:
        service.close()


if __name__ == "__main__":
    main()
