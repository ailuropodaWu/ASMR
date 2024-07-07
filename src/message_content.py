action_trans = {
    "delete_history": "刪除紀錄",
    "get_summary": "產生摘要",
    "get_reply": "產生回覆",
    "get_images": "讀取照片",
    "last_state": "上一步",
    "finish": "結束",
}

emoji_list = [
    # (productId, emojiId)
    ("5ac21a8c040ab15980c9b43f", "053"), # 1
    ("5ac21a8c040ab15980c9b43f", "054"), # 2
    ("5ac21a8c040ab15980c9b43f", "055"), # 3
    ("5ac21a8c040ab15980c9b43f", "056"), # 4
    ("5ac21a8c040ab15980c9b43f", "057"), # 5
    ("5ac21a8c040ab15980c9b43f", "058"), # 6
    ("5ac21a8c040ab15980c9b43f", "059"), # 7
    ("5ac21a8c040ab15980c9b43f", "060"), # 8
    ("5ac21a8c040ab15980c9b43f", "061"), # 9
    ("5ac21a8c040ab15980c9b43f", "062"), # 0
]
def get_action_string(action_list, use_emoji=False):
    if use_emoji:
        action_str_list = [f'{action_trans[action]}' for action in action_list]
    else:
        action_str_list = [f'{i+1}. {action_trans[action]}' for i, action in enumerate(action_list)]
    return '\n'.join(action_str_list)

    
def get_emojis(e_id, index):
    if e_id >= len(emoji_list):
        return None
    product_id, emoji_id = emoji_list[e_id]
    return {"index": index, "productId": product_id, "emojiId": emoji_id}