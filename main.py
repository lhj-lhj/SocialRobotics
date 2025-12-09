"""Main entry point controlling whether to use the planning module."""
import sys
import os

# Add project root to sys.path before importing local modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncio
import argparse
from connection.furhat_bridge import FurhatBridge
from utils.print_utils import cprint
from plan.orchestrator import Orchestrator


async def _run_bridge(bridge: FurhatBridge):
    """Run the bridge event loop asynchronously."""
    await bridge.run()


def main():
    """Main function: optionally run without the planning module or in test mode."""
    parser = argparse.ArgumentParser(description="Furhat dialogue system")
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Furhat robot IP address"
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
        "--replay-only",
        action="store_true",
        help="Replay stored answers only (no controller/reasoning model calls)"
    )
    args = parser.parse_args()

    if args.test:
        question = input("Test question (press Enter to use default): ").strip() or "How do you show thinking?"
        cprint("Test mode: running language and thinking pipeline only")
        orchestrator = Orchestrator(question, replay_only=args.replay_only)
        try:
            asyncio.run(orchestrator.run())
        except KeyboardInterrupt:
            cprint("\nTest interrupted by user")
        except RuntimeError as err:
            cprint(f"Configuration error: {err}")
        except Exception as err:
            cprint(f"Unexpected error: {err}")
            import traceback
            traceback.print_exc()
        return

    try:
        # Create the Furhat bridge
        bridge = FurhatBridge(host=args.host, auth_key=args.auth_key, replay_only=args.replay_only)
        
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
