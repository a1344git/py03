from flask import render_template, Flask, request, jsonify
from datetime import datetime  # datetime をインポート
import resapimodule
import base64

app = Flask(__name__)


@app.route('/')
def index():
    return render_template('mychatbot/index.html')


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
    if uploaded_file:
        # ファイルを読み取り、Base64に変換
        file_content = uploaded_file.read()  # ファイルの内容をバイナリで読み取る
        file_base64 = base64.b64encode(file_content).decode(
            'utf-8')  # Base64エンコードして文字列に変換
        print(f"ファイルがアップロードされました: {uploaded_file.filename}")
        print(f"Base64エンコードされたデータ: {file_base64[:100]}...")  # データの一部を表示

        if uploaded_file.content_type == 'application/pdf':
            generated_text = resapimodule.get_pdf_search(
                user_input, uploaded_file.filename,uploaded_file.content_type, file_base64, IsNewChat=IsNewConversation)  # ファイルを調べるAPIを呼び出す

        elif uploaded_file.content_type.startswith('image/'):
            generated_text = resapimodule.get_image_search(
                usequery=user_input, 
                filename=uploaded_file.filename, 
                contexttype=uploaded_file.content_type, 
                filebase64=file_base64, 
                IsNewChat=IsNewConversation)  # 画像を調べるAPIを呼び出す

        else:
            generated_text = resapimodule.get_pdf_search(
                usequery=user_input, 
                filename=uploaded_file.filename, 
                contexttype=uploaded_file.content_type, 
                filebase64=file_base64, 
                IsNewChat=IsNewConversation)
            # generated_text = f"サポートされていないファイル形式です: {uploaded_file.content_type}"

    else:
        generated_text = resapimodule.get_search_byresponse(user_input, IsNewChat=IsNewConversation)

    return jsonify({'message': generated_text})

# app.run(debug=True)
