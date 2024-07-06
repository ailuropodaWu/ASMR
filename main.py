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
    TextMessage,
    RichMenuRequest)
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
from typing import List


ACCOUNT_PATH = 'accounts/'

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

configuration = Configuration(access_token=channel_access_token)
api_client = ApiClient(configuration)
line_bot_api = MessagingApi(api_client)
parser = WebhookParser(channel_secret)

firebase_url = os.getenv('FIREBASE_URL')
fdb = firebase.FirebaseApplication(firebase_url, None)

gemini_key = os.getenv('GEMINI_API_KEY')
genai.configure(api_key=gemini_key)
model = genai.GenerativeModel('gemini-1.5-pro')

def parse_chat_hsitory(chat_history: List[dict]):
    ret = ''
    for chat in chat_history:
        for sender, text in chat.items():
            ret += f"{sender}說{text}\n"
    return ret

def get_all_acounts():
    accout_path = ACCOUNT_PATH
    accounts = fdb.get(accout_path, None)
    return [] if accounts is None else accounts

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
                """
                Personal usage: to summarize, reply to for the group messagges
                """
                if text == '__init__':
                    """
                    init the account
                    """
                    accout_path = ACCOUNT_PATH
                    accounts_list = get_all_acounts()
                    print(accounts_list)
                    if user_id in accounts_list:
                        reply_msg = "已啟用"
                    else:
                        accounts_list.append(user_id)
                        fdb.put_async(accout_path, None, accounts_list)
                        reply_msg = "成功啟用"
                elif text == '__group__':
                    """
                    get the group information
                    """
                    accounts_list = get_all_acounts()
                    if user_id not in accounts_list:
                        reply_msg = "請先啟用"
                    else:
                        chat_store_path = f'chat/{user_id}'
                        all_group_data = fdb.get(chat_store_path, None)
                        if all_group_data is None:
                            reply_msg = '沒有任何群組的資料'
                        else:
                            group_name2id = {line_bot_api.get_group_summary(group_id).group_name: group_id for group_id in all_group_data.keys()}
                            reply_msg = '\n'.join(list(group_name2id.keys()))
                elif text == '__reply__':
                    """
                    generate reply for specific group
                    """
                    accounts_list = get_all_acounts()
                    if user_id not in accounts_list:
                        reply_msg = "請先啟用"
                    else:
                        pass
                elif text == '__summary__':
                    accounts_list = get_all_acounts()
                    at_all = 0
                    at_person = 0
                    at_messages = []
                    if user_id not in accounts_list:
                        reply_msg = "請先啟用"
                    else:
                        chat_store_path = f'chat/{user_id}'
                        all_group_data = fdb.get(chat_store_path, None)
                        if all_group_data is None:
                            reply_msg = '沒有任何群組的資料'
                        else:
                            for group_id, chat_history in all_group_data.items():
                                group_name = line_bot_api.get_group_summary(group_id).group_name
                                user_name = line_bot_api.get_group_member_profile(group_id, user_id).display_name
                                for chat in chat_history:
                                    for sender, content in chat.items():
                                        if '@All ' in content:
                                            at_all += 1
                                            at_messages.append({sender: content})
                                        elif f'@{user_name} ' in content:
                                            at_person += 1
                                            at_messages.append({sender: content})
                            reply_msg = f"@ALL: {at_all}次, @YOU: {at_person}次\n{parse_chat_hsitory(at_messages)}"
                else:
                    """
                    mainly handle getting summary of specific group
                    """
                    accounts_list = get_all_acounts()
                    if user_id not in accounts_list:
                        reply_msg = "請先啟用"
                    else:
                        chat_store_path = f'chat/{user_id}'
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
                                """
                                Exist group -> delete chat history and use openai api (or gemini api) to summarize it.
                                """
                                fdb.delete(chat_store_path, group_id)
                                chat_history = all_group_data[group_id]
                                chat_history = parse_chat_hsitory(chat_history)
                                response = model.generate_content(f'請幫我將以下的對話紀錄內容整理成重點\n{chat_history}')
                                reply_msg = response.text
            else:
                """
                Group usage: for getting messages in group
                """
                accounts_list = get_all_acounts()
                group_id = event.source.group_id
                message_sender = line_bot_api.get_group_member_profile(group_id, user_id).display_name
                for accout in accounts_list:
                    try:
                        line_bot_api.get_group_member_profile(group_id, accout)
                    except:
                        continue
                    chat_store_path = f'chat/{accout}'
                    chat_stored = fdb.get(chat_store_path, group_id)
                    
                    if chat_stored is None:
                        chat_history = []
                    else:
                        chat_history = chat_stored
                        
                    chat_history.append({message_sender: text})
                    fdb.put_async(chat_store_path, group_id, chat_history)
                
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
