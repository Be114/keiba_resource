#!/usr/bin/env python3
"""
競馬データ収集ツールのエントリーポイント

netkeiba.comまたはkeibalab.jpから競馬データを収集し、データベースに保存します。
"""

import argparse
from datetime import datetime


def main() -> None:
    """
    メイン関数：コマンドライン引数を解析してデータ収集を実行
    """
    parser = argparse.ArgumentParser(
        description="競馬データを収集するツール（netkeiba.com / keibalab.jp対応）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # netkeiba.comから取得（デフォルト）
  python scrape_races.py --start-year 2023 --end-year 2024
  
  # keibalab.jpから取得
  python scrape_races.py --start-year 2020 --end-year 2021 --scraper-type keibalab
        """
    )
    
    parser.add_argument(
        '--start-year', 
        type=int, 
        required=True,
        help='データ取得開始年（例: 2023）'
    )
    
    parser.add_argument(
        '--end-year', 
        type=int, 
        required=True,
        help='データ取得終了年（例: 2024）'
    )
    
    parser.add_argument(
        '--scraper-type',
        type=str,
        choices=['netkeiba', 'keibalab'],
        default='keibalab',  # デフォルトをkeibalabに変更（より安定している）
        help='使用するスクレイパーのタイプ（デフォルト: keibalab）'
    )
    
    args = parser.parse_args()
    
    # 引数の妥当性チェック
    current_year = datetime.now().year
    
    if args.start_year > args.end_year:
        parser.error("開始年は終了年以下である必要があります")
    
    # スクレイパータイプ別の制約
    if args.scraper_type == 'netkeiba':
        if args.start_year < 2000:
            parser.error("netkeiba: 開始年は2000年以降である必要があります")
        print("注意: netkeiba.comのスクレイピングはSeleniumを使用するため、時間がかかります。")
    elif args.scraper_type == 'keibalab':
        if args.start_year < 2014:
            print(f"Warning: keibalab.jpは2014年以降のデータのみ提供しています。")
    
    if args.end_year > current_year:
        parser.error(f"終了年は現在年（{current_year}年）以下である必要があります")
    
    # スクレイパーの選択と実行
    if args.scraper_type == 'netkeiba':
        from src.build_database import DataScraper
        scraper = DataScraper(args.start_year, args.end_year)
    else:  # keibalab
        from src.keibalab_scraper import KeibalabScraper
        scraper = KeibalabScraper(args.start_year, args.end_year)
    
    print(f"使用するスクレイパー: {args.scraper_type}")
    scraper.run()


if __name__ == "__main__":
    main()