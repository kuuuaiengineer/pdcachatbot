from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# --- 設定項目（.envから読み込み） ---
LINE_ACCESS_TOKEN = os.getenv('LINE_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET')
DIFY_API_KEY = os.getenv('DIFY_API_KEY')
DIFY_BASE_URL = os.getenv('DIFY_BASE_URL', 'https://api.dify.ai/v1')  # セルフホストなら.envで上書き

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_msg = event.message.text
    user_id = event.source.user_id

    # Dify APIを叩く
    headers = {
        'Authorization': f'Bearer {DIFY_API_KEY}',
        'Content-Type': 'application/json'
    }
    
    # LINEのメッセージをDifyの「query」として送信
    # ※プロンプト側で「Plan: Do:」を判別するように調整が必要です
    data = {
        "inputs": {}, # フォーム入力ではなく会話形式で送る場合
        "query": user_msg,
        "response_mode": "blocking",
        "user": user_id # LINEのユーザーIDを渡すと履歴が保持される
    }

    response = requests.post(f"{DIFY_BASE_URL}/chat-messages", headers=headers, data=json.dumps(data))
    
    if response.status_code == 200:
        result = response.json()
        reply_text = result.get('answer', 'エラーが発生しました。')
    else:
        reply_text = "Difyとの連携に失敗しました。"

    # LINEに返信する
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

if __name__ == "__main__":
    app.run(port=5000)