"""
データベースユーティリティ関数

このモジュールはデータベース接続、セッション管理、初期化に関する
ユーティリティ関数を提供します。
"""

import os
from typing import Optional
from contextlib import contextmanager
from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import sessionmaker, Session
from dotenv import load_dotenv

from .models import Base


class DatabaseConfig:
    """データベース接続設定を管理するクラス"""
    
    def __init__(self):
        """環境変数からデータベース接続情報を読み込む"""
        load_dotenv()
        
        self.user = os.getenv('DB_USER', 'user')
        self.password = os.getenv('DB_PASSWORD', 'password')
        self.host = os.getenv('DB_HOST', 'localhost')
        self.port = os.getenv('DB_PORT', '5432')
        self.name = os.getenv('DB_NAME', 'keiba_data')
    
    @property
    def connection_url(self) -> str:
        """PostgreSQL接続URLを生成する"""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"
    
    def __repr__(self) -> str:
        """設定情報の文字列表現（パスワードは非表示）"""
        return f"<DatabaseConfig(user={self.user}, host={self.host}, port={self.port}, name={self.name})>"


class DatabaseManager:
    """データベース接続とセッション管理を行うクラス"""
    
    def __init__(self, config: Optional[DatabaseConfig] = None):
        """
        データベースマネージャーを初期化
        
        Args:
            config: データベース設定。Noneの場合は環境変数から読み込み
        """
        self.config = config or DatabaseConfig()
        self._engine: Optional[Engine] = None
        self._session_maker: Optional[sessionmaker] = None
    
    @property
    def engine(self) -> Engine:
        """SQLAlchemyエンジンを取得（遅延初期化）"""
        if self._engine is None:
            self._engine = create_engine(
                self.config.connection_url,
                echo=False,  # SQLログ出力を無効化（本番環境向け）
                pool_pre_ping=True,  # 接続の有効性を事前チェック
                pool_recycle=3600,  # 1時間で接続をリサイクル
            )
        return self._engine
    
    @property
    def session_maker(self) -> sessionmaker:
        """セッションメーカーを取得（遅延初期化）"""
        if self._session_maker is None:
            self._session_maker = sessionmaker(bind=self.engine)
        return self._session_maker
    
    def create_tables(self) -> None:
        """すべてのテーブルを作成する"""
        Base.metadata.create_all(self.engine)
    
    def drop_tables(self) -> None:
        """すべてのテーブルを削除する（開発・テスト用）"""
        Base.metadata.drop_all(self.engine)
    
    def get_session(self) -> Session:
        """新しいデータベースセッションを作成する"""
        return self.session_maker()
    
    @contextmanager
    def session_scope(self):
        """
        セッションのコンテキストマネージャー
        
        自動的にセッションを開始し、例外が発生した場合はロールバック、
        正常終了時はコミットして、最後にセッションを閉じる。
        
        Usage:
            with db_manager.session_scope() as session:
                session.add(some_object)
                # 自動的にコミットされる
        """
        session = self.get_session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    
    def test_connection(self) -> bool:
        """
        データベース接続をテストする
        
        Returns:
            接続が成功した場合True、失敗した場合False
        """
        try:
            with self.engine.connect() as connection:
                connection.execute("SELECT 1")
            return True
        except Exception:
            return False


# グローバルインスタンス（シングルトンパターン）
_db_manager: Optional[DatabaseManager] = None


def get_db_manager() -> DatabaseManager:
    """
    グローバルなデータベースマネージャーインスタンスを取得
    
    Returns:
        DatabaseManagerのシングルトンインスタンス
    """
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager


def init_database() -> None:
    """データベースを初期化（テーブル作成）"""
    db_manager = get_db_manager()
    db_manager.create_tables()


def get_session() -> Session:
    """
    新しいデータベースセッションを取得
    
    Returns:
        SQLAlchemy Session オブジェクト
    """
    db_manager = get_db_manager()
    return db_manager.get_session()


@contextmanager
def session_scope():
    """
    セッションスコープのコンテキストマネージャー
    
    Usage:
        with session_scope() as session:
            session.add(some_object)
            # 自動的にコミットされる
    """
    db_manager = get_db_manager()
    with db_manager.session_scope() as session:
        yield session