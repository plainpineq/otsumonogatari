from flask import Flask, render_template, request, redirect, session, send_file, make_response, flash, jsonify
from datetime import timedelta, datetime
import os
import json
import io
import glob
import pandas as pd

from db import init_user_db, get_user_conn
from auth import login
from security import hash_password
from user_files import load_user_data, save_user_data, get_user_data_path

def _reset_generation_counter(user_id: str):
    session[f"generation_counter_{user_id}"] = 0

def _get_next_generation_number(user_id: str) -> int:
    if f"generation_counter_{user_id}" not in session:
        _reset_generation_counter(user_id)
    session[f"generation_counter_{user_id}"] += 1
    return session[f"generation_counter_{user_id}"]


from ui_labels import UI_LABELS
from intent_templates import COMMON_INTENTS, DOC_TYPE_INTENTS
from lm_input import build_composition_ideas_prompt, mock_llm_call, build_title_plot_proposals_prompt

# Helper function for cleaning up old generated files
def _cleanup_old_generated_files(user_id: str):
    user_data_dir = get_user_data_path(user_id)
    if not os.path.exists(user_data_dir):
        return

    # Patterns for files to delete
    patterns = [
        os.path.join(user_data_dir, "generated_prompt*.md"), # `_` を削除し、より広い範囲にマッチ
        os.path.join(user_data_dir, "generated_llm*.txt"),  # `_` を削除し、より広い範囲にマッチ
        os.path.join(user_data_dir, "generated_llm*.json") # `_` を削除し、より広い範囲にマッチ
    ]

    for pattern in patterns:
        for file_path in glob.glob(pattern):
            try:
                os.remove(file_path)
                print(f"Cleaned up old generated file: {file_path}")
            except PermissionError as e:
                print(f"ERROR: Permission denied when deleting {file_path}: {e}")
                # ここではflashはしない。バックグラウンド処理のため。
            except OSError as e:
                print(f"Error deleting file {file_path}: {e}")

