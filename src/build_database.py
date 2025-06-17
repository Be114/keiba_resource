"""
競馬データ収集ツール

netkeiba.comから指定された期間のレース情報を取得し、データベースに保存するツール。
このモジュールは、スクレイピング機能とデータベース操作を組み合わせたデータ収集パイプラインを提供します。
"""

import argparse
import time
from datetime import datetime
from typing import List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter


class DataScraper:
    """
    netkeiba.comからレース情報を取得するデータスクレイパー
    
    指定された期間のレースIDを取得し、詳細情報をスクレイピングする機能を提供します。
    """
    
    # サイトへの負荷を考慮したリクエスト間隔（秒）
    TIME_SLEEP = 1
    
    # netkeiba.comのベースURL
    BASE_URL = "https://race.netkeiba.com"
    
    def __init__(self, start_year: int, end_year: int):
        """
        データスクレイパーを初期化
        
        Args:
            start_year: 取得開始年
            end_year: 取得終了年
        """
        self.start_year = start_year
        self.end_year = end_year
        self.session = self._create_session()
    
    def _create_session(self) -> requests.Session:
        """
        リトライ機能付きのHTTPセッションを作成
        
        Returns:
            設定済みのrequests.Sessionオブジェクト
        """
        session = requests.Session()
        
        # リトライ戦略の設定
        retry_strategy = Retry(
            total=3,  # 最大3回リトライ
            status_forcelist=[500, 502, 503, 504],  # 5xx系エラーでリトライ
            backoff_factor=2,  # 指数バックオフ（2秒、4秒、8秒）
            raise_on_status=False
        )
        
        # HTTPアダプターにリトライ戦略を適用
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        # User-Agentを設定（礼儀正しいスクレイピング）
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        return session
    
    def _generate_calendar_url(self, year: int, month: int) -> str:
        """
        指定された年月のカレンダーページURLを生成
        
        Args:
            year: 年
            month: 月
            
        Returns:
            カレンダーページのURL
        """
        return f"{self.BASE_URL}/top/calendar.html?year={year}&month={month:02d}"
    
    def _fetch_race_ids_from_month(self, year: int, month: int) -> List[str]:
        """
        指定された年月のレースIDを取得
        
        Args:
            year: 年
            month: 月
            
        Returns:
            レースIDのリスト
        """
        url = self._generate_calendar_url(year, month)
        race_ids = []
        
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'lxml')
            
            # レースリンクを抽出（netkeiba.comのHTML構造に依存）
            # 一般的なパターン: /race/xxxxxxxx/ の形式のリンク
            race_links = soup.find_all('a', href=True)
            
            for link in race_links:
                href = link.get('href', '')
                if '/race/' in href and href.count('/') >= 3:
                    # URLからレースIDを抽出
                    # 例: /race/202312345/ → 202312345
                    parts = href.strip('/').split('/')
                    if len(parts) >= 2 and parts[0] == 'race':
                        race_id = parts[1]
                        if race_id.isdigit() and len(race_id) >= 8:
                            race_ids.append(race_id)
            
            # 重複を除去
            race_ids = list(set(race_ids))
            
        except requests.RequestException as e:
            print(f"Error fetching data for {year}-{month:02d}: {e}")
        except Exception as e:
            print(f"Unexpected error for {year}-{month:02d}: {e}")
        
        return race_ids
    
    def run(self) -> None:
        """
        指定された期間のレースIDを取得するメイン処理
        """
        print(f"データ収集開始: {self.start_year}年 - {self.end_year}年")
        print(f"対象期間: {self.start_year}年1月 - {self.end_year}年12月")
        
        total_months = (self.end_year - self.start_year + 1) * 12
        all_race_ids = []
        
        # 進捗バーの設定
        with tqdm(total=total_months, desc="レースID取得中") as pbar:
            for year in range(self.start_year, self.end_year + 1):
                for month in range(1, 13):
                    # 月ごとのレースID取得
                    race_ids = self._fetch_race_ids_from_month(year, month)
                    all_race_ids.extend(race_ids)
                    
                    # 進捗表示
                    pbar.set_postfix({
                        '年月': f'{year}-{month:02d}',
                        '取得数': len(race_ids),
                        '累計': len(all_race_ids)
                    })
                    pbar.update(1)
                    
                    # サイトへの負荷軽減
                    time.sleep(self.TIME_SLEEP)
        
        # 結果の表示
        print(f"\n取得完了!")
        print(f"総レース数: {len(all_race_ids)}")
        
        # 年別の統計表示
        year_stats = {}
        for race_id in all_race_ids:
            if len(race_id) >= 4:
                year = race_id[:4]
                year_stats[year] = year_stats.get(year, 0) + 1
        
        print("\n年別統計:")
        for year in sorted(year_stats.keys()):
            print(f"  {year}年: {year_stats[year]}レース")
        
        # サンプルレースIDの表示（最初の10件）
        if all_race_ids:
            print(f"\nサンプルレースID（最初の10件）:")
            for i, race_id in enumerate(all_race_ids[:10], 1):
                print(f"  {i:2d}. {race_id}")
        
        print("\n注意: この段階ではレースIDの取得のみを行いました。")
        print("詳細情報の取得とデータベース保存は次のフェーズで実装予定です。")


def main() -> None:
    """
    メイン関数：コマンドライン引数を解析してデータ収集を実行
    """
    parser = argparse.ArgumentParser(
        description="netkeiba.comから競馬データを収集するツール",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  python build_database.py --start-year 2023 --end-year 2024
  python build_database.py --start-year 2022 --end-year 2022
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
    
    args = parser.parse_args()
    
    # 引数の妥当性チェック
    current_year = datetime.now().year
    
    if args.start_year > args.end_year:
        parser.error("開始年は終了年以下である必要があります")
    
    if args.start_year < 2000:
        parser.error("開始年は2000年以降である必要があります")
    
    if args.end_year > current_year:
        parser.error(f"終了年は現在年（{current_year}年）以下である必要があります")
    
    # データスクレイパーの実行
    scraper = DataScraper(args.start_year, args.end_year)
    scraper.run()


if __name__ == "__main__":
    main()