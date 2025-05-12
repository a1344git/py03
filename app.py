from flask import render_template, Flask, request, jsonify, redirect, url_for, flash
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
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Length, EqualTo, ValidationError
from pytz import timezone
import pytz

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

# DB初期化
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///chatapp.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# CSRF有効化を環境で自動切替
if os.environ.get('FLASK_ENV') == 'production':
    app.config['WTF_CSRF_ENABLED'] = True
else:
    app.config['WTF_CSRF_ENABLED'] = False  # 開発用: CSRFチェックを無効化

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Flask-WTF用のシークレットキー
app.config['SECRET_KEY'] = 'your_secret_key_here'  # 本番は環境変数で管理

# ユーザモデル
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# チャット履歴モデル
class ChatHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_user = db.Column(db.Boolean, default=True)
    timestamp = db.Column(db.DateTime, server_default=db.func.now())

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

@app.after_request
def cleanup(response):
    gc.collect()
    return response

# --- ユーザ登録フォーム ---
class RegisterForm(FlaskForm):
    username = StringField('ユーザー名', validators=[DataRequired(), Length(min=3, max=150)])
    password = PasswordField('パスワード', validators=[DataRequired(), Length(min=6)])
    confirm = PasswordField('パスワード(確認)', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('登録')

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user:
            raise ValidationError('このユーザー名は既に使われています。')

# --- ログインフォーム ---
class LoginForm(FlaskForm):
    username = StringField('ユーザー名', validators=[DataRequired()])
    password = PasswordField('パスワード', validators=[DataRequired()])
    submit = SubmitField('ログイン')

# --- ユーザ登録ルート ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        user = User(username=form.username.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('ユーザー登録が完了しました。ログインしてください。', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', form=form)

# --- ログインルート ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            flash('ログインしました', 'success')
            return redirect(url_for('index'))
        else:
            flash('ユーザー名またはパスワードが違います', 'danger')
    return render_template('login.html', form=form)

# --- ログアウトルート ---
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('ログアウトしました', 'info')
    return redirect(url_for('login'))

# --- チャット画面（index）ルート修正 ---
@app.route('/')
@login_required
def index():
    JST = timezone('Asia/Tokyo')
    histories = ChatHistory.query.filter_by(user_id=current_user.id, is_user=True).order_by(ChatHistory.id.desc()).limit(20).all()
    for h in histories:
        if h.timestamp and h.timestamp.tzinfo is None:
            h.timestamp = pytz.utc.localize(h.timestamp).astimezone(JST)
        elif h.timestamp:
            h.timestamp = h.timestamp.astimezone(JST)
    print(f"取得履歴: user_id={current_user.id}, count={len(histories)})")
    return render_template('mychatbot/index.html', histories=histories)

@app.route('/history')
@login_required
def history():
    JST = timezone('Asia/Tokyo')
    histories = ChatHistory.query.filter_by(user_id=current_user.id, is_user=True).order_by(ChatHistory.id.desc()).limit(20).all()
    for h in histories:
        if h.timestamp and h.timestamp.tzinfo is None:
            h.timestamp = pytz.utc.localize(h.timestamp).astimezone(JST)
        elif h.timestamp:
            h.timestamp = h.timestamp.astimezone(JST)
    return render_template('mychatbot/_history.html', histories=histories)

@app.route('/history/answer/<int:history_id>')
@login_required
def get_ai_answer(history_id):
    # 指定履歴の直後のAI回答を取得（idで比較）
    user_msg = ChatHistory.query.filter_by(id=history_id, user_id=current_user.id, is_user=True).first()
    if not user_msg:
        return jsonify({'answer': '該当履歴が見つかりません'}), 404
    ai_msg = ChatHistory.query.filter(
        ChatHistory.user_id==current_user.id,
        ChatHistory.is_user==False,
        ChatHistory.id > user_msg.id
    ).order_by(ChatHistory.id.asc()).first()
    if not ai_msg:
        return jsonify({'answer': 'AI回答が見つかりません'}), 404
    return jsonify({'answer': ai_msg.message})

@app.errorhandler(Exception)
def handle_exception(e):
    app.logger.error(f"Unhandled exception: {str(e)}", exc_info=True)
    if os.environ.get('FLASK_ENV') == 'production':
        return jsonify({'message': 'サーバーエラーが発生しました。管理者に連絡してください。'}), 500
    else:
        return jsonify({'message': f'エラー: {str(e)}'}), 500


@app.route('/submit', methods=['POST'])
@login_required
def submit():
    generated_text = ""
    user_input = request.form.get('message')
    session_mode = request.form.get('session_mode')
    IsNewConversation = True if session_mode == 'new' else False
    uploaded_file = request.files.get('file')
    file_base64 = None
    if uploaded_file:
        file_content = uploaded_file.read()
        file_base64 = base64.b64encode(file_content).decode('utf-8')
        if uploaded_file.content_type == 'application/pdf':
            generated_text = resapimodule.get_pdf_search(
                user_input, uploaded_file.filename,uploaded_file.content_type, file_base64, IsNewChat=IsNewConversation)
        elif uploaded_file.content_type.startswith('image/'):
            generated_text = resapimodule.get_image_search(
                usequery=user_input, 
                filename=uploaded_file.filename, 
                contexttype=uploaded_file.content_type, 
                filebase64=file_base64, 
                IsNewChat=IsNewConversation)
        else:
            generated_text = resapimodule.get_pdf_search(
                usequery=user_input, 
                filename=uploaded_file.filename, 
                contexttype=uploaded_file.content_type, 
                filebase64=file_base64, 
                IsNewChat=IsNewConversation)
    else:
        generated_text = resapimodule.get_search_byresponse(user_input, IsNewChat=IsNewConversation)

    # チャット履歴をDBに保存（ユーザ発言・AI応答）
    from app import db, ChatHistory
    if current_user.is_authenticated:
        db.session.add(ChatHistory(user_id=current_user.id, message=user_input, is_user=True))
        db.session.add(ChatHistory(user_id=current_user.id, message=generated_text, is_user=False))
        db.session.commit()
        print(f"履歴保存: user_id={current_user.id}, user_input={user_input}, ai={generated_text}")
    else:
        print("未ログインのため履歴保存せず")

    return jsonify({'message': generated_text})

# ログインマネージャ
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
# app.run(debug=True)
