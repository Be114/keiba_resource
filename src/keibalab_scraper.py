"""
keibalab.jp用データ収集ツール

keibalab.jpから指定された期間のレース情報を取得し、データベースに保存するツール。
静的HTMLを利用したシンプルなスクレイピング機能を提供します。
"""

import re
import time
from datetime import datetime, timedelta, date
from typing import List, Optional, Dict, Any, Tuple
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup
from tqdm import tqdm
from sqlalchemy.exc import IntegrityError
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

from src.db_utils import DatabaseManager
from src.models import Race, Result


class KeibalabScraper:
    """
    keibalab.jpからレース情報を取得するデータスクレイパー
    
    日付ベースのURL構造を利用し、効率的にレースデータをスクレイピングします。
    """
    
    # サイトへの負荷を考慮したリクエスト間隔（秒）
    TIME_SLEEP = 1
    
    # keibalab.jpのベースURL
    BASE_URL = "https://www.keibalab.jp/db/race/"
    
    # 開催場所コードマッピング
    COURSE_CODES = {
        "札幌": "01",
        "函館": "02",
        "福島": "03",
        "新潟": "04",
        "東京": "05",
        "中山": "06",
        "中京": "07",
        "京都": "08",
        "阪神": "09",
        "小倉": "10"
    }
    
    # コースコードから開催場所への逆引き辞書
    COURSE_NAMES = {v: k for k, v in COURSE_CODES.items()}
    
    # レースメタデータ抽出用の正規表現パターン
    DISTANCE_PATTERN = re.compile(r'(\d+)m')
    TRACK_TYPE_PATTERN = re.compile(r'(芝|ダート|障害)')
    WEATHER_PATTERN = re.compile(r'天気\s*[:：]\s*(\S+)')
    TRACK_CONDITION_PATTERN = re.compile(r'馬場\s*[:：]\s*(\S+)')
    
    def __init__(self, start_year: int, end_year: int):
        """
        データスクレイパーを初期化
        
        Args:
            start_year: 取得開始年（2014年以降）
            end_year: 取得終了年
        """
        # keibalab.jpは2014年以降のデータのみ
        if start_year < 2014:
            print(f"Warning: keibalab.jp only has data from 2014 onwards. Adjusting start_year to 2014.")
            start_year = 2014
            
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
        
        # リトライ戦略を設定
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504]
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        # User-Agentを設定（礼儀正しいスクレイピング）
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        return session
    
    def _generate_date_urls(self) -> List[Tuple[date, str]]:
        """
        指定期間の全日付に対するURLリストを生成
        
        Returns:
            (日付, URL)のタプルのリスト
        """
        date_urls = []
        start_date = date(self.start_year, 1, 1)
        end_date = date(self.end_year, 12, 31)
        
        current_date = start_date
        while current_date <= end_date:
            date_str = current_date.strftime("%Y%m%d")
            url = f"{self.BASE_URL}{date_str}/"
            date_urls.append((current_date, url))
            current_date += timedelta(days=1)
        
        return date_urls
    
    def _fetch_race_ids_from_date(self, date_url: str) -> List[str]:
        """
        指定された日付ページからレースIDを取得
        
        Args:
            date_url: 日付ページのURL
            
        Returns:
            レースIDのリスト
        """
        race_ids = []
        
        try:
            response = self.session.get(date_url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'lxml')
            
            # レースへのリンクを探す（確定アイコンがあるリンク）
            race_links = soup.find_all('a', href=True)
            
            for link in race_links:
                href = link.get('href', '')
                # レースIDのパターンマッチング（14桁の数字）
                match = re.search(r'/race/(\d{14})/', href)
                if match:
                    race_id = match.group(1)
                    race_ids.append(race_id)
            
            # 重複を除去
            race_ids = list(set(race_ids))
            
        except requests.RequestException as e:
            print(f"Error fetching {date_url}: {e}")
        except Exception as e:
            print(f"Unexpected error for {date_url}: {e}")
        
        return race_ids
    
    def _extract_race_metadata(self, soup: BeautifulSoup, race_id: str) -> dict:
        """
        レースページのHTMLからメタデータを抽出
        
        Args:
            soup: BeautifulSoupオブジェクト
            race_id: レースID（開催場所コードの抽出に使用）
            
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
            # レースIDから開催場所を特定
            if len(race_id) >= 10:
                course_code = race_id[8:10]
                metadata['course'] = self.COURSE_NAMES.get(course_code, 'Unknown')
            
            # ページ全体のテキストを取得
            page_text = soup.get_text()
            
            # レース名を抽出（通常は大きなフォントサイズで表示される）
            h1_elements = soup.find_all('h1')
            if h1_elements:
                metadata['race_name'] = h1_elements[0].get_text(strip=True)
            
            # 距離を抽出
            distance_match = self.DISTANCE_PATTERN.search(page_text)
            if distance_match:
                metadata['distance'] = int(distance_match.group(1))
            
            # コース種別（芝/ダート/障害）を抽出
            track_type_match = self.TRACK_TYPE_PATTERN.search(page_text)
            if track_type_match:
                metadata['track_type'] = track_type_match.group(1)
            
            # 天候を抽出
            weather_match = self.WEATHER_PATTERN.search(page_text)
            if weather_match:
                metadata['weather'] = weather_match.group(1)
            
            # 馬場状態を抽出
            track_condition_match = self.TRACK_CONDITION_PATTERN.search(page_text)
            if track_condition_match:
                metadata['track_condition'] = track_condition_match.group(1)
            
        except Exception as e:
            print(f"Error extracting metadata for race {race_id}: {e}")
        
        return metadata
    
    def _scrape_race_details(self, race_id: str) -> Optional[Tuple[pd.DataFrame, dict]]:
        """
        指定されたレースIDの結果データとメタデータをスクレイピング
        
        Args:
            race_id: レースの一意識別子（14桁）
            
        Returns:
            (レース結果のDataFrame, レースメタデータの辞書) のタプル。取得に失敗した場合はNone
        """
        url = f"{self.BASE_URL}{race_id}/"
        
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'lxml')
            
            # メタデータを抽出
            metadata = self._extract_race_metadata(soup, race_id)
            
            # pandas.read_html()を使用してテーブルデータを抽出
            tables = pd.read_html(response.text)
            
            if not tables:
                print(f"No tables found for race {race_id}")
                return None
            
            # 通常、レース結果は最初の大きなテーブルに含まれる
            results_df = None
            for table in tables:
                # 競馬結果テーブルの特徴：着順、馬名、騎手などの列がある
                if len(table.columns) > 10 and any('着' in str(col) for col in table.columns):
                    results_df = table
                    break
            
            if results_df is None:
                print(f"No results table found for race {race_id}")
                return None
            
            # データクレンジング
            # 列名の正規化（サイトの表記揺れに対応）
            column_mapping = {
                '着順': '着順',
                '枠': '枠番',
                '馬番': '馬番',
                '馬名': '馬名',
                '性齢': '性齢',
                '斤量': '斤量',
                '騎手': '騎手',
                'タイム': 'タイム',
                '着差': '着差',
                '人気': '人気',
                '単勝': '単勝',
                '調教師': '調教師',
                '馬体重': '馬体重'
            }
            
            # 列名を正規化
            results_df.columns = [column_mapping.get(col, col) for col in results_df.columns]
            
            # 数値列の処理
            numeric_columns = ['着順', '人気', '単勝', '斤量']
            for col in numeric_columns:
                if col in results_df.columns:
                    results_df[col] = results_df[col].replace(['---', '', '除外', '中止', '取消', '失格'], pd.NA)
                    results_df[col] = pd.to_numeric(results_df[col], errors='coerce')
            
            # 文字列列の処理
            string_columns = ['馬名', '騎手']
            for col in string_columns:
                if col in results_df.columns:
                    results_df[col] = results_df[col].fillna('').astype(str)
            
            # race_idを追加
            results_df['race_id'] = race_id
            
            return (results_df, metadata)
            
        except requests.RequestException as e:
            print(f"HTTP error for race {race_id}: {e}")
            return None
        except ValueError as e:
            print(f"Error parsing HTML tables for race {race_id}: {e}")
            return None
        except Exception as e:
            print(f"Unexpected error for race {race_id}: {e}")
            return None
    
    def _save_to_database(self, race_info: Dict[str, Any], results_df: pd.DataFrame) -> bool:
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
        指定された期間のレースデータを取得するメイン処理
        """
        print(f"keibalabデータ収集開始: {self.start_year}年 - {self.end_year}年")
        
        # 日付URLリストを生成
        date_urls = self._generate_date_urls()
        print(f"対象日数: {len(date_urls)}日")
        
        all_race_ids: List[str] = []
        
        # 日付ごとにレースIDを取得
        print("\nレースID取得中...")
        with tqdm(total=len(date_urls), desc="日付スキャン") as pbar:
            for current_date, url in date_urls:
                race_ids = self._fetch_race_ids_from_date(url)
                
                if race_ids:
                    all_race_ids.extend(race_ids)
                
                pbar.set_postfix({
                    '日付': current_date.strftime('%Y-%m-%d'),
                    '取得数': len(race_ids),
                    '累計': len(all_race_ids)
                })
                pbar.update(1)
                
                # サイトへの負荷軽減
                if race_ids:  # レースがあった日のみスリープ
                    time.sleep(self.TIME_SLEEP)
        
        # 結果の表示
        print(f"\nレースID取得完了!")
        print(f"総レース数: {len(all_race_ids)}")
        
        # 年別・開催場所別の統計表示
        stats = {}
        for race_id in all_race_ids:
            year = race_id[:4]
            course_code = race_id[8:10]
            course_name = self.COURSE_NAMES.get(course_code, f"Unknown({course_code})")
            
            if year not in stats:
                stats[year] = {}
            if course_name not in stats[year]:
                stats[year][course_name] = 0
            stats[year][course_name] += 1
        
        print("\n年別・開催場所別統計:")
        for year in sorted(stats.keys()):
            print(f"\n{year}年:")
            for course in sorted(stats[year].keys()):
                print(f"  {course}: {stats[year][course]}レース")
        
        # レース詳細データの取得とデータベース保存
        print(f"\nレース詳細データの取得を開始します...")
        successful_saves = 0
        failed_saves = 0
        
        with tqdm(total=len(all_race_ids), desc="データ取得・保存中") as pbar:
            for race_id in all_race_ids:
                try:
                    # レース結果とメタデータをスクレイピング
                    result = self._scrape_race_details(race_id)
                    
                    if result is not None:
                        results_df, metadata = result
                        
                        # レース情報を作成
                        race_info = {
                            'id': race_id,
                            'date': datetime.strptime(race_id[:8], '%Y%m%d').date(),
                            'course': metadata.get('course') or 'Unknown',
                            'race_number': int(race_id[10:12]) if len(race_id) >= 12 else 1,
                            'distance': metadata.get('distance') or 1600,
                            'track_type': metadata.get('track_type') or '芝',
                            'weather': metadata.get('weather'),
                            'track_condition': metadata.get('track_condition')
                        }
                        
                        # データベースに保存
                        if self._save_to_database(race_info, results_df):
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