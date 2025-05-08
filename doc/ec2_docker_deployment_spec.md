# EC2デプロイのための変更仕様書（Docker対応・最小構成版）

## 現状の課題

コードベースを分析した結果、EC2環境（無料枠）でDockerを使用して安全かつ効率的にデプロイするために以下の課題が特定されました：

### セキュリティ関連の課題

1. **APIキー管理の脆弱性**
   - OpenAI APIキーが環境変数から直接取得されているが、検証やフォールバックメカニズムがない
   - APIキーが平文で環境変数に保存されている

2. **HTTPSサポートの欠如**
   - アプリケーションがHTTPSを強制する設定がない

3. **セキュリティヘッダーの欠如**
   - Content Security Policy (CSP)などのセキュリティヘッダーが設定されていない
   - CSRF保護が実装されていない

4. **ファイルアップロードの脆弱性**
   - アップロードサイズ制限がない
   - ファイルタイプの厳格な検証がない
   - アップロードされたファイルの安全な保存場所が定義されていない

5. **エラー処理とログ記録の不足**
   - 本番環境向けの適切なエラー処理がない
   - 構造化されたログ記録システムがない

### デプロイ関連の課題

1. **本番サーバー設定の欠如**
   - `app.run(debug=True)`がコメントアウトされているが、代替のWSGIサーバー設定がない

2. **環境設定管理の欠如**
   - 開発/テスト/本番環境の設定を区別する仕組みがない

3. **Docker設定の欠如**
   - Dockerfileがない
   - docker-compose.ymlがない
   - コンテナ間の通信設定がない

4. **EC2固有の設定の欠如**
   - セキュリティグループ設定がない
   - 無料枠EC2向けのリソース最適化がない

## 推奨される変更

### 1. APIキー管理の改善

```python
# 現在のコード (resapimodule.py)
openai.api_key = os.getenv('OPENAI_API_KEY')

# 推奨される変更
import os
import json

def get_secret():
    """APIキーを取得する関数"""
    # Docker環境変数から取得
    api_key = os.getenv('OPENAI_API_KEY')
    
    if not api_key:
        # フォールバックとしてファイルから読み込む（開発環境用）
        try:
            with open('/run/secrets/openai_api_key', 'r') as f:
                api_key = f.read().strip()
        except (FileNotFoundError, IOError):
            pass
    
    if not api_key:
        raise Exception("APIキーが設定されていません")
        
    return api_key

# APIキーを設定
openai.api_key = get_secret()
```

### 2. 本番サーバー設定の追加

```python
# 現在のコード (app.py)
# app.run(debug=True)

# 推奨される変更 (app.py)
if __name__ == "__main__":
    # Dockerコンテナ内では0.0.0.0にバインド
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
```

### 3. セキュリティヘッダーとCSRF保護の追加

```python
# 推奨される変更 (app.py)
from flask_wtf.csrf import CSRFProtect
from flask_talisman import Talisman

csrf = CSRFProtect(app)
talisman = Talisman(
    app,
    content_security_policy={
        'default-src': "'self'",
        'script-src': ["'self'", "'unsafe-inline'", "cdn.jsdelivr.net"],
        'style-src': ["'self'", "'unsafe-inline'"],
        'img-src': ["'self'", "data:"],
        'connect-src': ["'self'"]
    },
    force_https=False  # EC2内部通信ではHTTPSを強制しない
)

# CSRFトークンをテンプレートに渡す
@app.route('/')
def index():
    return render_template('mychatbot/index.html', csrf_token=csrf.generate_csrf())
```

### 4. ファイルアップロードセキュリティの強化

```python
# 推奨される変更 (app.py)
import os
from werkzeug.utils import secure_filename

# 設定
UPLOAD_FOLDER = '/tmp/uploads'
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'gif'}
MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5MB (無料枠EC2向けに制限)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/submit', methods=['POST'])
def submit():
    # ...既存のコード...
    
    # アップロードされたファイルを取得
    uploaded_file = request.files.get('file')
    file_base64 = None
    
    if uploaded_file and uploaded_file.filename:
        if not allowed_file(uploaded_file.filename):
            return jsonify({'message': 'サポートされていないファイル形式です'})
            
        # 安全なファイル名を生成
        filename = secure_filename(uploaded_file.filename)
        
        # ディレクトリが存在することを確認
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        
        # ファイルを一時的に保存
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        uploaded_file.save(file_path)
        
        # ファイルを読み取り、Base64に変換
        with open(file_path, 'rb') as f:
            file_content = f.read()
            file_base64 = base64.b64encode(file_content).decode('utf-8')
            
        # 処理後、一時ファイルを削除
        os.remove(file_path)
        
        # ...残りの処理...
```

