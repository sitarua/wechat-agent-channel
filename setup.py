import argparse
import sys

from wechat_agent.setup_flow import main


if __name__ == "__main__":
    try:
        parser = argparse.ArgumentParser(description="Set up WeChat login and default provider.")
        parser.add_argument(
            "--reset-provider",
            action="store_true",
            help="Prompt to choose the default provider again even if one is already saved.",
        )
        args = parser.parse_args()
        main(reset_provider=args.reset_provider, select_provider=True)
    except KeyboardInterrupt:
        print("\n已取消。")
        raise SystemExit(1)
    except Exception as err:
        print(f"错误: {err}", file=sys.stderr)
        raise SystemExit(1)
