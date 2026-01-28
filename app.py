from flask import Flask, render_template, request, redirect, session, send_file, make_response, flash, jsonify
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
    update_units_content,
    DEFAULT_COMPOSITION_META # Add this line
)

from services.domain_bridge import (
    document_to_domain,
    domain_to_document
)

from services.services import update_intent, normalize_composition_elements, update_composition_elements
from services.services import attach_unit_scores
from services.services import extract_red_units, build_llm_prompt, build_composition_ideas_prompt
from intent_service import normalize_intent as normalize_intent_service # Rename to avoid conflict with services.py version

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


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form["email"]
        password = hash_password(request.form["password"])

        with get_user_conn() as conn:
            try:
                conn.execute(
                    "INSERT INTO users (email, password_hash, created_at) "
                    "VALUES (?, ?, datetime('now'))",
                    (email, password)
                )
                conn.commit()
                flash("登録が完了しました。ログインしてください。", "success")
                return redirect("/login")
            except conn.IntegrityError:
                flash("このメールアドレスは既に使用されています。", "error")
                return render_template("register.html"), 400

    return render_template("register.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ---------- ダッシュボード ----------

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session: # Removed data_loaded check
        return redirect("/dashboard")

    data = load_user_data(session["user_id"])
    documents = data.get("documents", [])
    
    user_config = {
        "llm": {
            "api_key": session.get("llm_api_key", ""),
            "model_name": session.get("llm_model_name", ""),
            "base_url": session.get("llm_base_url", "") # Retrieve base URL from session
        },
        "quantum": {
            "api_key": session.get("quantum_server_api_key", "")
        }
    }

    return render_template(
        "dashboard.html",
        documents=documents,
        doc_types=DOC_TYPE_INTENTS.keys(),
        user_config=user_config
    )

@app.route("/upload", methods=["POST"])
def upload():
    if "user_id" not in session: # Removed data_loaded check
        return redirect("/dashboard")

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
        file_content_bytes = file.read()
        try:
            uploaded_json_content = json.loads(file_content_bytes.decode('utf-8'))
        except UnicodeDecodeError:
            # Fallback for common non-UTF-8 encodings, e.g., Shift-JIS for Japanese
            uploaded_json_content = json.loads(file_content_bytes.decode('shift_jis'))
    except json.JSONDecodeError:
        flash("無効なJSONファイルです")
        return redirect("/dashboard")
    except UnicodeDecodeError:
        flash("ファイルのエンコーディングを認識できませんでした。UTF-8またはShift-JISで保存されていることを確認してください。")
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

@app.route("/save_config", methods=["POST"])
def save_config():
    if "user_id" not in session:
        flash("ログインしてください。", "error")
        return redirect("/login")

    # Store LLM config in session
    session["llm_api_key"] = request.form["llm_api_key"]
    session["llm_model_name"] = request.form["llm_model_name"]
    session["llm_base_url"] = request.form["llm_base_url"] # Store new base URL
    session["quantum_server_api_key"] = request.form["quantum_server_api_key"]
    
    flash("設定を保存しました。", "success")
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

    # Normalize document for both GET and POST requests
    normalize_intent_service(document)
    normalize_composition_elements(document)

    if request.method == "POST":
        # composition_elements の更新を処理
        if request.form.get("update_composition_elements"):
            update_composition_elements(document, request.form)
        else: # 既存の unit content 更新も残しておく
            update_units_content(document, request.form)
        
        save_user_data(session["user_id"], data)
        return redirect(f"/document/{doc_id}#composition") # 常に構成要素タブにリダイレクト

    labels = UI_LABELS[document["doc_type"]]

    # 日本語の doc_type を英語のキーにマッピング
    doc_type_mapping = {meta["label"]: doc_id for doc_id, meta in DEFAULT_COMPOSITION_META["doc_types"].items()}
    mapped_doc_type_id = doc_type_mapping.get(document["doc_type"])

    return render_template(
        "document.html",
        document=document,
        labels=labels,
        mapped_doc_type_id=mapped_doc_type_id # 追加
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
    normalize_intent_service(document) # services.py の normalize_intent との衝突を避けるためリネーム

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

from services.llm_client import call_llm # Import the generic LLM client


def mock_llm_call(prompt: str) -> dict:
    """Mocks a call to the LLM, returning a predefined set of suggestions."""
    return {
        "suggestions": [
            "（モック）登場人物が予期せぬ選択をする",
            "（モック）過去の出来事が現在の状況に影響を与える",
            "（モック）主人公が自身の価値観に疑問を抱く出来事",
            "（モック）新たな対立軸が生まれる",
            "（モック）結末を暗示する象徴的なアイテムが登場する"
        ]
    }

@app.route("/document/<doc_id>/generate_ideas", methods=["POST"])
def generate_composition_ideas(doc_id):
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    data = load_user_data(session["user_id"])
    document = find_document(data, doc_id)
    if document is None:
        return jsonify({"error": "Document not found"}), 404

    # Get LLM configuration from session
    llm_api_key = session.get("llm_api_key")
    llm_model_name = session.get("llm_model_name")
    llm_base_url = session.get("llm_base_url")

    # Fallback to mock if essential configuration is missing
    if (not llm_api_key and not llm_base_url) or not llm_model_name:
        prompt = build_composition_ideas_prompt(document)
        suggestions_dict = mock_llm_call(prompt)
        suggestions = suggestions_dict.get("suggestions", [])
        return jsonify({"suggestions": suggestions, "message": "LLM設定が不完全なため、モックデータを使用しました。"}), 200

    # Build prompt for LLM
    prompt = build_composition_ideas_prompt(document)
    
    try:
        # Call actual LLM using the dispatcher
        suggestions_dict = call_llm(llm_api_key, llm_model_name, prompt, base_url=llm_base_url)
        suggestions = suggestions_dict.get("suggestions", [])
        return jsonify({"suggestions": suggestions})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except RuntimeError as e:
        return jsonify({"error": f"LLM呼び出しエラー: {str(e)}", "message": "LLM呼び出しでエラーが発生しました。設定とプロンプトを確認してください。"}), 500
    except Exception as e:
        return jsonify({"error": f"予期せぬエラー: {str(e)}", "message": "予期せぬエラーが発生しました。"}), 500

@app.route("/document/<doc_id>/add_composition_element", methods=["POST"])
def add_composition_element(doc_id):
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = load_user_data(session["user_id"])
    document = find_document(data, doc_id)
    if document is None:
        return jsonify({"error": "Document not found"}), 404

    request_data = request.get_json()
    new_element_label = request_data.get("label")

    if not new_element_label:
        return jsonify({"error": "Label is required"}), 400

    # Find or create a user-editable category to add the suggestion to
    elements_data = document["composition_elements"]
    doc_type_specific_categories = elements_data["doc_type_specific"].setdefault("categories", [])
    common_categories = elements_data["common"].setdefault("categories", [])
    
    # Try to add to an editable doc_type_specific category first
    target_category = next((cat for cat in doc_type_specific_categories if cat.get("editable")), None)
    
    # If no editable doc_type_specific category, try editable common category
    if not target_category:
        target_category = next((cat for cat in common_categories if cat.get("editable")), None)

    # If still no editable category, create a new "AI提案" category under common
    if not target_category:
        ai_suggestions_category_id = "ai_suggestions_cat"
        target_category = next((cat for cat in common_categories if cat["id"] == ai_suggestions_category_id), None)
        if not target_category:
            target_category = {
                "id": ai_suggestions_category_id,
                "label": "AI提案",
                "editable": True,
                "elements": []
            }
            common_categories.append(target_category)
    
    target_elements = target_category.setdefault("elements", [])
    target_elements.append({
        "id": os.urandom(4).hex(), # Generate a unique ID for the new element
        "label": new_element_label,
        "value": "",
        "editable": True
    })

    save_user_data(session["user_id"], data)
    return jsonify({"message": "Composition element added successfully"})


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

