from firebase import firebase

def get_msg_id(fdb: firebase.FirebaseApplication, chat_url):
    msg_ids = fdb.get(chat_url, None)
    if len(msg_ids) == 0:
        return 0
    msg_ids = msg_ids.keys().sort()
    return msg_ids[-1] + 1