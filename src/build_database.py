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

from src.db_utils import DatabaseManager
from src.models import Race, Result


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
    
    # レースメタデータ抽出用の正規表現パターン
    DISTANCE_PATTERN = re.compile(r'(\d+)m')
    TRACK_TYPE_PATTERN = re.compile(r'(芝|ダート|障害)')
    WEATHER_PATTERN = re.compile(r'天候\s*:\s*(\S+)')
    TRACK_CONDITION_PATTERN = re.compile(r'馬場\s*:\s*(\S+)')
    RACE_NAME_PATTERN = re.compile(r'race_name.*?>([^<]+)</)
    
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
    
    def _scrape_race_metadata(self, soup: BeautifulSoup) -> dict:
        """
        レースページのHTMLからメタデータを抽出
        
        Args:
            soup: BeautifulSoupオブジェクト（レースページのHTML）
            
        Returns:
            レースメタデータを含む辞書
        """
        metadata = {
            'race_name': None,
            'distance': None,
            'track_type': None,
            'weather': None,
            'track_condition': None,
            'course': None
        }
        
        try:
            # レース名を抽出
            race_name_elem = soup.find('h1')
            if race_name_elem:
                metadata['race_name'] = race_name_elem.get_text(strip=True)
            
            # コース情報（開催場所）を抽出
            # 一般的に「阪神」「東京」などが含まれる要素を探す
            course_candidates = soup.find_all(['p', 'div', 'span'], 
                                            text=re.compile(r'(東京|中山|阪神|京都|中京|新潟|小倉|函館|札幌|福島)'))
            if course_candidates:
                course_text = course_candidates[0].get_text(strip=True)
                # 開催場所名を抽出
                course_match = re.search(r'(東京|中山|阪神|京都|中京|新潟|小倉|函館|札幌|福島)', course_text)
                if course_match:
                    metadata['course'] = course_match.group(1)
            
            # レース条件を含むテキストを検索
            # netkeiba.comでは通常「芝1600m」のような表記が使われる
            race_info_text = soup.get_text()
            
            # 距離を抽出
            distance_match = self.DISTANCE_PATTERN.search(race_info_text)
            if distance_match:
                metadata['distance'] = int(distance_match.group(1))
            
            # コース種別（芝/ダート/障害）を抽出
            track_type_match = self.TRACK_TYPE_PATTERN.search(race_info_text)
            if track_type_match:
                metadata['track_type'] = track_type_match.group(1)
            
            # 天候を抽出
            weather_match = self.WEATHER_PATTERN.search(race_info_text)
            if weather_match:
                metadata['weather'] = weather_match.group(1)
            
            # 馬場状態を抽出
            track_condition_match = self.TRACK_CONDITION_PATTERN.search(race_info_text)
            if track_condition_match:
                metadata['track_condition'] = track_condition_match.group(1)
            
            # より具体的な要素を探す
            # レース条件を含む特定のクラスや要素を探す
            race_data_elements = soup.find_all(['td', 'th', 'span', 'div'], 
                                              text=re.compile(r'(芝|ダート|障害).*(\d+)m'))
            
            if race_data_elements:
                for elem in race_data_elements:
                    text = elem.get_text(strip=True)
                    # より詳細な距離とコース種別の抽出
                    detailed_match = re.search(r'(芝|ダート|障害)\s*(\d+)', text)
                    if detailed_match:
                        if not metadata['track_type']:
                            metadata['track_type'] = detailed_match.group(1)
                        if not metadata['distance']:
                            metadata['distance'] = int(detailed_match.group(2))
                        break
            
        except Exception as e:
            print(f"Error extracting race metadata: {e}")
        
        return metadata
    
    def _scrape_race_results(self, race_id: str) -> Optional[tuple[pd.DataFrame, dict]]:
        """
        指定されたレースIDの結果データとメタデータをスクレイピング
        
        Args:
            race_id: レースの一意識別子
            
        Returns:
            (レース結果のDataFrame, レースメタデータの辞書) のタプル。取得に失敗した場合はNone
        """
        url = f"https://db.netkeiba.com/race/{race_id}/"
        
        try:
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            
            # BeautifulSoupオブジェクトを作成してメタデータを抽出
            soup = BeautifulSoup(response.content, 'lxml')
            metadata = self._scrape_race_metadata(soup)
            
            # pandas.read_html()を使用してテーブルデータを抽出
            tables = pd.read_html(response.content)
            
            if not tables:
                print(f"No tables found for race {race_id}")
                return None
            
            # 通常、レース結果は最初のテーブルに含まれる
            results_df = tables[0]
            
            # データクレンジング: 不要な列を削除し、データ型を調整
            # 基本的なクレンジング
            # 数値列の処理
            numeric_columns = ['着順', '人気', '単勝', '斤量']
            for col in numeric_columns:
                if col in results_df.columns:
                    # "---"や空文字列をNaNに変換
                    results_df[col] = results_df[col].replace(['---', '', '除外', '中止', '取消'], pd.NA)
                    # 数値型に変換を試行
                    results_df[col] = pd.to_numeric(results_df[col], errors='coerce')
            
            # 文字列列の処理
            string_columns = ['馬名', '騎手']
            for col in string_columns:
                if col in results_df.columns:
                    results_df[col] = results_df[col].fillna('').astype(str)
            
            # 最小限の列数チェック
            if len(results_df.columns) > 5:  # 最小限の列数チェック
                # race_idを追加
                results_df['race_id'] = race_id
                return (results_df, metadata)
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
                # 安全な型変換
                rank = int(row.get('着順', 0)) if pd.notna(row.get('着順', 0)) else 0
                pre_race_rank = int(row.get('人気', 0)) if pd.notna(row.get('人気', 0)) else 0
                odds = float(row.get('単勝', 0.0)) if pd.notna(row.get('単勝', 0.0)) else 0.0
                weight = float(row.get('斤量', 0.0)) if pd.notna(row.get('斤量', 0.0)) else 0.0
                
                result = Result(
                    race_id=race.id,
                    horse_name=row.get('馬名', ''),
                    rank=rank,
                    pre_race_rank=pre_race_rank,
                    jockey_name=row.get('騎手', ''),
                    odds=odds,
                    weight=weight
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
                    # レース結果とメタデータをスクレイピング
                    result = self._scrape_race_results(race_id)
                    
                    if result is not None:
                        results_df, metadata = result
                        
                        # スクレイピングしたメタデータを使用してレース情報を作成
                        race_info = {
                            'id': race_id,
                            'date': datetime.strptime(race_id[:8], '%Y%m%d').date(),
                            'course': metadata.get('course') or 'Unknown',
                            'race_number': int(race_id[8:10]) if len(race_id) >= 10 else 1,
                            'distance': metadata.get('distance') or 1600,
                            'track_type': metadata.get('track_type') or '芝',
                            'weather': metadata.get('weather'),
                            'track_condition': metadata.get('track_condition')
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