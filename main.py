"""主入口：控制要不要 plan"""
import sys
import os

# 添加项目根目录到路径（必须在导入之前）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncio
import argparse

from connection.furhat_bridge import FurhatBridge
from plan.behavior_generator import BehaviorGenerator
from plan import Orchestrator
from utils.print_utils import cprint


async def _run_bridge(bridge: FurhatBridge):
    """异步运行桥接器"""
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
    """主函数：控制是否使用 plan 模块"""
    parser = argparse.ArgumentParser(description="Furhat 机器人对话系统")
    parser.add_argument(
        "--host",
        type=str,
        default="192.168.1.110",
        help="Furhat 机器人 IP 地址"
    )
    parser.add_argument(
        "--auth_key",
        type=str,
        default=None,
        help="Realtime API 的认证密钥"
    )
    parser.add_argument(
        "--no-plan",
        action="store_true",
        help="不使用 plan 模块（仅用于调试）"
    )
    parser.add_argument(
        "--local-test",
        action="store_true",
        help="本地测试模式，不连接 Furhat，只写日志"
    )
    args = parser.parse_args()

    try:
        if args.local_test:
            asyncio.run(_run_local_test())
            return

        # 创建连接桥接器
        bridge = FurhatBridge(host=args.host, auth_key=args.auth_key)
        
        if args.no_plan:
            cprint("警告：未使用 plan 模块，仅连接模式")
            # 可以在这里添加不使用 plan 的逻辑
        
        # 运行主循环
        asyncio.run(_run_bridge(bridge))
        
    except KeyboardInterrupt:
        cprint("\n程序被用户中断")
    except RuntimeError as err:
        cprint(f"配置错误：{err}")
    except Exception as err:
        cprint(f"未预期的错误：{err}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