from services.services import (
    create_document,
    find_document,
    update_units_content,
    update_intent,
    normalize_composition_elements,
    update_composition_elements,
    DEFAULT_COMPOSITION_META
)
from services.domain_bridge import (
    document_to_domain,
    domain_to_document
)
from intent_service import normalize_intent as normalize_intent_service
from semantic_labeler import label_suggestions
from feature_extractor import FeatureExtractor
from element_fitter import apply_fit_to_candidates




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
    
    # Get persistent server configurations
    llm_servers = data.get("llm_servers", {})
    quantum_server = data.get("quantum_server", {})

    # Ensure all roles have a default dictionary to prevent template errors
    for role in ["generation", "evaluation", "drafting"]:
        llm_servers.setdefault(role, {})

    user_config = {
        "llm_servers": llm_servers,
        "quantum_server": quantum_server,
        "suggestion_count": session.get("suggestion_count", 3)
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

@app.route("/update_suggestion_count", methods=["POST"])
def update_suggestion_count():
    if "user_id" not in session:
        flash("ログインしてください。", "error")
        return redirect("/login")

    try:
        suggestion_count = int(request.form["suggestion_count"])
        if not (1 <= suggestion_count <= 5):
            raise ValueError("提案個数は1から5の範囲で指定してください。")
        session["suggestion_count"] = suggestion_count
        flash("提案個数を保存しました。", "success")
    except ValueError as e:
        flash(f"エラー: {e}", "error")
    except Exception as e:
        flash(f"予期せぬエラーが発生しました: {e}", "error")
    
    return redirect("/dashboard")


@app.route("/save_servers_config", methods=["POST"])
def save_servers_config():
    if "user_id" not in session:
        flash("ログインしてください。", "error")
        return redirect("/login")

    data = load_user_data(session["user_id"])
    
    # --- LLMサーバー設定の解析 ---
    llm_servers = {}
    roles = ["generation", "evaluation", "drafting"]
    for role in roles:
        role_config = {
            "provider": request.form.get(f"llm_servers[{role}][provider]", "gemini"),
            "api_key": request.form.get(f"llm_servers[{role}][api_key]", ""),
            "model_name": request.form.get(f"llm_servers[{role}][model_name]", ""),
            "base_url": request.form.get(f"llm_servers[{role}][base_url]", ""),
            "temperature": request.form.get(f"llm_servers[{role}][temperature]", "0.7"),
            "max_tokens": request.form.get(f"llm_servers[{role}][max_tokens]", "2048"),
        }
        # providerに応じたデフォルトモデル名の設定
        if role_config["provider"] == "gemini" and not role_config["model_name"]:
            role_config["model_name"] = "gemini-pro"
        elif role_config["provider"] == "chatgpt" and not role_config["model_name"]:
            role_config["model_name"] = "gpt-4o-mini"
            
        llm_servers[role] = role_config

    # --- 量子サーバー設定の解析 ---
    quantum_server = {
        "api_key": request.form.get("quantum_server[api_key]", "")
    }

    # --- 保存 ---
    data["llm_servers"] = llm_servers
    data["quantum_server"] = quantum_server
    
    save_user_data(session["user_id"], data)
    
    flash("サーバー設定を保存しました。", "success")
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
        # composition_elements の更新を処理
        if request.form.get("update_composition_elements"):
            update_composition_elements(document, request.form)
        else: # 既存の unit content 更新も残しておく
            update_units_content(document, request.form)
        
        # Ensure normalization happens AFTER updates/deletions are processed
        normalize_intent_service(document) # Re-normalize intent after any potential changes
        normalize_composition_elements(document) # Re-normalize composition elements after any potential changes

        save_user_data(session["user_id"], data)
        return redirect(f"/document/{doc_id}#composition") # 常に構成要素タブにリダイレクト

    # GETリクエストの場合も、テンプレートに渡す前にcomposition_elementsを正規化
    normalize_composition_elements(document)

    labels = UI_LABELS[document["doc_type"]]

    # 日本語の doc_type を英語のキーにマッピング
    doc_type_mapping = {meta["label"]: doc_id for doc_id, meta in DEFAULT_COMPOSITION_META["doc_types"].items()}
    mapped_doc_type_id = doc_type_mapping.get(document["doc_type"])

    # Ensure all expected document keys are present for the template to avoid Undefined errors
    document.setdefault("llm_suggestions", [])
    document.setdefault("semantic_labels", [])
    document.setdefault("numerical_features", [])
    document.setdefault("fit_results", [])
    document.setdefault("composition_elements", {})
    document.setdefault("composition_meta", {})
    document.setdefault("intent", {"fields": {}}) # Add default for intent
    
    response = make_response(render_template(
        "document.html",
        document=document,
        labels=labels,
        mapped_doc_type_id=mapped_doc_type_id
    ))
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


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


from services.llm_client import call_llm # Import the generic LLM client


# ====================================================================
# NEW STAGED GENERATION FLOW (STEP 1, 2, 3)
# ====================================================================

@app.route("/document/<doc_id>/generate_proposals", methods=["POST"])
def generate_proposals(doc_id):
    """
    STEP 1: Generate initial Title and Plot proposals.
    """
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    data = load_user_data(session["user_id"])
    document = find_document(data, doc_id)
    if document is None:
        return jsonify({"error": "Document not found"}), 404

    # Cleanup old files and reset counter for a new full generation cycle
    _cleanup_old_generated_files(session["user_id"])
    _reset_generation_counter(session["user_id"])
    
    current_generation_number = _get_next_generation_number(session["user_id"])
    suffix = f"_{current_generation_number}_proposals"

    # Get LLM config
    llm_servers = data.get("llm_servers", {})
    generation_config = llm_servers.get("generation", {})
    llm_provider = generation_config.get("provider")
    llm_api_key = generation_config.get("api_key")
    llm_model_name = generation_config.get("model_name")
    llm_base_url = generation_config.get("base_url")
    suggestion_count = session.get("suggestion_count", 3)

    print(f"[LLM] PROVIDER: {llm_provider}: Model: {llm_model_name}")

    is_config_incomplete = not llm_provider or not llm_model_name or \
                           (llm_provider in ["gemini", "chatgpt"] and not llm_api_key) or \
                           (llm_provider == "other" and not llm_base_url)

    if is_config_incomplete:
        # Mock call if config is incomplete
        return jsonify({
            "suggestions": [
                {"category": "基本設定", "elements": {"題名": [f"模擬タイトル案{i+1}" for i in range(suggestion_count)]}},
                {"category": "基本設定", "elements": {"あらすじ": [f"模擬プロット案{i+1}: これはモックデータです。" for i in range(suggestion_count)]}}
            ],
            "message": "LLM設定が不完全なため、モックデータを使用しました。"
        }), 200

    try:
        prompt = build_title_plot_proposals_prompt(document, DEFAULT_COMPOSITION_META, session["user_id"], suffix=suffix, suggestion_count=suggestion_count)
        raw_text, suggestions_dict = call_llm(llm_api_key, llm_model_name, prompt, llm_provider, base_url=llm_base_url)
        
        # Save raw and structured responses
        user_data_dir = get_user_data_path(session["user_id"])
        with open(os.path.join(user_data_dir, f"generated_llm{suffix}.txt"), "w", encoding="utf-8") as f:
            f.write(raw_text)
        with open(os.path.join(user_data_dir, f"generated_llm{suffix}.json"), "w", encoding="utf-8") as f:
            json.dump(suggestions_dict, f, ensure_ascii=False, indent=2)

        return jsonify(suggestions_dict)

    except (ValueError, RuntimeError, Exception) as e:
        return jsonify({"error": f"LLM呼び出し中にエラーが発生しました: {str(e)}"}), 500


@app.route("/document/<doc_id>/save_selection", methods=["POST"])
def save_selection(doc_id):
    """
    STEP 2: Save the user-selected and edited title and plot.
    """
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    
    data = load_user_data(session["user_id"])
    document = find_document(data, doc_id)
    if document is None:
        return jsonify({"error": "Document not found"}), 404

    request_data = request.get_json()
    selected_title = request_data.get("title")
    selected_plot = request_data.get("plot")

    if not selected_title or not selected_plot:
        return jsonify({"error": "Title and plot are required."}), 400

    # Save the selections into the document data
    document["selected_title"] = selected_title
    document["selected_plot"] = selected_plot

    save_user_data(session["user_id"], data)
    
    return jsonify({"success": True, "message": "Selection saved."})


@app.route("/document/<doc_id>/generate_composition", methods=["POST"])
def generate_composition(doc_id):
    """
    STEP 3: Generate the rest of the composition elements based on the selected title and plot.
    This is a modified version of the original generate_composition_ideas.
    It now iterates through categories and generates suggestions for each.
    """
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    data = load_user_data(session["user_id"])
    document = find_document(data, doc_id)
    if document is None:
        return jsonify({"error": "Document not found"}), 404

    # This endpoint is called for each category, so we get the label from the request
    request_data = request.get_json()
    category_label = request_data.get("category_label")
    if not category_label:
        return jsonify({"error": "Category label is required"}), 400

    # --- DEBUG PRINTS ---
    print(f"--- Debugging generate_composition ---")
    print(f"Target Category Label: '{category_label}'")
    print(f"Document composition_elements: {json.dumps(document.get('composition_elements', {}), ensure_ascii=False, indent=2)}")
    # --- END DEBUG PRINTS ---
        
    # Suffix for file generation should be unique per category
    current_generation_number = _get_next_generation_number(session["user_id"])
    suffix = f"_{current_generation_number}_{category_label.replace(' ', '_')}"

    # Get LLM config
    llm_servers = data.get("llm_servers", {})
    generation_config = llm_servers.get("generation", {})
    llm_provider = generation_config.get("provider")
    llm_api_key = generation_config.get("api_key")
    llm_model_name = generation_config.get("model_name")
    llm_base_url = generation_config.get("base_url")
    suggestion_count = session.get("suggestion_count", 3)

    is_config_incomplete = not llm_provider or not llm_model_name or \
                           (llm_provider in ["gemini", "chatgpt"] and not llm_api_key) or \
                           (llm_provider == "other" and not llm_base_url)

    # Note: No mock call here, assuming config is complete by this stage.
    if is_config_incomplete:
        return jsonify({"error": "LLM configuration is incomplete."}), 400

    # The logic here is very similar to the original `generate_composition_ideas`,
    # but the prompt builder needs to be aware of the selected_title and selected_plot.
    # We will modify `build_composition_ideas_prompt` later if needed, but for now,
    # let's assume the existing prompt builder is sufficient if `intent` is well-defined.
    
    try:
        # We now call the original prompt builder, but for a single category
        prompt = build_composition_ideas_prompt(document, DEFAULT_COMPOSITION_META, session["user_id"], target_category_label=category_label, suffix=suffix, suggestion_count=suggestion_count)
        
        raw_text, suggestions_dict = call_llm(llm_api_key, llm_model_name, prompt, llm_provider, base_url=llm_base_url)

        # Save responses
        user_data_dir = get_user_data_path(session["user_id"])
        with open(os.path.join(user_data_dir, f"generated_llm{suffix}.txt"), "w", encoding="utf-8") as f:
            f.write(raw_text)
        with open(os.path.join(user_data_dir, f"generated_llm{suffix}.json"), "w", encoding="utf-8") as f:
            json.dump(suggestions_dict, f, ensure_ascii=False, indent=2)

        # Append suggestions to the main document object
        if "llm_suggestions" not in document or not isinstance(document["llm_suggestions"], list):
            document["llm_suggestions"] = []

        # This logic assumes the response contains suggestions for the requested category
        new_suggestions = suggestions_dict.get("suggestions", [])
        if new_suggestions:
            document["llm_suggestions"].extend(new_suggestions)
        
        save_user_data(session["user_id"], data)

        return jsonify(suggestions_dict)

    except (ValueError, RuntimeError, Exception) as e:
        return jsonify({"error": f"LLM_ERROR: {str(e)}"}), 500

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

    # ダウンロード用にdocumentのコピーを作成し、不要なキーを削除
    download_document_data = document.copy()
    keys_to_remove = [
        # "llm_suggestions", # ユーザーの要望によりダウンロード対象に含める
        # "semantic_labels", # ユーザーの要望によりダウンロード対象に含める
        # "numerical_features",
        # "fit_results",
        "units" # ユーザー提供の例にないため削除
    ]
    for key in keys_to_remove:
        download_document_data.pop(key, None) # キーが存在しない場合はエラーにならないようにpop(key, None)を使用

    document_json = json.dumps(download_document_data, ensure_ascii=False, indent=2)
    
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


@app.route("/document/<doc_id>/evaluate", methods=["POST"])
def evaluate_document(doc_id):
    """
    評価ページにリダイレクトする。実際の処理はクライアントサイドのJavaScriptが
    /evaluate/stream エンドポイントを呼び出すことで開始される。
    """
    if "user_id" not in session:
        return redirect("/login")

    data = load_user_data(session["user_id"])
    document = find_document(data, doc_id)

    # LLM設定が不完全な場合はエラーを表示して中断
    evaluation_config = data.get("llm_servers", {}).get("evaluation", {})
    llm_provider = evaluation_config.get("provider")
    is_config_incomplete = not llm_provider or not evaluation_config.get("model_name") or \
                           (llm_provider in ["gemini", "chatgpt"] and not evaluation_config.get("api_key")) or \
                           (llm_provider == "other" and not evaluation_config.get("base_url"))

    if is_config_incomplete:
        flash("評価を実行するには、まずダッシュボードで「構成要素評価 用 LLM」設定を完了してください。", "warning")
        return redirect(f"/document/{doc_id}#evaluation")

    if not document or "llm_suggestions" not in document or not document["llm_suggestions"]:
        flash("評価対象のAI提案がありません。「提案」タブで先にアイデアを生成してください。", "warning")
        return redirect(f"/document/{doc_id}#evaluation")

    # ページをリロードし、クライアント側でストリーミングを開始させる
    flash("評価処理を開始します。結果はリアルタイムで表示されます...", "info")
    return redirect(f"/document/{doc_id}#evaluation")


@app.route('/document/<doc_id>/evaluate/stream')
def evaluate_stream(doc_id):
    """
    Server-Sent Events (SSE) を使用して、意味ラベル評価の結果をストリーミングする。
    """
    from flask import Response
    import logging

    if "user_id" not in session:
        return Response("Unauthorized", status=401)

    def generate_labels(user_id_arg):
        data = load_user_data(user_id_arg)
        document = find_document(data, doc_id)

        # Get LLM configuration for the 'evaluation' role from persistent user data
        llm_config = data.get("llm_servers", {}).get("evaluation", {})

        if not document or "llm_suggestions" not in document or not document["llm_suggestions"]:
            yield f"data: {json.dumps({'error': '評価対象のデータが見つかりません。'})}\n\n"
            return

        user_data_dir = get_user_data_path(user_id_arg)
        log_file_path = os.path.join(user_data_dir, "labeler.log")
        evaluation_input = {"llm_suggestions": document["llm_suggestions"]}
        
        all_results = []
        # ロガーのハンドラをクリーンアップするための準備
        logger_to_cleanup = logging.getLogger("semantic_labeler")

        # Calculate total items
        total_suggestions_count = sum(
            len(texts) 
            for sg in evaluation_input.get("llm_suggestions", []) 
            for texts in sg.get("elements", {}).values() 
            if isinstance(texts, list)
        )
        # Send total items as initial event
        yield f"data: {json.dumps({'event': 'total_items', 'count': total_suggestions_count})}\n\n"

        current_processed_count = 0
        try:
            for labeled_result in label_suggestions(evaluation_input, llm_config=llm_config, log_file_path=log_file_path):
                all_results.append(labeled_result)
                current_processed_count += 1
                yield f"data: {json.dumps(labeled_result, ensure_ascii=False)}\n\n"
                # Send progress update
                yield f"data: {json.dumps({'event': 'progress', 'current': current_processed_count})}\n\n"
            
            document["semantic_labels"] = all_results
            save_user_data(user_id_arg, data)
            yield f"data: {json.dumps({'event': 'close', 'message': '全ての評価が完了しました。'})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': f'ストリーミング中にエラーが発生しました: {str(e)}'})}\n\n"
        finally:
            # ストリーム終了時に必ずハンドラを閉じてクリーンアップ
            for handler in logger_to_cleanup.handlers[:]:
                handler.close()
                logger_to_cleanup.removeHandler(handler)

    # ジェネレータに必要な情報を引数として渡す
    return Response(generate_labels(session["user_id"]), mimetype='text/event-stream')



@app.route("/document/<doc_id>/download_evaluation")
def download_evaluation(doc_id):
    if "user_id" not in session:
        return redirect("/login")

    data = load_user_data(session["user_id"])
    document = find_document(data, doc_id)

    if not document or "semantic_labels" not in document or not document["semantic_labels"]:
        flash("ダウンロードする評価データがありません。", "warning")
        return redirect(f"/document/{doc_id}#evaluation")

    try:
        # Flatten the data
        df = pd.json_normalize(document["semantic_labels"], sep='_')
        
        # Convert to CSV
        csv_data = df.to_csv(index=False, encoding='utf-8-sig')
        
        # Create response
        response = make_response(csv_data)
        response.headers["Content-Disposition"] = "attachment; filename=evaluation_results.csv"
        response.headers["Content-Type"] = "text/csv; charset=utf-8-sig"
        return response

    except Exception as e:
        flash(f"CSVの生成中にエラーが発生しました: {e}", "error")
        return redirect(f"/document/{doc_id}#evaluation")


@app.route("/document/<doc_id>/vectorize", methods=["POST"])
def vectorize_document(doc_id):
    if "user_id" not in session:
        return redirect("/login")

    data = load_user_data(session["user_id"])
    document = find_document(data, doc_id)

    if not document or "semantic_labels" not in document or not document["semantic_labels"]:
        flash("数値化する評価済みデータがありません。「評価」タブで先に意味ラベルを付与してください。", "warning")
        return redirect(f"/document/{doc_id}#evaluation")

    # Instantiate the extractor and call the method
    try:
        extractor = FeatureExtractor()
        numerical_features = extractor.create_numerical_features(document["semantic_labels"])
    except (FileNotFoundError, ValueError) as e:
        flash(f"特徴量の数値化中にエラーが発生しました: {e}", "error")
        return redirect(f"/document/{doc_id}#evaluation")
    
    document["numerical_features"] = numerical_features
    save_user_data(session["user_id"], data)
    flash("数値特徴量への変換が完了しました。", "success")

    return redirect(f"/document/{doc_id}#vectorization")


@app.route("/document/<doc_id>/element_fit", methods=["POST"])
def element_fit(doc_id):
    if "user_id" not in session:
        return redirect("/login")

    data = load_user_data(session["user_id"])
    document = find_document(data, doc_id)

    # 1. Check for necessary data
    candidates = document.get("numerical_features")
    if not candidates:
        flash("適合度を計算するには、先に「数値化」タブで提案を数値化してください。", "warning")
        return redirect(f"/document/{doc_id}#element-fit")

    composition_elements = document.get("composition_elements", {})
    if not composition_elements:
        flash("適合度を計算するには、先に「構成要素」タブで理想の役割を定義してください。", "warning")
        return redirect(f"/document/{doc_id}#element-fit")

    # 2. Extract ideal elements from composition data and assign unique features
    
    # Load reader effects to create unique feature vectors for ideals
    try:
        with open("prompt_templates/novel_label_config.json", "r", encoding="utf-8") as f:
            label_config = json.load(f)
        reader_effects = list(label_config.get("labels", {}).get("reader_effect", {}).keys())
    except Exception:
        reader_effects = []

    ideal_elements_raw = []
    element_index = 0
    for cat_group in composition_elements.values(): # "common", "doc_type_specific"
        for category in cat_group.get("categories", []):
            for element in category.get("elements", []):
                
                # Create a unique label set for each ideal to give it a unique feature vector
                temp_labels = {}
                if reader_effects:
                    # Assign a unique reader_effect based on the element's index to ensure
                    # each ideal has a different feature vector.
                    effect_to_assign = reader_effects[element_index % len(reader_effects)]
                    temp_labels["reader_effect"] = [effect_to_assign]

                ideal_elements_raw.append({
                    "category": category.get("label"),
                    "element": element.get("label"),
                    "text": element.get("label"), # Use label as text for featurizing
                    "labels": temp_labels # Use the generated labels instead of empty ones
                })
                element_index += 1

    if not ideal_elements_raw:
        flash("適合度を計算するための理想の役割が「構成要素」タブで定義されていません。", "warning")
        return redirect(f"/document/{doc_id}#element-fit")

    # 3. Featurize ideal elements
    try:
        extractor = FeatureExtractor()
        ideal_elements_with_features = extractor.create_numerical_features(ideal_elements_raw)
    except (FileNotFoundError, ValueError) as e:
        flash(f"理想役割の数値化中にエラーが発生しました: {e}", "error")
        return redirect(f"/document/{doc_id}#element-fit")

    # 4. Calculate fit
    fit_results = apply_fit_to_candidates(candidates, ideal_elements_with_features)

    # 5. Save results and redirect
    document["fit_results"] = fit_results
    save_user_data(session["user_id"], data)
    flash("適合度の計算が完了しました。", "success")
    return redirect(f"/document/{doc_id}#element-fit")


if __name__ == "__main__":
    app.run(debug=True)