### 5. エラー処理とログ記録の改善

```python
# 推奨される変更 (app.py)
import logging
import sys

# ログ設定 - Dockerコンテナ向け
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)  # コンテナログをstdoutに出力
    ]
)

# グローバルエラーハンドラー
@app.errorhandler(Exception)
def handle_exception(e):
    app.logger.error(f"Unhandled exception: {str(e)}", exc_info=True)
    if os.environ.get('FLASK_ENV') == 'production':
        return jsonify({'message': 'サーバーエラーが発生しました。管理者に連絡してください。'}), 500
    else:
        return jsonify({'message': f'エラー: {str(e)}'}), 500
```

### 6. 環境設定管理の改善

```python
# 推奨される変更 (config.py - 新規ファイル)
import os

class Config:
    """共通設定"""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'hard-to-guess-string'
    UPLOAD_FOLDER = '/tmp/uploads'
    ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'gif'}
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5MB

class DevelopmentConfig(Config):
    """開発環境設定"""
    DEBUG = True
    TESTING = False

class TestingConfig(Config):
    """テスト環境設定"""
    DEBUG = False
    TESTING = True

class ProductionConfig(Config):
    """本番環境設定"""
    DEBUG = False
    TESTING = False
    # メモリ使用量を最小化
    PRESERVE_CONTEXT_ON_EXCEPTION = False
    JSONIFY_PRETTYPRINT_REGULAR = False

config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
```

```python
# app.py での使用
from config import config
import os

# 環境設定の適用
config_name = os.environ.get('FLASK_ENV') or 'default'
app.config.from_object(config[config_name])
```

## Docker設定

### 1. Dockerfile

```dockerfile
# 軽量なPythonイメージを使用
FROM python:3.9-slim

# 作業ディレクトリを設定
WORKDIR /app

# 依存関係をコピーしてインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションコードをコピー
COPY . .

# アップロードディレクトリを作成
RUN mkdir -p /tmp/uploads && chmod 777 /tmp/uploads

# 環境変数を設定
ENV FLASK_APP=app.py
ENV FLASK_ENV=production
ENV PORT=5000

# Gunicornを使用してアプリケーションを実行
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--threads", "2", "app:app"]

# ヘルスチェック
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:5000/ || exit 1
```

### 2. docker-compose.yml

```yaml
version: '3'

services:
  web:
    build: .
    restart: always
    ports:
      - "80:5000"
    environment:
      - FLASK_APP=app.py
      - FLASK_ENV=production
      - SECRET_KEY=${SECRET_KEY}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    volumes:
      - ./logs:/app/logs
    deploy:
      resources:
        limits:
          cpus: '0.5'
          memory: 512M
        reservations:
          cpus: '0.25'
          memory: 256M
```

### 3. .dockerignore

```
.git
.gitignore
__pycache__
*.pyc
*.pyo
*.pyd
.Python
env/
venv/
.venv/
.env
.vscode
.idea
*.log
logs/
```

### 4. requirements.txt

```
flask==2.0.1
openai==1.3.0
flask-wtf==1.0.0
flask-talisman==0.8.1
gunicorn==20.1.0
```

## EC2デプロイのための追加設定

### 1. EC2インスタンスのセキュリティグループ設定

```
# セキュリティグループ設定
- 名前: chatbot-app-sg
- 説明: Security group for chatbot application

インバウンドルール:
- HTTP (80): 0.0.0.0/0 (または特定のIP範囲)
- SSH (22): 管理用IPのみ (例: 社内IPレンジ)

アウトバウンドルール:
- すべてのトラフィック: 0.0.0.0/0 (または必要に応じて制限)
```

### 2. EC2起動スクリプト (user-data)

