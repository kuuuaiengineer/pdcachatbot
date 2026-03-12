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
    # streaming: Agentアシスタント対応 / blocking: チャットアプリ向け
    data = {
        "inputs": {},
        "query": user_msg,
        "response_mode": "streaming",
        "user": user_id
    }

    try:
        response = requests.post(
            f"{DIFY_BASE_URL}/chat-messages",
            headers=headers,
            data=json.dumps(data),
            timeout=120,
            stream=True
        )
        
        if response.status_code == 200:
            # streamingレスポンスをパース（Chat: message / Agent: agent_message）
            reply_text = ""
            for line in response.iter_lines():
                if line and line.startswith(b'data: '):
                    try:
                        payload = line[6:].decode()
                        if payload.strip() == '[DONE]':
                            break
                        chunk = json.loads(payload)
                        ev = chunk.get('event')
                        if ev in ('message', 'agent_message'):
                            reply_text += chunk.get('answer', '')
                        elif ev == 'message_end':
                            break
                    except (json.JSONDecodeError, KeyError):
                        continue
            if not reply_text:
                reply_text = "応答を取得できませんでした。"
        else:
            error_detail = response.text
            try:
                err_json = response.json()
                error_detail = err_json.get('message', error_detail)
            except Exception:
                pass
            print(f"[Dify Error] status={response.status_code}, body={error_detail}")
            reply_text = f"Difyとの連携に失敗しました。（{response.status_code}）"
    except requests.exceptions.RequestException as e:
        print(f"[Dify Error] Request failed: {e}")
        reply_text = "Difyとの連携に失敗しました。（通信エラー）"

    # LINEに返信する
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)