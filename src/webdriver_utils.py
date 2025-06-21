"""
WebDriverユーティリティ関数

このモジュールはSelenium WebDriverの作成、管理、設定に関する
ユーティリティ関数を提供します。
"""

import os
import threading
from typing import Optional
from contextlib import contextmanager
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager


class WebDriverConfig:
    """WebDriver設定を管理するクラス"""
    
    def __init__(self):
        """環境変数からWebDriver設定を読み込む"""
        self.headless = os.getenv('WEBDRIVER_HEADLESS', 'true').lower() == 'true'
        self.timeout = int(os.getenv('WEBDRIVER_TIMEOUT', '10'))
        self.window_size = os.getenv('WEBDRIVER_WINDOW_SIZE', '1920,1080')
        self.user_agent = os.getenv('WEBDRIVER_USER_AGENT', 
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    def get_chrome_options(self) -> Options:
        """Chrome WebDriverのオプションを生成"""
        options = Options()
        
        if self.headless:
            options.add_argument('--headless')
        
        # 基本的なオプション
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--disable-web-security')
        options.add_argument('--ignore-certificate-errors')
        options.add_argument('--ignore-ssl-errors')
        options.add_argument('--ignore-certificate-errors-spki-list')
        
        # ウィンドウサイズの設定
        options.add_argument(f'--window-size={self.window_size}')
        
        # User-Agentの設定
        options.add_argument(f'--user-agent={self.user_agent}')
        
        # メモリ使用量の最適化
        options.add_argument('--memory-pressure-off')
        options.add_argument('--max_old_space_size=4096')
        
        return options
    
    def __repr__(self) -> str:
        """設定情報の文字列表現"""
        return f"<WebDriverConfig(headless={self.headless}, timeout={self.timeout})>"


class WebDriverManager:
    """WebDriverの作成と管理を行うクラス"""
    
    _lock = threading.Lock()
    
    def __init__(self, config: Optional[WebDriverConfig] = None):
        """
        WebDriverマネージャーを初期化
        
        Args:
            config: WebDriver設定。Noneの場合はデフォルト設定を使用
        """
        self.config = config or WebDriverConfig()
        self._service: Optional[Service] = None
    
    @property
    def service(self) -> Service:
        """ChromeDriverサービスを取得（遅延初期化）"""
        if self._service is None:
            with self._lock:
                if self._service is None:
                    # webdriver-managerを使ってChromeDriverを自動取得
                    driver_path = ChromeDriverManager().install()
                    self._service = Service(driver_path)
        return self._service
    
    def create_driver(self) -> webdriver.Chrome:
        """
        新しいChrome WebDriverインスタンスを作成
        
        Returns:
            設定済みのChrome WebDriverインスタンス
        """
        options = self.config.get_chrome_options()
        driver = webdriver.Chrome(service=self.service, options=options)
        
        # タイムアウトの設定
        driver.implicitly_wait(self.config.timeout)
        driver.set_page_load_timeout(self.config.timeout * 3)  # ページロードは長めに設定
        
        return driver
    
    @contextmanager
    def driver_scope(self):
        """
        WebDriverのコンテキストマネージャー
        
        自動的にWebDriverを作成し、使用後にクリーンアップする。
        
        Usage:
            with webdriver_manager.driver_scope() as driver:
                driver.get("https://example.com")
                # 自動的にドライバーが終了される
        """
        driver = None
        try:
            driver = self.create_driver()
            yield driver
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    # ドライバー終了時のエラーは無視
                    pass
    
    def wait_for_element(self, driver: webdriver.Chrome, by: By, value: str, 
                        timeout: Optional[int] = None) -> bool:
        """
        指定された要素が表示されるまで待機
        
        Args:
            driver: WebDriverインスタンス
            by: 要素の検索方法
            value: 検索する値
            timeout: タイムアウト秒数（Noneの場合はデフォルト値を使用）
            
        Returns:
            要素が見つかった場合True、タイムアウトした場合False
        """
        try:
            wait_timeout = timeout or self.config.timeout
            WebDriverWait(driver, wait_timeout).until(
                EC.presence_of_element_located((by, value))
            )
            return True
        except Exception:
            return False
    
    def safe_get(self, driver: webdriver.Chrome, url: str) -> bool:
        """
        安全にページを取得する
        
        Args:
            driver: WebDriverインスタンス
            url: 取得するURL
            
        Returns:
            ページ取得が成功した場合True、失敗した場合False
        """
        try:
            driver.get(url)
            return True
        except Exception:
            return False


# グローバルインスタンス（シングルトンパターン）
_webdriver_manager: Optional[WebDriverManager] = None


def get_webdriver_manager() -> WebDriverManager:
    """
    グローバルなWebDriverマネージャーインスタンスを取得
    
    Returns:
        WebDriverManagerのシングルトンインスタンス
    """
    global _webdriver_manager
    if _webdriver_manager is None:
        _webdriver_manager = WebDriverManager()
    return _webdriver_manager


def create_driver() -> webdriver.Chrome:
    """
    新しいWebDriverインスタンスを作成
    
    Returns:
        設定済みのChrome WebDriverインスタンス
    """
    manager = get_webdriver_manager()
    return manager.create_driver()


@contextmanager
def driver_scope():
    """
    WebDriverスコープのコンテキストマネージャー
    
    Usage:
        with driver_scope() as driver:
            driver.get("https://example.com")
            # 自動的にドライバーが終了される
    """
    manager = get_webdriver_manager()
    with manager.driver_scope() as driver:
        yield driver