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
from lm_input import build_composition_ideas_prompt, mock_llm_call

# Helper function for cleaning up old generated files
def _cleanup_old_generated_files(user_id: str):
    user_data_dir = get_user_data_path(user_id)
    if not os.path.exists(user_data_dir):
        return

    # Patterns for files to delete
    patterns = [
        os.path.join(user_data_dir, "generated_prompt_*.md"),
        os.path.join(user_data_dir, "generated_llm_*.txt"),
        os.path.join(user_data_dir, "generated_llm_*.json")
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
    
    user_config = {
        "llm": {
            "api_key": session.get("llm_api_key", ""),
            "model_name": session.get("llm_model_name", ""),
            "base_url": session.get("llm_base_url", ""),
            "provider": session.get("llm_provider", "gemini")
        },
        "quantum": {
            "api_key": session.get("quantum_server_api_key", "")
        },
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

@app.route("/save_config", methods=["POST"])
def save_config():
    if "user_id" not in session:
        flash("ログインしてください。", "error")
        return redirect("/login")

    # Store LLM config in session
    session["llm_api_key"] = request.form["llm_api_key"]
    
    llm_provider = request.form.get("llm_provider", "gemini")
    session["llm_provider"] = llm_provider

    if llm_provider == "gemini":
        session["llm_model_name"] = "gemini-pro" # Default for Gemini
        session["llm_base_url"] = "" # Gemini typically doesn't use a custom base_url
    elif llm_provider == "chatgpt":
        session["llm_model_name"] = "gpt-4o-mini" # Default for ChatGPT
        session["llm_base_url"] = "" # ChatGPT typically doesn't use a custom base_url
    else: # other
        # For 'other', use the values provided in the form
        session["llm_model_name"] = request.form["llm_model_name"]
        session["llm_base_url"] = request.form["llm_base_url"]
    
    session["quantum_server_api_key"] = request.form["quantum_server_api_key"]
    
    flash("設定を保存しました。", "success")
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

@app.route("/document/<doc_id>/generate_ideas", methods=["POST"])
def generate_composition_ideas(doc_id):
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    data = load_user_data(session["user_id"])
    document = find_document(data, doc_id)
    if document is None:
        return jsonify({"error": "Document not found"}), 404

    request_data = request.get_json()
    category_label = request_data.get("category_label") # Get category label from request
    is_first_category_in_session = request_data.get("is_first_category_in_session", False)

    # If this is the first category request in a new generation session, clean up and reset counter
    if is_first_category_in_session:
        _cleanup_old_generated_files(session["user_id"])
        _reset_generation_counter(session["user_id"])

    # Get the next sequential number for this generation
    current_generation_number = _get_next_generation_number(session["user_id"])
    suffix = f"_{current_generation_number}"

    # Get LLM configuration from session
    llm_api_key = session.get("llm_api_key")
    llm_model_name = session.get("llm_model_name")
    llm_base_url = session.get("llm_base_url")
    llm_provider = session.get("llm_provider", "gemini") # Retrieve llm_provider
    suggestion_count = session.get("suggestion_count", 3) # Retrieve suggestion_count

    # Refined mock fallback logic
    # Mock if API key is missing for Gemini/ChatGPT, or if any of the three are missing for 'other'
    is_config_incomplete = False
    if llm_provider in ["gemini", "chatgpt"] and not llm_api_key:
        is_config_incomplete = True
    elif llm_provider == "other" and (not llm_model_name or not llm_base_url):
        is_config_incomplete = True
    
    if is_config_incomplete:
        prompt = build_composition_ideas_prompt(document, DEFAULT_COMPOSITION_META, session["user_id"], target_category_label=category_label, suffix=suffix, suggestion_count=suggestion_count)
        suggestions_dict = mock_llm_call(prompt, suggestion_count=suggestion_count)
        return jsonify({"suggestions": suggestions_dict.get("suggestions", []), "message": "LLM設定が不完全なため、モックデータを使用しました。"}), 200

    # --- Retry logic for LLM call ---
    MAX_RETRIES_PER_CATEGORY_ELEMENT = 3
    accumulated_suggestions_for_category = {}
    
    # Get the elements for the target_category_label to properly check completion
    target_elements_in_document = []
    # Helper to process categories (common or doc_type_specific)
    def extract_elements_from_doc(categories_data):
        if not categories_data:
            return
        for category_obj in categories_data:
            if category_obj.get("label") == category_label:
                if category_obj.get("elements"):
                    for element_obj in category_obj["elements"]:
                        if element_obj.get("label"):
                            target_elements_in_document.append(element_obj["label"])
                break # Found the category, no need to check further

    common_categories = document.get("composition_elements", {}).get("common", {}).get("categories")
    extract_elements_from_doc(common_categories)
    doc_type_specific_categories = document.get("composition_elements", {}).get("doc_type_specific", {}).get("categories")
    extract_elements_from_doc(doc_type_specific_categories)
    
    # Initialize accumulated suggestions for each element to empty lists
    for element_label in target_elements_in_document:
        accumulated_suggestions_for_category[element_label] = []

    final_suggestions_for_response = []

    for retry_attempt in range(MAX_RETRIES_PER_CATEGORY_ELEMENT + 1):
        try:
            # Build prompt for LLM (same prompt for retries for simplicity)
            prompt = build_composition_ideas_prompt(document, DEFAULT_COMPOSITION_META, session["user_id"], target_category_label=category_label, suffix=suffix, suggestion_count=suggestion_count)
            
            raw_text, suggestions_dict = call_llm(llm_api_key, llm_model_name, prompt, llm_provider, base_url=llm_base_url)

            # Find the target category's suggestions from the LLM response
            current_llm_suggestions = suggestions_dict.get("suggestions", [])
            target_category_llm_response = next(
                (sug_cat for sug_cat in current_llm_suggestions if sug_cat.get("category") == category_label),
                None
            )

            if target_category_llm_response:
                elements_from_llm = target_category_llm_response.get("elements", {})
                for element_label, new_suggestions in elements_from_llm.items():
                    if element_label in target_elements_in_document: # Only process elements that exist in the document
                        current_list = accumulated_suggestions_for_category.setdefault(element_label, [])
                        updated_list = list(set(current_list + new_suggestions)) # Ensure uniqueness and accumulate
                        accumulated_suggestions_for_category[element_label] = updated_list[:suggestion_count] # Trim to suggestion_count

            # Check if all target elements have reached the desired suggestion_count
            all_elements_complete = True
            for element_label in target_elements_in_document:
                if len(accumulated_suggestions_for_category.get(element_label, [])) < suggestion_count:
                    all_elements_complete = False
                    break
            
            if all_elements_complete:
                break # Exit retry loop if all elements are complete

        except ValueError as e:
            if retry_attempt == MAX_RETRIES_PER_CATEGORY_ELEMENT:
                return jsonify({"error": str(e)}), 400
            print(f"ValueError during LLM call, retrying... ({e})")
            continue
        except RuntimeError as e:
            if retry_attempt == MAX_RETRIES_PER_CATEGORY_ELEMENT:
                return jsonify({"error": f"LLM呼び出しエラー: {str(e)}", "message": "LLM呼び出しでエラーが発生しました。設定とプロンプトを確認してください。"}), 500
            print(f"RuntimeError during LLM call, retrying... ({e})")
            continue
        except Exception as e:
            if retry_attempt == MAX_RETRIES_PER_CATEGORY_ELEMENT:
                return jsonify({"error": f"予期せぬエラー: {str(e)}", "message": "予期せぬエラーが発生しました。"}), 500
            print(f"Unexpected error during LLM call, retrying... ({e})")
            continue

    # --- End of Retry logic ---

    # Construct the final suggestions for the response based on accumulated_suggestions_for_category
    if accumulated_suggestions_for_category:
        final_suggestions_for_response.append({
            "category": category_label,
            "elements": accumulated_suggestions_for_category
        })
    else:
        # If no suggestions were accumulated after all retries (e.g., LLM consistently failed or returned nothing)
        return jsonify({"suggestions": [], "message": "提案を生成できませんでした。"}), 500

    # Save the raw LLM response (from the last successful or attempted call) to a text file with suffix
    user_data_dir = get_user_data_path(session["user_id"])
    os.makedirs(user_data_dir, exist_ok=True)
    llm_output_file_path = os.path.join(user_data_dir, f"generated_llm{suffix}.txt")
    try:
        with open(llm_output_file_path, "w", encoding="utf-8") as f:
            f.write(raw_text if 'raw_text' in locals() else "No LLM response received.")
        print(f"Raw LLM response written to: {llm_output_file_path}")
    except PermissionError as e:
        print(f"ERROR: Permission denied when writing to {llm_output_file_path}: {e}")
        flash(f"ファイルの書き込み権限がありません: {llm_output_file_path}。ファイルのパーミッションを確認してください。", "error")
        return jsonify({"error": f"ファイルの書き込み権限がありません: {e}"}), 500
    except IOError as e:
        print(f"ERROR: IO error when writing to {llm_output_file_path}: {e}")
        flash(f"ファイル書き込み中にエラーが発生しました: {llm_output_file_path}。ディスク容量やファイルロックを確認してください。", "error")
        return jsonify({"error": f"ファイル書き込み中にエラーが発生しました: {e}"}), 500


    # Save the structured LLM response (final accumulated suggestions) to a JSON file with suffix
    llm_json_output_file_path = os.path.join(user_data_dir, f"generated_llm{suffix}.json")
    try:
        with open(llm_json_output_file_path, "w", encoding="utf-8") as f:
            json.dump({"suggestions": final_suggestions_for_response}, f, ensure_ascii=False, indent=2)
        print(f"Structured LLM response written to: {llm_json_output_file_path}")
    except PermissionError as e:
        print(f"ERROR: Permission denied when writing to {llm_json_output_file_path}: {e}")
        flash(f"ファイルの書き込み権限がありません: {llm_json_output_file_path}。ファイルのパーミッションを確認してください。", "error")
        return jsonify({"error": f"ファイルの書き込み権限がありません: {e}"}), 500
    except IOError as e:
        print(f"ERROR: IO error when writing to {llm_json_output_file_path}: {e}")
        flash(f"ファイル書き込み中にエラーが発生しました: {llm_json_output_file_path}。ディスク容量やファイルロックを確認してください。", "error")
        return jsonify({"error": f"ファイル書き込み中にエラーが発生しました: {e}"}), 500

    # If this is the first call in the generation sequence, clear old suggestions
    if is_first_category_in_session:
        document["llm_suggestions"] = []
    
    # Ensure llm_suggestions key exists and is a list
    if "llm_suggestions" not in document or not isinstance(document["llm_suggestions"], list):
        document["llm_suggestions"] = []

    # Update/append new suggestions for the target category
    existing_category_index = -1
    for idx, existing_sug_cat in enumerate(document["llm_suggestions"]):
        if existing_sug_cat.get("category") == category_label:
            existing_category_index = idx
            break

    if existing_category_index != -1:
        # Update existing category
        document["llm_suggestions"][existing_category_index] = final_suggestions_for_response[0]
    else:
        # Append new category
        if final_suggestions_for_response:
            document["llm_suggestions"].extend(final_suggestions_for_response)
            
    save_user_data(session["user_id"], data)

    return jsonify({"suggestions": final_suggestions_for_response})

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
        "fit_results",
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

    # LLM設定が不完全な場合はエラーを表示して中断
    llm_provider = session.get("llm_provider")
    is_config_incomplete = (llm_provider in ["gemini", "chatgpt"] and not session.get("llm_api_key")) or \
                           (llm_provider == "other" and (not session.get("llm_model_name") or not session.get("llm_base_url")))

    if is_config_incomplete:
        flash("評価を実行するには、まず「設定」タブでLLM設定を完了してください。", "warning")
        return redirect(f"/document/{doc_id}#evaluation")

    data = load_user_data(session["user_id"])
    document = find_document(data, doc_id)

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

    # ジェネレータが実行される前に、リクエストコンテキストから必要な情報を取得
    user_id = session["user_id"]
    llm_config = {
        "api_key": session.get("llm_api_key"),
        "model_name": session.get("llm_model_name"),
        "provider": session.get("llm_provider"),
        "base_url": session.get("llm_base_url")
    }

    def generate_labels(user_id_arg, llm_config_arg):
        data = load_user_data(user_id_arg)
        document = find_document(data, doc_id)

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
            for labeled_result in label_suggestions(evaluation_input, llm_config=llm_config_arg, log_file_path=log_file_path):
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
    return Response(generate_labels(user_id, llm_config), mimetype='text/event-stream')



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

    # 2. Extract ideal elements from composition data
    ideal_elements_raw = []
    for cat_group in composition_elements.values(): # "common", "doc_type_specific"
        for category in cat_group.get("categories", []):
            for element in category.get("elements", []):
                # NOTE: The 'value' from the form is not used for featurizing.
                # We are creating a "template" based on its name/role.
                # The featurizer will assign default values.
                ideal_elements_raw.append({
                    "category": category.get("label"),
                    "element": element.get("label"),
                    "text": element.get("label"), # Use label as text for featurizing
                    "labels": {} # No semantic labels, so featurizer will use defaults
                })

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

