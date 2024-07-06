import matplotlib.pyplot as plt
import io
import os
import requests
from PIL import Image
import google.generativeai as genai
from typing import List

def plot_at_count(at_all_count: dict, at_person_count: dict):
    plt.bar([i + 1 for i in range(len(at_all_count))], at_all_count.values(), tick_label=at_all_count.keys(), width=0.4, color=['gray'], align='edge')
    plt.bar([i + 0.8 for i in range(len(at_all_count))], at_person_count.values(), width=0.4, color=['darkgray'])
    plt.legend(['@ALL', '@YOU'])
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    return buf.getvalue()

def check_img_content(img_data):
    genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
    image = Image.open(io.BytesIO(img_data))

    model = genai.GenerativeModel('gemini-pro-vision')
    response = model.generate_content([
        "你是一個重點整理機器人。若以下圖片包含文字，請整理文字重點。若沒有包含文字，請概述圖片內容成20字以內文字",
        image
    ])
    return response.text


def parse_chat_hsitory(chat_history: List[dict]):
    ret = ''
    for chat in chat_history:
        for sender, text in chat.items():
            ret += f"{sender}傳了 {text}\n"
    return ret