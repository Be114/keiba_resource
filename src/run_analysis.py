#!/usr/bin/env python3
"""
競馬分析エンジン - メインスクリプト

このスクリプトはYAMLファイルで定義された分析条件を読み込み、
競馬データの分析を実行するメインエンジンです。
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

import yaml
import pandas as pd
from sqlalchemy.orm import Session

from .db_utils import DatabaseManager
from .models import Race, Result


class AnalysisEngine:
    """
    競馬データ分析エンジンのメインクラス
    
    YAMLファイルから分析条件を読み込み、必須キーの検証を行い、
    分析条件を表示する機能を提供します。
    """
    
    REQUIRED_KEYS = ['analysis_name', 'conditions', 'output']
    
    def __init__(self, config_path: str) -> None:
        """
        分析エンジンを初期化します
        
        Args:
            config_path: 分析条件を定義したYAMLファイルのパス
        """
        self.config_path = Path(config_path)
        self.config: Dict[str, Any] = {}
        self.db_manager = DatabaseManager()
        
    def load_config(self) -> bool:
        """
        YAMLファイルから分析条件を読み込みます
        
        Returns:
            bool: 読み込みが成功した場合True、失敗した場合False
        """
        try:
            if not self.config_path.exists():
                print(f"エラー: 設定ファイルが見つかりません: {self.config_path}")
                return False
                
            with open(self.config_path, 'r', encoding='utf-8') as file:
                self.config = yaml.safe_load(file)
                
            print(f"設定ファイルを読み込みました: {self.config_path}")
            return True
            
        except yaml.YAMLError as e:
            print(f"エラー: YAMLファイルの解析に失敗しました: {e}")
            return False
        except Exception as e:
            print(f"エラー: ファイルの読み込みに失敗しました: {e}")
            return False
    
    def validate_config(self) -> bool:
        """
        設定ファイルの必須キーを検証します
        
        Returns:
            bool: 検証が成功した場合True、失敗した場合False
        """
        missing_keys: List[str] = []
        
        for key in self.REQUIRED_KEYS:
            if key not in self.config:
                missing_keys.append(key)
        
        if missing_keys:
            print(f"エラー: 必須キーが不足しています: {', '.join(missing_keys)}")
            print(f"必要なキー: {', '.join(self.REQUIRED_KEYS)}")
            return False
            
        print("設定ファイルの検証が完了しました")
        return True
    
    def display_config(self) -> None:
        """
        読み込んだ分析条件を画面に表示します
        """
        print("\n" + "="*50)
        print("分析条件")
        print("="*50)
        
        print(f"分析名: {self.config.get('analysis_name', 'N/A')}")
        
        print("\n条件:")
        conditions = self.config.get('conditions', {})
        for key, value in conditions.items():
            print(f"  {key}: {value}")
        
        print(f"\n出力設定: {self.config.get('output', 'N/A')}")
        
        print("="*50)
    
    def _apply_date_conditions(self, query: Any, conditions: Dict[str, Any]) -> Any:
        """
        日付範囲条件をクエリに適用します
        
        Args:
            query: SQLAlchemyクエリオブジェクト
            conditions: YAML設定の条件辞書
            
        Returns:
            更新されたSQLAlchemyクエリオブジェクト
            
        Raises:
            ValueError: 日付フォーマットが不正な場合
        """
        if 'date_range' not in conditions:
            return query
            
        date_range = conditions['date_range']
        
        if 'start' in date_range:
            try:
                start_date = datetime.strptime(date_range['start'], '%Y-%m-%d').date()
                query = query.filter(Race.date >= start_date)
            except ValueError as e:
                raise ValueError(f"日付フォーマットエラー (date_range.start): '{date_range['start']}' は正しい日付形式 (YYYY-MM-DD) ではありません") from e
                
        if 'end' in date_range:
            try:
                end_date = datetime.strptime(date_range['end'], '%Y-%m-%d').date()
                query = query.filter(Race.date <= end_date)
            except ValueError as e:
                raise ValueError(f"日付フォーマットエラー (date_range.end): '{date_range['end']}' は正しい日付形式 (YYYY-MM-DD) ではありません") from e
                
        return query
    
    def _apply_track_conditions(self, query: Any, conditions: Dict[str, Any]) -> Any:
        """
        競馬場条件をクエリに適用します
        
        Args:
            query: SQLAlchemyクエリオブジェクト
            conditions: YAML設定の条件辞書
            
        Returns:
            更新されたSQLAlchemyクエリオブジェクト
        """
        if 'race_tracks' in conditions:
            race_tracks = conditions['race_tracks']
            if race_tracks:
                query = query.filter(Race.course.in_(race_tracks))
        return query
    
    def _apply_distance_conditions(self, query: Any, conditions: Dict[str, Any]) -> Any:
        """
        距離範囲条件をクエリに適用します
        
        Args:
            query: SQLAlchemyクエリオブジェクト
            conditions: YAML設定の条件辞書
            
        Returns:
            更新されたSQLAlchemyクエリオブジェクト
        """
        if 'distance_range' in conditions:
            distance_range = conditions['distance_range']
            if 'min' in distance_range:
                query = query.filter(Race.distance >= distance_range['min'])
            if 'max' in distance_range:
                query = query.filter(Race.distance <= distance_range['max'])
        return query
    
    def _apply_course_type_conditions(self, query: Any, conditions: Dict[str, Any]) -> Any:
        """
        コース種別条件をクエリに適用します
        
        Args:
            query: SQLAlchemyクエリオブジェクト
            conditions: YAML設定の条件辞書
            
        Returns:
            更新されたSQLAlchemyクエリオブジェクト
        """
        if 'course_types' in conditions:
            course_types = conditions['course_types']
            if course_types:
                query = query.filter(Race.track_type.in_(course_types))
        return query
    
    def _apply_weather_conditions(self, query: Any, conditions: Dict[str, Any]) -> Any:
        """
        天候条件をクエリに適用します
        
        Args:
            query: SQLAlchemyクエリオブジェクト
            conditions: YAML設定の条件辞書
            
        Returns:
            更新されたSQLAlchemyクエリオブジェクト
        """
        if 'weather_conditions' in conditions:
            weather_conditions = conditions['weather_conditions']
            if weather_conditions:
                query = query.filter(Race.weather.in_(weather_conditions))
        return query
    
    def _apply_track_state_conditions(self, query: Any, conditions: Dict[str, Any]) -> Any:
        """
        馬場状態条件をクエリに適用します
        
        Args:
            query: SQLAlchemyクエリオブジェクト
            conditions: YAML設定の条件辞書
            
        Returns:
            更新されたSQLAlchemyクエリオブジェクト
        """
        if 'track_conditions' in conditions:
            track_conditions = conditions['track_conditions']
            if track_conditions:
                query = query.filter(Race.track_condition.in_(track_conditions))
        return query
    
    def _build_query(self, session: Session) -> Any:
        """
        YAML設定の条件に基づいて動的にSQLAlchemyクエリを構築します
        
        Args:
            session: データベースセッション
            
        Returns:
            SQLAlchemyクエリオブジェクト
            
        Raises:
            ValueError: 日付フォーマットが不正な場合
        """
        # 基本クエリ: ResultとRaceをJOIN
        query = session.query(Result).join(Race)
        
        conditions = self.config.get('conditions', {})
        
        # 各条件をヘルパーメソッドで適用
        query = self._apply_date_conditions(query, conditions)
        query = self._apply_track_conditions(query, conditions)
        query = self._apply_distance_conditions(query, conditions)
        query = self._apply_course_type_conditions(query, conditions)
        query = self._apply_weather_conditions(query, conditions)
        query = self._apply_track_state_conditions(query, conditions)
        
        return query
    
    def _extract_data_to_dataframe(self, results: List[Result]) -> pd.DataFrame:
        """
        クエリ結果をPandas DataFrameに変換します
        
        Args:
            results: Resultオブジェクトのリスト
            
        Returns:
            変換されたDataFrame
        """
        data = []
        for result in results:
            data.append({
                'race_id': result.race_id,
                'race_date': result.race.date,
                'course': result.race.course,
                'race_number': result.race.race_number,
                'distance': result.race.distance,
                'track_type': result.race.track_type,
                'weather': result.race.weather,
                'track_condition': result.race.track_condition,
                'horse_name': result.horse_name,
                'rank': result.rank,
                'pre_race_rank': result.pre_race_rank,
                'jockey_name': result.jockey_name,
                'odds': result.odds,
                'weight': result.weight,
                'is_winner': result.is_winner,
                'is_place': result.is_place
            })
        
        return pd.DataFrame(data)
    
    def run(self) -> bool:
        """
        分析エンジンのメイン処理を実行します
        
        Returns:
            bool: 処理が成功した場合True、失敗した場合False
        """
        if not self.load_config():
            return False
            
        if not self.validate_config():
            return False
            
        self.display_config()
        
        try:
            # データベース接続テスト
            if not self.db_manager.test_connection():
                print("\nエラー: データベースに接続できません")
                return False
            
            print("\nデータベースからデータを抽出しています...")
            
            # セッションを使用してクエリを実行
            with self.db_manager.session_scope() as session:
                query = self._build_query(session)
                results = query.all()
                
                if not results:
                    print("条件に一致するデータが見つかりませんでした。")
                    return True
                
                # データをDataFrameに変換
                df = self._extract_data_to_dataframe(results)
                
                print(f"\n抽出されたデータ: {len(df)} 件")
                print("\n=== データサンプル（最初の5行）===")
                print(df.head())
                
                print("\n=== データ統計情報 ===")
                print(f"総レース数: {df['race_id'].nunique()}")
                print(f"総競走馬数: {df['horse_name'].nunique()}")
                print(f"対象期間: {df['race_date'].min()} 〜 {df['race_date'].max()}")
                
            print("\nデータ抽出が完了しました。")
            return True
            
        except Exception as e:
            print(f"\nエラー: データ抽出中に問題が発生しました: {e}")
            return False


def parse_arguments() -> argparse.Namespace:
    """
    コマンドライン引数を解析します
    
    Returns:
        argparse.Namespace: 解析されたコマンドライン引数
    """
    parser = argparse.ArgumentParser(
        description='競馬データ分析エンジン',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
使用例:
  python run_analysis.py analysis_definitions/sample_analysis.yml
  python run_analysis.py config/my_analysis.yml
        '''
    )
    
    parser.add_argument(
        'config_file',
        help='分析条件を定義したYAMLファイルのパス'
    )
    
    return parser.parse_args()


def main() -> int:
    """
    メイン関数
    
    Returns:
        int: 終了コード (0: 成功, 1: 失敗)
    """
    args = parse_arguments()
    
    print("競馬分析エンジンを起動しています...")
    
    engine = AnalysisEngine(args.config_file)
    
    if engine.run():
        print("処理が正常に完了しました。")
        return 0
    else:
        print("処理中にエラーが発生しました。")
        return 1


if __name__ == "__main__":
    sys.exit(main())