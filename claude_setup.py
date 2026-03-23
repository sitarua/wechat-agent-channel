import sys

from wechat_agent.setup_flow import main


if __name__ == "__main__":
    try:
        main(select_provider=False)
    except KeyboardInterrupt:
        print("\n已取消。")
        raise SystemExit(1)
    except Exception as err:
        print(f"错误: {err}", file=sys.stderr)
        raise SystemExit(1)
