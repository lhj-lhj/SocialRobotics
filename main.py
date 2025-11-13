"""主入口：控制要不要 plan"""
import sys
import os

# 添加项目根目录到路径（必须在导入之前）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncio
import argparse
from connection.furhat_bridge import FurhatBridge
from utils.print_utils import cprint


async def _run_bridge(bridge: FurhatBridge):
    """异步运行桥接器"""
    await bridge.run()


def main():
    """主函数：控制是否使用 plan 模块"""
    parser = argparse.ArgumentParser(description="Furhat 机器人对话系统")
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
        help="Realtime API 的认证密钥"
    )
    parser.add_argument(
        "--no-plan",
        action="store_true",
        help="不使用 plan 模块（仅用于调试）"
    )
    args = parser.parse_args()

    try:
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
