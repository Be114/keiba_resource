"""
WebDriver管理ユーティリティ

Selenium WebDriverの設定、初期化、および管理を行うモジュール。
Chrome WebDriverの自動管理とコンテキストマネージャーパターンによる
リソースの安全な管理を提供します。
"""

import os
import time
from contextlib import contextmanager
from typing import Optional, Generator

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager


class WebDriverConfig:
    """
    WebDriver設定管理クラス
    
    環境変数とデフォルト値を使用してWebDriverの設定を管理します。
    """
    
    def __init__(self):
        """設定の初期化"""
        # 環境変数から設定を読み込み、デフォルト値を設定
        self.headless: bool = os.getenv('WEBDRIVER_HEADLESS', 'true').lower() == 'true'
        self.timeout: int = int(os.getenv('WEBDRIVER_TIMEOUT', '30'))
        self.window_width: int = int(os.getenv('WEBDRIVER_WINDOW_WIDTH', '1920'))
        self.window_height: int = int(os.getenv('WEBDRIVER_WINDOW_HEIGHT', '1080'))
        self.user_agent: str = os.getenv(
            'WEBDRIVER_USER_AGENT', 
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        )
        
    def get_chrome_options(self) -> Options:
        """
        Chrome WebDriverのオプションを取得
        
        Returns:
            設定済みのChromeOptionsオブジェクト
        """
        options = Options()
        
        # ヘッドレスモード
        if self.headless:
            options.add_argument('--headless')
        
        # ウィンドウサイズ
        options.add_argument(f'--window-size={self.window_width},{self.window_height}')
        
        # User-Agent
        options.add_argument(f'--user-agent={self.user_agent}')
        
        # パフォーマンス最適化のためのオプション
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--disable-extensions')
        options.add_argument('--disable-plugins')
        options.add_argument('--disable-images')
        
        # セキュリティ関連のオプション
        options.add_argument('--disable-web-security')
        options.add_argument('--disable-features=VizDisplayCompositor')
        
        return options


class WebDriverManager:
    """
    WebDriver管理クラス
    
    Chrome WebDriverの初期化、設定、および安全な終了処理を管理します。
    """
    
    def __init__(self, config: Optional[WebDriverConfig] = None):
        """
        WebDriverManagerの初期化
        
        Args:
            config: WebDriver設定オブジェクト。Noneの場合はデフォルト設定を使用
        """
        self.config = config or WebDriverConfig()
        self._driver_path: Optional[str] = None
        
    def _ensure_driver_path(self) -> str:
        """
        ChromeDriverのパスを確保
        
        Returns:
            ChromeDriverの実行可能ファイルパス
        """
        if self._driver_path is None:
            # webdriver-managerを使用してChromeDriverを自動ダウンロード・管理
            self._driver_path = ChromeDriverManager().install()
        return self._driver_path
    
    def create_driver(self) -> webdriver.Chrome:
        """
        Chrome WebDriverインスタンスを作成
        
        Returns:
            設定済みのChrome WebDriverインスタンス
            
        Raises:
            WebDriverException: WebDriver作成に失敗した場合
        """
        try:
            # ChromeDriverのパスを取得
            driver_path = self._ensure_driver_path()
            
            # サービスオブジェクトを作成
            service = Service(driver_path)
            
            # Chromeオプションを取得
            options = self.config.get_chrome_options()
            
            # WebDriverインスタンスを作成
            driver = webdriver.Chrome(service=service, options=options)
            
            # タイムアウト設定
            driver.implicitly_wait(self.config.timeout)
            driver.set_page_load_timeout(self.config.timeout)
            
            return driver
            
        except Exception as e:
            raise WebDriverException(f"Failed to create WebDriver: {e}")
    
    def safe_get(self, driver: webdriver.Chrome, url: str, retries: int = 3) -> bool:
        """
        URLを安全に取得（リトライ機能付き）
        
        Args:
            driver: WebDriverインスタンス
            url: 取得するURL
            retries: リトライ回数
            
        Returns:
            成功した場合True、失敗した場合False
        """
        for attempt in range(retries):
            try:
                driver.get(url)
                return True
            except (TimeoutException, WebDriverException) as e:
                if attempt < retries - 1:
                    print(f"Retry {attempt + 1}/{retries} for {url}: {e}")
                    time.sleep(2 ** attempt)  # 指数バックオフ
                else:
                    print(f"Failed to load {url} after {retries} attempts: {e}")
                    return False
        return False
    
    def wait_for_element(self, driver: webdriver.Chrome, by: str, value: str, timeout: Optional[int] = None) -> bool:
        """
        要素の出現を待機
        
        Args:
            driver: WebDriverインスタンス
            by: 要素の検索方法（'id', 'class name', 'tag name'など）
            value: 検索値
            timeout: タイムアウト時間（秒）。Noneの場合はデフォルト設定を使用
            
        Returns:
            要素が見つかった場合True、タイムアウトした場合False
        """
        try:
            wait_timeout = timeout or self.config.timeout
            wait = WebDriverWait(driver, wait_timeout)
            
            # by文字列をBy定数に変換
            by_mapping = {
                'id': By.ID,
                'class name': By.CLASS_NAME,
                'tag name': By.TAG_NAME,
                'css selector': By.CSS_SELECTOR,
                'xpath': By.XPATH,
                'link text': By.LINK_TEXT,
                'partial link text': By.PARTIAL_LINK_TEXT,
                'name': By.NAME
            }
            
            by_constant = by_mapping.get(by.lower(), By.CSS_SELECTOR)
            wait.until(EC.presence_of_element_located((by_constant, value)))
            return True
            
        except TimeoutException:
            print(f"Timeout waiting for element: {by}='{value}'")
            return False
    
    @contextmanager
    def driver_scope(self) -> Generator[webdriver.Chrome, None, None]:
        """
        WebDriverのコンテキストマネージャー
        
        Yields:
            Chrome WebDriverインスタンス
        """
        driver = None
        try:
            driver = self.create_driver()
            yield driver
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception as e:
                    print(f"Error closing WebDriver: {e}")


# グローバルインスタンス（シングルトンパターン）
_webdriver_manager: Optional[WebDriverManager] = None


def get_webdriver_manager() -> WebDriverManager:
    """
    WebDriverManagerのグローバルインスタンスを取得
    
    Returns:
        WebDriverManagerインスタンス
    """
    global _webdriver_manager
    if _webdriver_manager is None:
        _webdriver_manager = WebDriverManager()
    return _webdriver_manager


@contextmanager
def driver_scope() -> Generator[webdriver.Chrome, None, None]:
    """
    WebDriverのコンテキストマネージャー（グローバル関数版）
    
    Yields:
        Chrome WebDriverインスタンス
    """
    manager = get_webdriver_manager()
    with manager.driver_scope() as driver:
        yield driver