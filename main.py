import logging
import os
import re
import sys
if os.getenv('API_ENV') != 'production':
    from dotenv import load_dotenv

    load_dotenv()

from fastapi import FastAPI, HTTPException, Request
from datetime import datetime
from linebot.v3.webhook import WebhookParser
from linebot.v3.messaging import (
    AsyncApiClient,
    AsyncMessagingApi,
    Configuration,
    MessagingApi,
    ApiClient,
    ReplyMessageRequest,
    TextMessage)
from linebot.v3.exceptions import (
    InvalidSignatureError
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent,
)
import uvicorn
import requests
import google.generativeai as genai
from firebase import firebase


logging.basicConfig(level=os.getenv('LOG', 'WARNING'))
logger = logging.getLogger(__file__)

app = FastAPI()

channel_secret = os.getenv('LINE_CHANNEL_SECRET', None)
channel_access_token = os.getenv('LINE_CHANNEL_ACCESS_TOKEN', None)
if channel_secret is None:
    print('Specify LINE_CHANNEL_SECRET as environment variable.')
    sys.exit(1)
if channel_access_token is None:
    print('Specify LINE_CHANNEL_ACCESS_TOKEN as environment variable.')
    sys.exit(1)

configuration = Configuration(
    access_token=channel_access_token
)

async_api_client = ApiClient(configuration)
line_bot_api = MessagingApi(async_api_client)
parser = WebhookParser(channel_secret)

firebase_url = os.getenv('FIREBASE_URL')
gemini_key = os.getenv('GEMINI_API_KEY')


# Initialize the Gemini Pro API
genai.configure(api_key=gemini_key)


fdb = firebase.FirebaseApplication(firebase_url, None)



@app.post("/webhooks/line")
async def handle_callback(request: Request):
    signature = request.headers['X-Line-Signature']

    # get request body as text
    body = await request.body()
    body = body.decode()

    try:
        events = parser.parse(body, signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    for event in events:
        logging.info(event)
        if not isinstance(event, MessageEvent):
            continue
        if not isinstance(event.message, TextMessageContent):
            continue
        text = event.message.text
        user_id = event.source.user_id

        msg_type = event.message.type
        if msg_type == 'text':
            reply_msg = None
            if event.source.type != 'group':
                # user_chat_path = f'chat/personal/{user_id}'
                chat_store_path = f'chat/'
                all_group_data = fdb.get(chat_store_path, None)
                if all_group_data is None:
                    reply_msg = '沒有任何群組的資料'
                
                else:
                    group_name = text
                    group_name2id = {line_bot_api.get_group_summary(group_id).group_name: group_id for group_id in all_group_data.keys()}
                    group_id = group_name2id.get(group_name, None)
                    if group_id is None:
                        reply_msg = '不存在的群組'
                    else:
                        chat_history = all_group_data[group_id]
                        reply_msg = f'{chat_history}'
            else:
                group_id = event.source.group_id
                message_sender = line_bot_api.get_group_member_profile(group_id, user_id).display_name
                chat_store_path = f'chat/{group_id}'
                chat_stored = fdb.get(chat_store_path, None)
                
                if chat_stored is None:
                    chat_history = []
                else:
                    chat_history = chat_stored
                    
                chat_history.append({message_sender: text})
                fdb.put_async(chat_store_path, None, chat_history)
                
            if reply_msg is not None:
                await line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text=reply_msg)]
                    ))
    return 'OK'

if __name__ == "__main__":
    port = int(os.environ.get('PORT', default=8080))
    debug = True if os.environ.get(
        'API_ENV', default='develop') == 'develop' else False
    logging.info('Application will start...')
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=debug)
