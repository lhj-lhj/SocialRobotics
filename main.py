"""Main entry point controlling whether to use the planning module."""
import sys
import os

# Add project root to sys.path before importing local modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncio
import argparse

from connection.furhat_bridge import FurhatBridge
from plan.behavior_generator import BehaviorGenerator
from plan import Orchestrator
from utils.print_utils import cprint
from plan.orchestrator import Orchestrator


async def _run_bridge(bridge: FurhatBridge):
    """Run the bridge event loop asynchronously."""
    await bridge.run()


async def _run_local_test():
    """本地测试模式：不连接 Furhat，仅运行编排流程并写日志"""
    cprint("进入本地测试模式（不连接机器人）。输入问题，输入 exit/quit 退出。")
    behavior_generator = BehaviorGenerator(furhat_client=None)

    while True:
        try:
            question = input("\nYou> ").strip()
        except (EOFError, KeyboardInterrupt):
            cprint("\n退出本地测试。")
            break

        if not question:
            continue
        if question.lower() in {"exit", "quit"}:
            cprint("退出本地测试。")
            break

        orchestrator = Orchestrator(
            question,
            behavior_generator=behavior_generator,
            furhat_client=None,
        )
        await orchestrator.run()
        cprint(f"日志输出：{orchestrator.logger.log_path}")


def main():
    """Main function: optionally run without the planning module or in test mode."""
    parser = argparse.ArgumentParser(description="Furhat dialogue system")
    parser.add_argument(
        "--host",
        type=str,
        default="192.168.1.114",
        help="Furhat 机器人 IP 地址"
    )
    parser.add_argument(
        "--auth_key",
        type=str,
        default=None,
        help="Realtime API auth key"
    )
    parser.add_argument(
        "--no-plan",
        action="store_true",
        help="Skip the planning module (debug only)"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Test language/thinking only without connecting to Furhat"
    )
    parser.add_argument(
        "--local-test",
        action="store_true",
        help="本地测试模式，不连接 Furhat，只写日志"
    )
    args = parser.parse_args()

    try:
        # 创建连接桥接器
        bridge = FurhatBridge(host=args.host, auth_key=args.auth_key)
        
        if args.no_plan:
            cprint("Warning: planning module disabled (connection-only mode)")
            # Insert custom logic for no-plan mode here if needed
        
        # Run the main event loop
        asyncio.run(_run_bridge(bridge))
        
    except KeyboardInterrupt:
        cprint("\nInterrupted by user")
    except RuntimeError as err:
        cprint(f"Configuration error: {err}")
    except Exception as err:
        cprint(f"Unexpected error: {err}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
