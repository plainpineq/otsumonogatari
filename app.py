from flask import Flask, render_template, request, redirect, session, send_file, make_response, flash
from datetime import timedelta
import os
import json
import io
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

    if 'file' not in request.files:
        flash("ファイルがありません")
        return redirect("/dashboard")

    file = request.files["file"]

    if file.filename == '':
        flash("ファイルが選択されていません")
        return redirect("/dashboard")

    # Assuming 'file' is not empty at this point, if it passes previous checks.
    # The 'if not file:' check is now less critical given the above.

    # Load the uploaded JSON data
    try:
        uploaded_json_content = json.load(file)
    except json.JSONDecodeError:
        flash("無効なJSONファイルです")
        return redirect("/dashboard")

    # Validate that the uploaded content is a dictionary and looks like a document
    # (e.g., has a 'title' key)
    if not isinstance(uploaded_json_content, dict) or "title" not in uploaded_json_content:
        flash("アップロードされたファイルは有効なドキュメント形式ではありません。'title'キーが見つかりません。")
        return redirect("/dashboard")

    # Load existing user data
    existing_data = load_user_data(session["user_id"])
    
    # Ensure 'documents' key exists and is a list
    if "documents" not in existing_data or not isinstance(existing_data["documents"], list):
        existing_data["documents"] = []

    # Append the new document to the existing list
    existing_data["documents"].append(uploaded_json_content)

    # Save the updated user data
    save_user_data(session["user_id"], existing_data)
    flash("ファイルをアップロードしました。")
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

@app.route("/document/<doc_id>/download", methods=["GET"])
def download_document(doc_id):
    if "user_id" not in session:
        return redirect("/login")

    data = load_user_data(session["user_id"])
    document = find_document(data, doc_id)

    if document is None:
        return redirect("/dashboard")

    document_json = json.dumps(document, ensure_ascii=False, indent=2)
    
    # Use io.BytesIO to create an in-memory file
    file_data = io.BytesIO(document_json.encode('utf-8'))
    
    # Use send_file for robust downloading
    response = send_file(
        file_data,
        mimetype='application/json',
        as_attachment=True,
        download_name=f"{document['title']}.json"
    )
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

if __name__ == "__main__":
    app.run(debug=True)

