import json, os

BASE_DIR = "user_data"

def user_dir(user_id):
    path = os.path.join(BASE_DIR, user_id)
    os.makedirs(path, exist_ok=True)
    return path

def save_user_data(user_id, data):
    with open(os.path.join(user_dir(user_id), "working.json"),
              "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_user_data(user_id):
    path = os.path.join(user_dir(user_id), "working.json")
    if not os.path.exists(path):
        return {"documents": []}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
