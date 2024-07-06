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
    Configuration,
    MessagingApi,
    ApiClient,
    ReplyMessageRequest,
    TextMessage,
    ImageMessage)
from linebot.v3.exceptions import (
    InvalidSignatureError
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent,
)
import uvicorn
import google.generativeai as genai
from openai import OpenAI
from firebase import firebase

from utils import *


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

openai_client = OpenAI()

def get_all_acounts():
    account_path = ACCOUNT_PATH
    accounts = fdb.get(account_path, None)
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
        msg_type = event.message.type
        reply_msg = None
        if event.source.type != 'group':
            """
            Personal usage: to summarize, reply to for the group messagges
            """
            if msg_type != 'text':
                continue
            text = event.message.text
            user_id = event.source.user_id
            state_url = f'state/{user_id}'
            buf_url = f'buffer/{user_id}'
            chat_store_url = f'chat/{user_id}'
            unread_img_url = f'img/{user_id}'
            
            state = fdb.get(state_url, None)
            all_group_data = fdb.get(chat_store_url, None)
            action_list = [
                "delete_history",
                "get_summary",
                "get_reply",
                "get_images",
                "last_state",
                "finish"
            ]
            if state is None:
                state = -1
            
            if text == '__init__':
                """
                init the account
                """
                account_path = ACCOUNT_PATH
                accounts_list = get_all_acounts()
                print(accounts_list)
                if user_id in accounts_list:
                    reply_msg = "已啟用"
                else:
                    accounts_list.append(user_id)
                    fdb.put_async(account_path, None, accounts_list)
                    reply_msg = "成功啟用"
                # Add some basic introduction
                reply_msg += "\n" 
                state = -1
            elif text == 'get_groups':
                """
                get the group information
                """
                accounts_list = get_all_acounts()
                if user_id not in accounts_list:
                    reply_msg = "請先啟用"
                else:
                    if all_group_data is None:
                        reply_msg = '沒有任何群組的資料'
                    else:
                        group_name2id = {line_bot_api.get_group_summary(group_id).group_name: group_id for group_id in all_group_data.keys()}
                        reply_msg = '\n'.join(list(group_name2id.keys()))
                        reply_msg += '\n\n請選擇群組：'
                        state = 0
            elif text == 'summary':
                accounts_list = get_all_acounts()
                at_all = {}
                at_person = {}
                at_messages = []
                if user_id not in accounts_list:
                    reply_msg = "請先啟用"
                else:
                    if all_group_data is None:
                        reply_msg = '沒有任何群組的資料'
                    else:
                        for group_id, chat_history in all_group_data.items():
                            group_name = line_bot_api.get_group_summary(group_id).group_name
                            user_name = line_bot_api.get_group_member_profile(group_id, user_id).display_name
                            at_all[group_name] = 0
                            at_person[group_name] = 0
                            for chat in chat_history:
                                for sender, content in chat.items():
                                    if '@All ' in content:
                                        at_all[group_name] += 1
                                    elif f'@{user_name} ' in content:
                                        at_person[group_name] += 1
                                    else:
                                        continue
                                    at_messages.append(f'{group_name}: {sender}說 {content}')
                        at_messages = '\n'.join(at_messages)
                        at_plot = plot_at_count(at_all, at_person)
                        reply_msg = f"@ALL: {at_all}次, @YOU: {at_person}次\n {at_messages}"
                state = -1
            else:
                """
                mainly handle different states and choices
                """
                accounts_list = get_all_acounts()
                if user_id not in accounts_list:
                    reply_msg = "請先啟用"
                else:
                    if state == -1:
                        reply_msg = "請先選擇菜單"
                    elif state == 0:
                        group_name = text
                        group_name2id = {line_bot_api.get_group_summary(group_id).group_name: group_id for group_id in all_group_data.keys()}
                        group_id = group_name2id.get(group_name, None)
                        if group_id is None:
                            reply_msg = '不存在的群組'
                            state = -1
                        else:
                            """
                            Exist group -> delete chat history and use openai api (or gemini api) to summarize it.
                            """
                            state = 1
                            fdb.put_async(buf_url, None, group_id)
                            # menu of action list
                            reply_msg = "請選擇功能："
                    elif state == 1:
                        group_id = fdb.get(buf_url, None)
                        try:
                            text = action_list[int(text) - 1]
                        except:
                            reply_msg = "不要亂選ㄛ!!!"
                            
                        if text == "delete_history":
                            fdb.delete(chat_store_url, group_id)
                            
                        elif text == 'get_summary':
                            user_name = line_bot_api.get_group_member_profile(group_id, user_id).display_name
                            chat_history = all_group_data[group_id]
                            chat_history = parse_chat_hsitory(chat_history)
                            response = openai_client.chat.completions.create(
                                model="gpt-3.5-turbo",
                                messages=[
                                    {'role': 'system', 'content': '你的身分是一個整理聊天紀錄的機器人'},
                                    {'role': 'user', 'content': f'請幫我將以下的對話紀錄內容簡短的整理成20字以內的重點\n{chat_history}'}
                                ]
                            ).choices[0].message.content
                            reply_msg = f'{response}'
                            
                        elif text == 'get_reply':
                            suggest_reply =openai_client.chat.completions.create(
                                model="gpt-3.5-turbo",
                                messages=[
                                    {'role': 'system', 'content': '你的身分是負責回覆訊息的機器人'},
                                    {'role': 'user', 'content': f'我的身分是{user_name}，請幫我根據以下內容產生一句15字以內，符合我的風格且恰當的回覆\n{chat_history}'}]
                            ).choices[0].message.content
                            reply_msg = f'建議回覆:\n{suggest_reply}'
                            
                        elif text == 'get_images':
                            unread_img = fdb.get(unread_img_url, group_id)
                            if unread_img is None:
                                reply_msg = "沒有未讀取的照片"
                            else:
                                max_reply = 5
                                cnt = 0
                                for img in unread_img:
                                    contentUrl, previewUrl = img
                                    line_bot_api.reply_message(
                                        ReplyMessageRequest(
                                            reply_token=event.reply_token,
                                            messages=[ImageMessage(originalContentUrl=contentUrl, previewImageUrl=previewUrl)]
                                        ))
                                    cnt += 1
                                    if cnt == max_reply:
                                        break
                                unread_img = unread_img[cnt:]
                                fdb.put_async(unread_img_url, group_id, unread_img)
                            
                        elif text == 'last_state':
                            group_name2id = {line_bot_api.get_group_summary(group_id).group_name: group_id for group_id in all_group_data.keys()}
                            reply_msg = '\n'.join(list(group_name2id.keys()))
                            reply_msg += '\n\n請選擇群組：'
                            state = 0
                            
                        elif text == 'finish':
                            reply_msg = "已完成"
                            state = -1
            """
            Handle personal reply, menu...
            """
            if reply_msg is not None:
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text=reply_msg)]
                    ))
            fdb.put_async(state_url, None, state)
        else:
            """
            Group usage: for getting messages in group
            """
            print(msg_type)
            if msg_type == 'text':
                text = event.message.text
            elif msg_type == 'image':
                contentUrl = event.message.content_provider.original_content_url
                previewUrl = event.message.content_provider.preview_image_url
                text = '圖片:' + check_img_content(contentUrl)
            sender_id = event.source.user_id
            group_id = event.source.group_id
            message_sender = line_bot_api.get_group_member_profile(group_id, sender_id).display_name
            accounts_list = get_all_acounts()
            for account in accounts_list:
                try:
                    line_bot_api.get_group_member_profile(group_id, account)
                except:
                    continue
                chat_store_url = f'chat/{account}'
                unread_img_url = f'img/{account}'
                
                if account == sender_id:
                    fdb.delete(chat_store_url, group_id)
                    fdb.delete(unread_img_url, group_id)
                    continue
                
                chat_stored = fdb.get(chat_store_url, group_id)
                if chat_stored is None:
                    chat_stored = []
                chat_stored.append({message_sender: text})
                fdb.put_async(chat_store_url, group_id, chat_stored)
                
                if msg_type == 'image':
                    unread_img = fdb.get(unread_img_url, group_id)
                    if unread_img is None:
                        unread_img = []
                    unread_img.append((contentUrl, previewUrl))
                    fdb.put_async(unread_img_url, group_id, unread_img)
    return 'OK'

if __name__ == "__main__":
    port = int(os.environ.get('PORT', default=8080))
    debug = True if os.environ.get(
        'API_ENV', default='develop') == 'develop' else False
    logging.info('Application will start...')
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=debug)
