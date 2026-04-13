#!/usr/bin/env python3
"""
爬蟲主程式入口。

使用方式：
    python main.py                           # 使用預設設定
    python main.py --config my_site.yaml     # 指定設定檔
    python main.py -c crawler/config/default.yaml
"""

import argparse
import sys

from crawler.runner import run


def main():
    parser = argparse.ArgumentParser(
        description="可設定式網頁爬蟲",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例：
  python main.py                                  使用預設設定執行
  python main.py -c my_site.yaml                  指定設定檔
  CRAWLER_ENGINE_TIMEOUT=60 python main.py        透過環境變數覆寫設定
        """,
    )
    parser.add_argument(
        "-c", "--config",
        help="YAML 設定檔路徑",
        default=None,
    )
    args = parser.parse_args()

    try:
        results = run(args.config)
        print(f"\n完成！共取得 {len(results) if results else 0} 筆資料。")
    except FileNotFoundError as e:
        print(f"錯誤: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n使用者中斷執行")
        sys.exit(0)
    except Exception as e:
        print(f"執行錯誤: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
