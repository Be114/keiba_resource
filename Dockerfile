# ベースとなるPythonの公式イメージを指定
FROM python:3.11-slim

# コンテナ内での作業ディレクトリを設定
WORKDIR /app

# --- ここからが追加部分 ---
# パッケージリストを更新し、Chromeのインストールに必要な依存関係をインストール
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    --no-install-recommends

# Google Chromeの公式リポジトリキーをダウンロード・配置
RUN wget -q -O /usr/share/keyrings/google-chrome.gpg https://dl-ssl.google.com/linux/linux_signing_key.pub

# Google Chromeの公式リポジトリをパッケージソースに追加（signed-byオプション使用）
RUN sh -c 'echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list'

# パッケージリストを再度更新し、Google Chrome（安定版）をインストール
RUN apt-get update && apt-get install -y \
    google-chrome-stable \
    --no-install-recommends

# 不要になったパッケージキャッシュを削除して、イメージサイズを小さくする
RUN rm -rf /var/lib/apt/lists/*
# --- ここまでが追加部分 ---

# まず、依存関係ファイルだけをコピーしてインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# プロジェクトの残りのファイルをすべてコピー
COPY . .

# このコンテナが起動したときに実行されるデフォルトのコマンド (何もしない)
CMD ["tail", "-f", "/dev/null"]