"""
競馬データベースモデル定義

このモジュールは競馬データを格納するためのSQLAlchemyモデルを定義します。
主要なエンティティ：Race（レース情報）とResult（レース結果）
"""

from datetime import date
from typing import List, Optional
from sqlalchemy import Column, Integer, String, Date, Float, ForeignKey
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class Race(Base):
    """
    競馬レース情報を表すモデルクラス
    
    Attributes:
        id: レースの一意識別子
        date: 開催日
        course: コース名（例：東京、阪神）
        race_number: レース番号（1〜12）
        distance: 距離（メートル）
        track_type: コース種別（芝、ダート、障害）
        weather: 天気
        track_condition: 馬場状態
        results: このレースに関連する結果のリスト
    """
    
    __tablename__ = 'races'
    
    id: int = Column(Integer, primary_key=True, autoincrement=True)
    date: date = Column(Date, nullable=False)
    course: str = Column(String(50), nullable=False)
    race_number: int = Column(Integer, nullable=False)
    distance: int = Column(Integer, nullable=False)
    track_type: str = Column(String(20), nullable=False)
    weather: Optional[str] = Column(String(20))
    track_condition: Optional[str] = Column(String(20))
    
    # リレーションシップ：1つのレースに複数の結果
    results: List["Result"] = relationship("Result", back_populates="race", cascade="all, delete-orphan")
    
    def __repr__(self) -> str:
        """レースオブジェクトの文字列表現を返す"""
        return f"<Race(id={self.id}, date={self.date}, course={self.course}, race_number={self.race_number})>"
    
    def __str__(self) -> str:
        """人間が読みやすい文字列表現を返す"""
        return f"{self.date} {self.course} {self.race_number}R ({self.distance}m {self.track_type})"


class Result(Base):
    """
    競馬レース結果を表すモデルクラス
    
    Attributes:
        id: 結果の一意識別子
        race_id: 関連するレースのID
        horse_name: 馬名
        rank: 着順
        pre_race_rank: 予想順位（オッズ順位）
        jockey_name: 騎手名
        odds: オッズ（単勝）
        weight: 負担重量（kg）
        race: 関連するレースオブジェクト
    """
    
    __tablename__ = 'results'
    
    id: int = Column(Integer, primary_key=True, autoincrement=True)
    race_id: int = Column(Integer, ForeignKey('races.id'), nullable=False)
    horse_name: str = Column(String(100), nullable=False)
    rank: int = Column(Integer, nullable=False)
    pre_race_rank: Optional[int] = Column(Integer)
    jockey_name: str = Column(String(50), nullable=False)
    odds: Optional[float] = Column(Float)
    weight: Optional[float] = Column(Float)
    
    # リレーションシップ：結果は1つのレースに属する
    race: Race = relationship("Race", back_populates="results")
    
    def __repr__(self) -> str:
        """結果オブジェクトの文字列表現を返す"""
        return f"<Result(id={self.id}, race_id={self.race_id}, horse_name={self.horse_name}, rank={self.rank})>"
    
    def __str__(self) -> str:
        """人間が読みやすい文字列表現を返す"""
        return f"{self.rank}着 {self.horse_name} ({self.jockey_name}) オッズ:{self.odds}"
    
    @property
    def is_winner(self) -> bool:
        """この結果が1着かどうかを判定する"""
        return self.rank == 1
    
    @property
    def is_place(self) -> bool:
        """この結果が3着以内かどうかを判定する"""
        return self.rank <= 3