```bash
#!/bin/bash
# EC2インスタンス起動時に実行するスクリプト

# 必要なパッケージのインストール
apt-get update
apt-get install -y docker.io docker-compose git

# Dockerサービスの開始
systemctl start docker
systemctl enable docker

# アプリケーションディレクトリの作成
mkdir -p /opt/chatbot
cd /opt/chatbot

# Gitからコードをクローン
git clone https://github.com/a1344git/py03.git .

# 環境変数ファイルの作成
cat > .env << EOF
FLASK_APP=app.py
FLASK_ENV=production
SECRET_KEY=$(openssl rand -hex 32)
OPENAI_API_KEY=your_openai_api_key_here
EOF

# Dockerコンテナの起動
docker-compose up -d
```

### 3. 手動バックアップスクリプト

```bash
#!/bin/bash
# 手動バックアップスクリプト

# バックアップ日時
BACKUP_DATE=$(date +%Y%m%d_%H%M%S)

# バックアップディレクトリ
BACKUP_DIR="/opt/backups"
mkdir -p $BACKUP_DIR

# コードのバックアップ
cd /opt/chatbot
tar -czf $BACKUP_DIR/code_$BACKUP_DATE.tar.gz .

# Dockerボリュームのバックアップ（必要に応じて）
docker run --rm -v chatbot_logs:/logs -v $BACKUP_DIR:/backup alpine tar -czf /backup/logs_$BACKUP_DATE.tar.gz /logs

echo "バックアップが完了しました: $BACKUP_DIR/code_$BACKUP_DATE.tar.gz"
```

## EC2無料枠向け最適化

### 1. リソース使用量の最小化

```python
# app.py に追加
import gc

# メモリ使用量を定期的に最適化
@app.after_request
def cleanup(response):
    gc.collect()
    return response
```

### 2. Gunicornの最適化設定

```python
# gunicorn.conf.py - 新規ファイル
# 無料枠EC2向けの最適化設定

# ワーカー数を最小化
workers = 2
threads = 2

# ワーカーのタイムアウト設定
timeout = 120

# ワーカーの再起動設定
max_requests = 1000
max_requests_jitter = 50

# ログ設定
accesslog = '-'
errorlog = '-'
loglevel = 'info'

# メモリ使用量の最適化
worker_class = 'sync'
worker_tmp_dir = '/dev/shm'  # RAMディスクを使用
```

## セキュリティのベストプラクティス

1. **コンテナセキュリティ**
   - rootユーザーでアプリケーションを実行しない
   - 不要なパッケージをインストールしない
   - イメージを定期的に更新

2. **シークレット管理**
   - 環境変数を使用してシークレットを渡す
   - Docker Composeの環境変数ファイル(.env)をgitignoreに追加

3. **ネットワークセキュリティ**
   - 必要最小限のポートのみを公開
   - コンテナ間通信を制限

4. **リソース制限**
   - CPUとメモリの使用量を制限
   - ファイルアップロードサイズを制限

5. **ログとモニタリング**
   - コンテナログをホストに保存
   - 異常なアクティビティを監視

## 実装計画

1. **準備フェーズ**
   - 必要なファイル(Dockerfile, docker-compose.yml, .dockerignore)を作成
   - EC2セキュリティグループを設定

2. **コード変更フェーズ**
   - APIキー管理の改善
   - セキュリティヘッダーとCSRF保護の追加
   - ファイルアップロードセキュリティの強化
   - エラー処理とログ記録の改善
   - 環境設定管理の実装

3. **デプロイフェーズ**
   - EC2インスタンスの起動
   - 起動スクリプトの実行
   - Dockerコンテナのビルドと起動

4. **検証フェーズ**
   - アプリケーションの動作確認
   - セキュリティテスト
   - パフォーマンステスト

## 無料枠EC2の制約と対策

1. **メモリ制約 (1GB)**
   - メモリリークを防ぐためのガベージコレクション
   - Gunicornワーカー数の最小化
   - 不要なライブラリの削除

2. **CPU制約 (t2.micro)**
   - バーストパフォーマンスの効率的な使用
   - バックグラウンドタスクの最小化
   - 重い処理の分散

3. **ストレージ制約 (8GB)**
   - ログローテーションの実装
   - 一時ファイルの定期的なクリーンアップ
   - アップロードファイルの処理後の削除

4. **ネットワーク制約**
   - 大きなファイル転送の最小化
   - キャッシュの活用
   - 不要なAPIリクエストの削減
