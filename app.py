from flask import Flask, render_template, request, redirect, session, send_file
from datetime import timedelta
import os
import json

from db import init_user_db, get_user_conn
from auth import login
from security import hash_password
from user_files import load_user_data, save_user_data
from ui_labels import UI_LABELS
from structure_templates import STRUCTURE_TEMPLATES

app = Flask(__name__)
app.secret_key = "storyforge-secret"
app.permanent_session_lifetime = timedelta(hours=2)

init_user_db()

# ---------- 認証 ----------

@app.route("/")
def root():
    return redirect("/login")


@app.route("/login", methods=["GET", "POST"])
def login_view():
    return login()


@app.route("/register", methods=["POST"])
def register():
    email = request.form["email"]
    password = hash_password(request.form["password"])

    with get_user_conn() as conn:
        conn.execute(
            "INSERT INTO users (email, password_hash, created_at) "
            "VALUES (?, ?, datetime('now'))",
            (email, password)
        )
        conn.commit()

    return redirect("/login")


@app.route("/logout")
def logout():
    user_id = session.get("user_id")
    path = f"user_data/{user_id}/working.json"

    session.clear()

    if user_id and os.path.exists(path):
        return send_file(
            path,
            as_attachment=True,
            download_name="storyforge_data.json"
        )

    return redirect("/login")

# ---------- ダッシュボード ----------

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect("/login")

    documents = []

    if session.get("data_loaded"):
        data = load_user_data(session["user_id"])
        documents = data.get("documents", [])

    return render_template(
        "dashboard.html",
        documents=documents,
        data_loaded=session.get("data_loaded", False)
    )


@app.route("/upload", methods=["POST"])
def upload():
    if "user_id" not in session:
        return redirect("/login")

    file = request.files["file"]
    data = json.load(file)

    save_user_data(session["user_id"], data)
    session["data_loaded"] = True

    return redirect("/dashboard")


# ---------- ドキュメント ----------

@app.route("/document/create", methods=["POST"])
def create_document():
    if "user_id" not in session or not session.get("data_loaded"):
        return redirect("/dashboard")

    data = load_user_data(session["user_id"])

    doc_type = request.form["doc_type"]

    doc = {
        "id": os.urandom(4).hex(),
        "title": request.form["title"],
        "doc_type": doc_type,
        "intent": {},
        "units": [
            {"title": t, "content": ""}
            for t in STRUCTURE_TEMPLATES[doc_type]
        ],
        "entities": []
    }

    data["documents"].append(doc)
    save_user_data(session["user_id"], data)

    return redirect("/dashboard")


@app.route("/document/<doc_id>", methods=["GET", "POST"])
def view_document(doc_id):
    if "user_id" not in session or not session.get("data_loaded"):
        return redirect("/dashboard")

    data = load_user_data(session["user_id"])

    document = next(
        (d for d in data.get("documents", []) if d["id"] == doc_id),
        None
    )

    if document is None:
        return redirect("/dashboard")

    # ---- 保存処理（POST）----
    if request.method == "POST":
        for i, unit in enumerate(document["units"]):
            unit["content"] = request.form.get(f"unit_{i}", "")

        save_user_data(session["user_id"], data)
        return redirect(f"/document/{doc_id}")

    labels = UI_LABELS[document["doc_type"]]

    return render_template(
        "document.html",
        document=document,
        labels=labels
    )


if __name__ == "__main__":
    app.run(debug=True)
