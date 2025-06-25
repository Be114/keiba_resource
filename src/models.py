"""
競馬データベースモデル定義

このモジュールは競馬データを格納するためのSQLAlchemyモデルを定義します。
主要なエンティティ：Race（レース情報）とResult（レース結果）
"""

from datetime import date
from typing import List, Optional

from sqlalchemy import Column, Integer, String, Date, Float, ForeignKey
from sqlalchemy.orm import declarative_base, relationship, Mapped, mapped_column

Base = declarative_base()


class Race(Base):
    """
    競馬レース情報を表すモデルクラス
    
    Attributes:
        id: レースの一意識別子 (netkeibaのID)
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
    
    # SQLAlchemy 2.0 推奨の書き方に変更
    id: Mapped[str] = mapped_column(String(14), primary_key=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    course: Mapped[str] = mapped_column(String(50), nullable=False)
    race_number: Mapped[int] = mapped_column(Integer, nullable=False)
    distance: Mapped[int] = mapped_column(Integer, nullable=False)
    track_type: Mapped[str] = mapped_column(String(20), nullable=False)
    weather: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    track_condition: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    
    # リレーションシップの型ヒントもMapped[]で囲む
    results: Mapped[List["Result"]] = relationship("Result", back_populates="race", cascade="all, delete-orphan")
    
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
        id: 結果の一意識別子 (DBの自動採番)
        race_id: 関連するレースのID (netkeibaのID)
        horse_name: 馬名
        rank: 着順
        pre_race_rank: 予想順位（オッズ順位）
        jockey_name: 騎手名
        odds: オッズ（単勝）
        weight: 負担重量（kg）
        race: 関連するレースオブジェクト
    """
    
    __tablename__ = 'results'
    
    # SQLAlchemy 2.0 推奨の書き方に変更
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    race_id: Mapped[str] = mapped_column(String(14), ForeignKey('races.id'), nullable=False)
    horse_name: Mapped[str] = mapped_column(String(100), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    pre_race_rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    jockey_name: Mapped[str] = mapped_column(String(50), nullable=False)
    odds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    weight: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # リレーションシップの型ヒントもMapped[]で囲む
    race: Mapped["Race"] = relationship("Race", back_populates="results")
    
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
