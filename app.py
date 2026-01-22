from flask import Flask, render_template, request, redirect, session, send_file
from datetime import timedelta
import os
import json

from db import init_user_db, get_user_conn
from auth import login
from security import hash_password
from user_files import load_user_data, save_user_data
from ui_labels import UI_LABELS
from intent_templates import COMMON_INTENTS, DOC_TYPE_INTENTS




from services.services import (
    create_document,
    find_document,
    update_units_content
)

from services.domain_bridge import (
    document_to_domain,
    domain_to_document
)

from services.services import update_intent
from services.services import attach_unit_scores
from services.services import extract_red_units, build_llm_prompt
from intent_service import normalize_intent

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
    session.clear()
    return redirect("/login")

# ---------- ダッシュボード ----------

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect("/login")

    data = load_user_data(session["user_id"])
    documents = data.get("documents", [])

    return render_template(
        "dashboard.html",
        documents=documents,
        doc_types=DOC_TYPE_INTENTS.keys()
    )

@app.route("/upload", methods=["POST"])
def upload():
    if "user_id" not in session:
        return redirect("/login")

    file = request.files["file"]
    data = json.load(file)

    save_user_data(session["user_id"], data)
    return redirect("/dashboard")

# ---------- ドキュメント ----------

@app.route("/document/create", methods=["POST"])
def document_create():
    if "user_id" not in session: # Removed data_loaded check
        return redirect("/dashboard")

    data = load_user_data(session["user_id"])

    document = create_document(
        data=data,
        title=request.form["title"],
        doc_type=request.form["doc_type"]
    )

    save_user_data(session["user_id"], data)
    return redirect(f"/document/{document['id']}")

@app.route("/document/<doc_id>", methods=["GET", "POST"])
def view_document(doc_id):
    if "user_id" not in session: # Removed data_loaded check
        return redirect("/dashboard")

    data = load_user_data(session["user_id"])
    document = find_document(data, doc_id)

    if document is None:
        return redirect("/dashboard")

    if request.method == "POST":
        update_units_content(document, request.form)
        save_user_data(session["user_id"], data)
        return redirect(f"/document/{doc_id}")

    if request.method == "GET":
        normalize_intent(document)

    labels = UI_LABELS[document["doc_type"]]

    return render_template(
        "document.html",
        document=document,
        labels=labels
    )


@app.route("/document/<doc_id>/intent", methods=["POST"])
def edit_intent(doc_id):
    if "user_id" not in session: # Removed data_loaded check
        return redirect("/dashboard")

    data = load_user_data(session["user_id"])
    document = find_document(data, doc_id)

    if document is None:
        return redirect("/dashboard")

    # ★ ここで正規化（重要）
    normalize_intent(document)

    # ★ Intent更新（削除・追加・保存すべて）
    update_intent(document, request.form)

    save_user_data(session["user_id"], data)
    return redirect(f"/document/{doc_id}")

@app.route("/document/<doc_id>/improve/<int:unit_index>", methods=["POST"])
def improve_unit(doc_id, unit_index):
    if "user_id" not in session: # Removed data_loaded check
        return redirect("/dashboard")

    data = load_user_data(session["user_id"])
    document = find_document(data, doc_id)
    if document is None:
        return redirect(f"/document/{doc_id}")

    units = document.get("units", [])
    if unit_index < 0 or unit_index >= len(units):
        return redirect(f"/document/{doc_id}")

    unit = units[unit_index]

    prompt = build_llm_prompt(document, unit)

    # 🔽 今は LLM を呼ばず、そのまま表示
    return f"<pre>{prompt}</pre>"


if __name__ == "__main__":
    app.run(debug=True)

