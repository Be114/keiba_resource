#!/usr/bin/env python3
"""
競馬分析エンジン - メインスクリプト

このスクリプトはYAMLファイルで定義された分析条件を読み込み、
競馬データの分析を実行するメインエンジンです。
"""

import argparse
import os
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
    
    def _calculate_statistics(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        データフレームから競馬統計量を計算します
        
        Args:
            df: 競馬データのDataFrame
            
        Returns:
            統計情報を含む辞書
        """
        if df.empty:
            return {
                'analysis_name': self.config.get('analysis_name', 'N/A'),
                'total_races': 0,
                'total_horses': 0,
                'win_rate': 0.0,
                'place_rate': 0.0,
                'win_payout_rate': 0.0,
                'place_payout_rate': 0.0,
                'analysis_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        
        # 基本統計
        total_races = df['race_id'].nunique()
        total_horses = len(df)
        
        # 勝率計算
        winners = df[df['is_winner'] == True]
        win_rate = (len(winners) / total_horses * 100) if total_horses > 0 else 0.0
        
        # 複勝率計算（3着内率）
        place_finishers = df[df['is_place'] == True]
        place_rate = (len(place_finishers) / total_horses * 100) if total_horses > 0 else 0.0
        
        # 単勝回収率計算（100円ベットと仮定）
        total_bet_amount = total_horses * 100  # 1頭あたり100円ベット
        
        # 単勝払戻金計算
        win_payout = 0.0
        for _, row in winners.iterrows():
            if pd.notna(row['odds']) and row['odds'] > 0:
                win_payout += row['odds'] * 100  # 100円ベットの払戻金
        
        win_payout_rate = (win_payout / total_bet_amount * 100) if total_bet_amount > 0 else 0.0
        
        # 複勝払戻金計算（簡略化: 複勝オッズを単勝オッズの1/3と仮定）
        place_payout = 0.0
        for _, row in place_finishers.iterrows():
            if pd.notna(row['odds']) and row['odds'] > 0:
                # 複勝オッズは通常単勝オッズより低いので、簡略化して計算
                place_odds = max(1.0, row['odds'] / 3.0)  # 最低1.0倍
                place_payout += place_odds * 100
        
        place_payout_rate = (place_payout / total_bet_amount * 100) if total_bet_amount > 0 else 0.0
        
        return {
            'analysis_name': self.config.get('analysis_name', 'N/A'),
            'total_races': total_races,
            'total_horses': total_horses,
            'win_rate': round(win_rate, 2),
            'place_rate': round(place_rate, 2),
            'win_payout_rate': round(win_payout_rate, 2),
            'place_payout_rate': round(place_payout_rate, 2),
            'analysis_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
    
    def _export_to_csv(self, stats: Dict[str, Any]) -> None:
        """
        統計情報をCSVファイルに追記します
        
        Args:
            stats: 統計情報を含む辞書
        """
        output_config = self.config.get('output', {})
        csv_path = output_config.get('save_path', 'results/analysis_results.csv')
        
        # 出力ディレクトリが存在しない場合は作成
        output_dir = os.path.dirname(csv_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
        
        # DataFrameとして統計情報を整理
        stats_df = pd.DataFrame([stats])
        
        # ファイルが既に存在するかチェック
        file_exists = os.path.exists(csv_path)
        
        # CSVファイルに追記モードで書き込み
        stats_df.to_csv(
            csv_path,
            mode='a',
            header=not file_exists,  # ファイルが存在しない場合のみヘッダーを書き込み
            index=False,
            encoding='utf-8'
        )
        
        print(f"\n結果をCSVファイルに保存しました: {csv_path}")
    
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
                
                # 統計量を計算
                stats = self._calculate_statistics(df)
                
                # 結果を表示
                print("\n" + "="*60)
                print("競馬分析結果")
                print("="*60)
                print(f"分析名: {stats['analysis_name']}")
                print(f"総レース数: {stats['total_races']:,} レース")
                print(f"総出走頭数: {stats['total_horses']:,} 頭")
                print(f"勝率: {stats['win_rate']:.2f}%")
                print(f"複勝率（3着内率）: {stats['place_rate']:.2f}%")
                print(f"単勝回収率: {stats['win_payout_rate']:.2f}%")
                print(f"複勝回収率: {stats['place_payout_rate']:.2f}%")
                print(f"分析実行日時: {stats['analysis_date']}")
                print("="*60)
                
                # CSVファイルに結果を保存
                self._export_to_csv(stats)
                
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