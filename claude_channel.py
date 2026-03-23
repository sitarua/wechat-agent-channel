import sys

from wechat_agent.claude_channel_app import main


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit(0)
    except Exception as err:
        print(f"错误: {err}", file=sys.stderr)
        raise SystemExit(1)
