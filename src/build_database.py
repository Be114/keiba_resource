"""
競馬データ収集ツール

netkeiba.comから指定された期間のレース情報を取得し、データベースに保存するツール。
このモジュールは、スクレイピング機能とデータベース操作を組み合わせたデータ収集パイプラインを提供します。
"""

import argparse
import re
import time
from datetime import datetime, date
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup
from tqdm import tqdm
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
from sqlalchemy.exc import IntegrityError

from .db_utils import DatabaseManager
from .models import Race, Result


class DataScraper:
    """
    netkeiba.comからレース情報を取得するデータスクレイパー
    
    指定された期間のレースIDを取得し、詳細情報をスクレイピングする機能を提供します。
    """
    
    # サイトへの負荷を考慮したリクエスト間隔（秒）
    TIME_SLEEP = 1
    
    # netkeiba.comのベースURL
    BASE_URL = "https://race.netkeiba.com"
    
    # レースID抽出用の正規表現パターン
    RACE_ID_PATTERN = re.compile(r'/race/(\d{8,})')
    
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
        self.db_manager = DatabaseManager()
        # データベーステーブルを作成
        self.db_manager.create_tables()
    
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
                match = self.RACE_ID_PATTERN.search(href)
                if match:
                    race_id = match.group(1)
                    race_ids.append(race_id)
            
            # 重複を除去
            race_ids = list(set(race_ids))
            
        except requests.RequestException as e:
            print(f"Error fetching data for {year}-{month:02d}: {e}")
        except Exception as e:
            print(f"Unexpected error for {year}-{month:02d}: {e}")
        
        return race_ids
    
    def _scrape_race_results(self, race_id: str) -> Optional[pd.DataFrame]:
        """
        指定されたレースIDの結果データをスクレイピング
        
        Args:
            race_id: レースの一意識別子
            
        Returns:
            レース結果のDataFrame。取得に失敗した場合はNone
        """
        url = f"https://db.netkeiba.com/race/{race_id}/"
        
        try:
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            
            # pandas.read_html()を使用してテーブルデータを抽出
            tables = pd.read_html(response.content)
            
            if not tables:
                print(f"No tables found for race {race_id}")
                return None
            
            # 通常、レース結果は最初のテーブルに含まれる
            results_df = tables[0]
            
            # データクレンジング: 不要な列を削除し、データ型を調整
            # netkeiba.comの構造に依存するため、実際のHTML構造に合わせて調整が必要
            if len(results_df.columns) > 10:  # 最小限の列数チェック
                # race_idを追加
                results_df['race_id'] = race_id
                return results_df
            else:
                print(f"Insufficient columns in race {race_id}")
                return None
                
        except requests.RequestException as e:
            print(f"Error fetching race {race_id}: {e}")
            return None
        except ValueError as e:
            print(f"Error parsing HTML tables for race {race_id}: {e}")
            return None
        except Exception as e:
            print(f"Unexpected error for race {race_id}: {e}")
            return None
    
    def _save_data_to_db(self, race_info: Dict[str, Any], results_df: pd.DataFrame) -> bool:
        """
        レース情報と結果をデータベースに保存
        
        Args:
            race_info: レース基本情報の辞書
            results_df: レース結果のDataFrame
            
        Returns:
            保存が成功した場合True、失敗した場合False
        """
        session = self.db_manager.get_session()
        
        try:
            # 重複チェック: 既存のレースIDをチェック
            existing_race = session.query(Race).filter(Race.id == race_info['id']).first()
            if existing_race:
                print(f"Race {race_info['id']} already exists, skipping...")
                return True
            
            # Raceオブジェクトを作成
            race = Race(
                id=race_info['id'],
                date=race_info['date'],
                course=race_info['course'],
                race_number=race_info['race_number'],
                distance=race_info['distance'],
                track_type=race_info['track_type'],
                weather=race_info.get('weather'),
                track_condition=race_info.get('track_condition')
            )
            
            session.add(race)
            session.flush()  # raceのIDを取得するためにflush
            
            # Resultオブジェクトのリストを作成
            results = []
            for _, row in results_df.iterrows():
                result = Result(
                    race_id=race.id,
                    finish_position=row.get('着順', 0),
                    horse_number=row.get('馬番', 0),
                    horse_name=row.get('馬名', ''),
                    jockey_name=row.get('騎手', ''),
                    trainer_name=row.get('調教師', ''),
                    odds=row.get('単勝', 0.0),
                    popularity=row.get('人気', 0),
                    finish_time=row.get('タイム', '')
                )
                results.append(result)
            
            # 一括でResultを保存
            session.add_all(results)
            session.commit()
            
            return True
            
        except IntegrityError as e:
            session.rollback()
            print(f"Database integrity error for race {race_info['id']}: {e}")
            return False
        except Exception as e:
            session.rollback()
            print(f"Database error for race {race_info['id']}: {e}")
            return False
        finally:
            session.close()
    
    def run(self) -> None:
        """
        指定された期間のレースIDを取得するメイン処理
        """
        print(f"データ収集開始: {self.start_year}年 - {self.end_year}年")
        print(f"対象期間: {self.start_year}年1月 - {self.end_year}年12月")
        
        total_months = (self.end_year - self.start_year + 1) * 12
        all_race_ids: set[str] = set()
        
        # 進捗バーの設定
        with tqdm(total=total_months, desc="レースID取得中") as pbar:
            for year in range(self.start_year, self.end_year + 1):
                for month in range(1, 13):
                    # 月ごとのレースID取得
                    race_ids = self._fetch_race_ids_from_month(year, month)
                    all_race_ids.update(race_ids)
                    
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
            for i, race_id in enumerate(list(all_race_ids)[:10], 1):
                print(f"  {i:2d}. {race_id}")
        
        # レース詳細データの取得とデータベース保存
        print(f"\nレース詳細データの取得を開始します...")
        successful_saves = 0
        failed_saves = 0
        
        race_id_list = list(all_race_ids)
        
        with tqdm(total=len(race_id_list), desc="レースデータ取得・保存中") as pbar:
            for race_id in race_id_list:
                try:
                    # レース結果をスクレイピング
                    results_df = self._scrape_race_results(race_id)
                    
                    if results_df is not None:
                        # race_idから基本的なレース情報を作成（簡易版）
                        # 実際の実装では、レースページからより詳細な情報を抽出する必要がある
                        race_info = {
                            'id': int(race_id),
                            'date': datetime.strptime(race_id[:8], '%Y%m%d').date(),
                            'course': 'Unknown',  # HTMLパースで取得する必要がある
                            'race_number': int(race_id[8:10]) if len(race_id) >= 10 else 1,
                            'distance': 1600,  # デフォルト値、HTMLパースで取得する必要がある
                            'track_type': '芝',  # デフォルト値、HTMLパースで取得する必要がある
                            'weather': None,
                            'track_condition': None
                        }
                        
                        # データベースに保存
                        if self._save_data_to_db(race_info, results_df):
                            successful_saves += 1
                        else:
                            failed_saves += 1
                    else:
                        failed_saves += 1
                        
                except Exception as e:
                    print(f"\nError processing race {race_id}: {e}")
                    failed_saves += 1
                
                # 進捗更新
                pbar.set_postfix({
                    '成功': successful_saves,
                    '失敗': failed_saves,
                    '成功率': f"{successful_saves/(successful_saves+failed_saves)*100:.1f}%" if (successful_saves+failed_saves) > 0 else "0%"
                })
                pbar.update(1)
                
                # サイトへの負荷軽減
                time.sleep(self.TIME_SLEEP)
        
        # 最終結果の表示
        print(f"\n=== データ収集完了 ===")
        print(f"総レース数: {len(all_race_ids)}")
        print(f"保存成功: {successful_saves}")
        print(f"保存失敗: {failed_saves}")
        print(f"成功率: {successful_saves/(successful_saves+failed_saves)*100:.1f}%" if (successful_saves+failed_saves) > 0 else "0%")


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