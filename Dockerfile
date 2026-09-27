FROM python:3.10-slim

WORKDIR /app

# 依存ライブラリのインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションコードのコピー
COPY . .

# 実行時データディレクトリの確保
RUN mkdir -p data

# 環境変数の設定
ENV PORT=8080
ENV NO_BROWSER=1
ENV PYTHONUNBUFFERED=1

EXPOSE 8080

CMD ["python", "main.py"]
