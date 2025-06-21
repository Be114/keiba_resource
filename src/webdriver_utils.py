"""
競馬データ収集ツール (Seleniumベース)

netkeiba.comから指定された期間のレース情報を取得し、データベースに保存するツール。
動的なページに対応するため、Selenium WebDriverを使用します。
"""

import argparse
import re
import time
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple

import pandas as pd
from bs4 import BeautifulSoup
from selenium.common.exceptions import WebDriverException
from tqdm import tqdm
from sqlalchemy.exc import IntegrityError

# --- 修正点 1: 必要なモジュールをインポート ---
from src.db_utils import DatabaseManager
from src.models import Race, Result
from src.webdriver_utils import get_webdriver_manager, driver_scope

class DataScraper:
    """
    netkeiba.comからレース情報を取得するデータスクレイパー (Selenium版)
    """
    TIME_SLEEP = 1
    # --- 修正点 2: requests関連の正規表現を一部webdriver_utilsに寄せ、必要なものだけ残す ---
    KAISAI_DATE_PATTERN = re.compile(r'kaisai_date=(\d+)')
    RACE_ID_PATTERN = re.compile(r'race_id=(\d+)')

    # --- 修正点 3: メタデータ抽出の正規表現はここで管理 ---
    DISTANCE_PATTERN = re.compile(r'(\d+)m')
    TRACK_TYPE_PATTERN = re.compile(r'(芝|ダート|障害)')
    
    def __init__(self, start_year: int, end_year: int):
        self.start_year = start_year
        self.end_year = end_year
        # --- 修正点 4: sessionの代わりにwebdriver_managerを初期化 ---
        self.webdriver_manager = get_webdriver_manager()
        self.db_manager = DatabaseManager()
        self.db_manager.create_tables()

    # --- 修正点 5: requestsのセッション作成は不要になったので削除 ---
    # def _create_session(self) -> requests.Session: ... (このメソッド全体を削除)

    def _fetch_kaisai_dates(self, year: int, month: int) -> List[str]:
        """
        カレンダーページからその月のレース開催日リストを取得 (ここはrequestsでOK)
        """
        url = f"https://race.netkeiba.com/top/calendar.html?year={year}&month={month:02d}"
        # この部分だけは静的なので、高速なrequestsを直接使っても良いが、
        # User-Agentなどを統一するため、Selenium経由に統一するのも手。
        # ここではシンプルにSeleniumに統一する。
        dates = []
        try:
            with driver_scope() as driver:
                driver.get(url)
                soup = BeautifulSoup(driver.page_source, 'lxml')
                for a in soup.select('.Calendar_Table a[href*="kaisai_date"]'):
                    match = self.KAISAI_DATE_PATTERN.search(a['href'])
                    if match:
                        dates.append(match.group(1))
        except WebDriverException as e:
            print(f"Error fetching kaisai dates for {year}-{month:02d}: {e}")
        return list(set(dates))

    def _fetch_race_ids_from_date(self, kaisai_date: str) -> List[str]:
        """
        特定の日付のレース一覧ページからレースIDリストを取得 (Seleniumが必須)
        """
        url = f"https://race.netkeiba.com/top/race_list.html?kaisai_date={kaisai_date}"
        race_ids = []
        try:
            with driver_scope() as driver:
                driver.get(url)
                # 'RaceList_DataItem'クラスの要素が表示されるまで待機
                self.webdriver_manager.wait_for_element(driver, 'class name', 'RaceList_DataItem')
                soup = BeautifulSoup(driver.page_source, 'lxml')
                for a in soup.select('a[href*="race_id"]'):
                    match = self.RACE_ID_PATTERN.search(a['href'])
                    if match:
                        race_ids.append(match.group(1))
        except WebDriverException as e:
            print(f"Error fetching race IDs for {kaisai_date}: {e}")
        return list(set(race_ids))
        
    def _scrape_race_metadata(self, soup: BeautifulSoup) -> dict:
        metadata = {'race_name': None, 'distance': None, 'track_type': None, 'weather': None, 'track_condition': None, 'course': None}
        try:
            diary_title = soup.select_one('.RaceData01')
            if diary_title:
                text = diary_title.get_text(strip=True)
                # 例: "芝右 外2400m / 天候 : 晴 / 芝 : 良"
                parts = text.split('/')
                if len(parts) >= 3:
                    # コース情報
                    course_match = re.search(r'(芝|ダート|障害).*?(\d+)m', parts[0])
                    if course_match:
                        metadata['track_type'] = course_match.group(1)
                        metadata['distance'] = int(course_match.group(2))
                    # 天候
                    weather_match = re.search(r'天候 : (\S+)', parts[1])
                    if weather_match:
                        metadata['weather'] = weather_match.group(1)
                    # 馬場状態
                    condition_match = re.search(r'芝 : (\S+)|ダート : (\S+)', parts[2])
                    if condition_match:
                        metadata['track_condition'] = condition_match.group(1) or condition_match.group(2)
            
            race_name_elem = soup.select_one('.RaceName')
            if race_name_elem:
                metadata['race_name'] = race_name_elem.get_text(strip=True)

            main_race_data = soup.select_one('.RaceData02')
            if main_race_data:
                 metadata['course'] = main_race_data.get_text(strip=True).split(' ')[1]

        except Exception as e:
            print(f"Error extracting race metadata: {e}")
        return metadata

    def _scrape_race_results(self, race_id: str) -> Optional[Tuple[pd.DataFrame, dict]]:
        url = f"https://db.netkeiba.com/race/{race_id}"
        try:
            with driver_scope() as driver:
                driver.get(url)
                soup = BeautifulSoup(driver.page_source, 'lxml')
                metadata = self._scrape_race_metadata(soup)
                
                tables = pd.read_html(driver.page_source)
                if not tables:
                    print(f"No tables found for race {race_id}")
                    return None

                results_df = tables[0]
                # ... (データクレンジングのロジックはほぼ同じなので省略)
                return (results_df, metadata)
        except (WebDriverException, ValueError) as e:
            print(f"Error scraping race {race_id}: {e}")
            return None

    def _save_data_to_db(self, race_info: Dict[str, Any], results_df: pd.DataFrame) -> bool:
        # ... (このメソッドは大きな変更なし)
        pass # 便宜上省略

    def run(self) -> None:
        print(f"データ収集開始: {self.start_year}年 - {self.end_year}年")
        
        all_kaisai_dates = []
        for year in range(self.start_year, self.end_year + 1):
            for month in range(1, 13):
                dates = self._fetch_kaisai_dates(year, month)
                all_kaisai_dates.extend(dates)
                time.sleep(self.TIME_SLEEP)

        all_race_ids = set()
        with tqdm(total=len(all_kaisai_dates), desc="レースID取得中") as pbar:
            for kaisai_date in all_kaisai_dates:
                ids = self._fetch_race_ids_from_date(kaisai_date)
                all_race_ids.update(ids)
                pbar.set_postfix({'日付': kaisai_date, '取得数': len(ids)})
                pbar.update(1)
                time.sleep(self.TIME_SLEEP)
        
        # ... (ここから先のDB保存までの流れは以前とほぼ同じ)
        pass # 便宜上省略

# ... (main関数やargparseの部分は変更なし)