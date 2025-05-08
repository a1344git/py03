from flask import render_template, Flask, request, jsonify
from datetime import datetime  # datetime をインポート
import resapimodule
import base64
import os
import logging
import sys
import gc
from werkzeug.utils import secure_filename
from flask_wtf.csrf import CSRFProtect
from flask_talisman import Talisman
from config import config

app = Flask(__name__)

config_name = os.environ.get('FLASK_ENV') or 'default'
app.config.from_object(config[config_name])

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

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)  # コンテナログをstdoutに出力
    ]
)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

@app.after_request
def cleanup(response):
    gc.collect()
    return response


@app.route('/')
def index():
    return render_template('mychatbot/index.html', csrf_token=csrf.generate_csrf())

@app.errorhandler(Exception)
def handle_exception(e):
    app.logger.error(f"Unhandled exception: {str(e)}", exc_info=True)
    if os.environ.get('FLASK_ENV') == 'production':
        return jsonify({'message': 'サーバーエラーが発生しました。管理者に連絡してください。'}), 500
    else:
        return jsonify({'message': f'エラー: {str(e)}'}), 500


@app.route('/submit', methods=['POST'])
def submit():
    generated_text = ""


    # HTMLフォームから入力メッセージを取得
    user_input = request.form.get('message')
    session_mode = request.form.get('session_mode')
    IsNewConversation = True
    if session_mode == 'new':
        IsNewConversation = True
    else:
        IsNewConversation = False

    # アップロードされたファイルを取得
    uploaded_file = request.files.get('file')
    file_base64 = None  # Base64エンコードされたファイルデータを格納する変数
    
    if uploaded_file and uploaded_file.filename:
        if not allowed_file(uploaded_file.filename):
            app.logger.warning(f"サポートされていないファイル形式: {uploaded_file.filename}")
            return jsonify({'message': 'サポートされていないファイル形式です'})
            
        filename = secure_filename(uploaded_file.filename)
        
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        uploaded_file.save(file_path)
        
        try:
            # ファイルを読み取り、Base64に変換
            with open(file_path, 'rb') as f:
                file_content = f.read()
                file_base64 = base64.b64encode(file_content).decode('utf-8')
                
            app.logger.info(f"ファイルがアップロードされました: {filename}")
            
            if uploaded_file.content_type == 'application/pdf':
                generated_text = resapimodule.get_pdf_search(
                    user_input, filename, uploaded_file.content_type, file_base64, IsNewChat=IsNewConversation)
                    
            elif uploaded_file.content_type.startswith('image/'):
                generated_text = resapimodule.get_image_search(
                    usequery=user_input, 
                    filename=filename, 
                    contexttype=uploaded_file.content_type, 
                    filebase64=file_base64, 
                    IsNewChat=IsNewConversation)
                    
            else:
                generated_text = resapimodule.get_pdf_search(
                    usequery=user_input, 
                    filename=filename, 
                    contexttype=uploaded_file.content_type, 
                    filebase64=file_base64, 
                    IsNewChat=IsNewConversation)
                    
        except Exception as e:
            app.logger.error(f"ファイル処理中にエラーが発生しました: {str(e)}", exc_info=True)
            return jsonify({'message': 'ファイル処理中にエラーが発生しました'})
            
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)
                
    else:
        try:
            generated_text = resapimodule.get_search_byresponse(user_input, IsNewChat=IsNewConversation)
        except Exception as e:
            app.logger.error(f"テキスト処理中にエラーが発生しました: {str(e)}", exc_info=True)
            return jsonify({'message': 'テキスト処理中にエラーが発生しました'})

    return jsonify({'message': generated_text})

# app.run(debug=True)
