from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, flash, Response
import json
import os
from datetime import datetime
import time # For simulating work and testing progress updates


from user_files import load_user_data, save_user_data, get_user_data_path
from ideal_profile_generator import generate_ideal_profile
from ideal_profile_evaluator import IdealProfileEvaluator
from services.services import find_document, DEFAULT_COMPOSITION_META
from services.llm_client import call_llm # For explicit mock calls if needed
from feature_extractor import FeatureExtractor # For numerical features of candidates

evaluation_bp = Blueprint('evaluation_bp', __name__, template_folder='templates')


@evaluation_bp.route("/document/<doc_id>/evaluation_tab")
def evaluation_tab(doc_id):
    if "user_id" not in session:
        return redirect(url_for("login_view"))

    data = load_user_data(session["user_id"])
    document = find_document(data, doc_id)

    if document is None:
        flash("ドキュメントが見つかりませんでした。", "error")
        return redirect(url_for("dashboard"))
    
    # Ensure document has necessary default keys for the template
    document.setdefault("ideal_profile", {})
    document.setdefault("numerical_features", []) # Used for fit calculation
    document.setdefault("semantic_labels", []) # Used for fit calculation
    document.setdefault("fit_results", []) # NEW: Ensure fit_results has a default


    # Get persistent server configurations for evaluation role
    llm_servers = session.get("llm_servers", {})
    # For ideal_profile generation, we will use a new role, let's call it 'ideal_profile_generation'
    ideal_profile_llm_config = llm_servers.get("ideal_profile_generation", {})

    user_config = {
        "ideal_profile_llm_config": ideal_profile_llm_config,
        "suggestion_count": session.get("suggestion_count", 3)
    }

    return render_template(
        "evaluation.html",
        document=document,
        user_config=user_config
    )

@evaluation_bp.route("/document/<doc_id>/generate_ideal_profile", methods=["POST"])
def generate_ideal_profile_route(doc_id):
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = load_user_data(session["user_id"])
    document = find_document(data, doc_id)
    if document is None:
        return jsonify({"error": "Document not found"}), 404
    
    # Get LLM config for ideal_profile generation
    llm_servers = session.get("llm_servers", {})
    ideal_profile_llm_config = llm_servers.get("ideal_profile_generation", {})
    
    # Check if LLM config is complete, if not, provide mock data or error
    is_config_incomplete = (
        not ideal_profile_llm_config.get("provider") or
        not ideal_profile_llm_config.get("model_name") or
        (ideal_profile_llm_config.get("provider") in ["gemini", "chatgpt"] and not ideal_profile_llm_config.get("api_key")) or
        (ideal_profile_llm_config.get("provider") == "other" and not ideal_profile_llm_config.get("base_url"))
    )

    # For now, let's just mock if config is incomplete
    if is_config_incomplete:
        # Generate mock ideal_profile structure
        mock_ideal_profile = {
            "meta": {
                "created_at": datetime.now().isoformat(),
                "version": 1
            },
            "base_profile": {
                "主人公": {
                    "change_type": 2,
                    "causal_exposure": 2,
                    "conflict_type": 2,
                    "reader_effect": ["違和感", "緊張"]
                },
                "ヒロイン": {
                    "change_type": 1,
                    "causal_exposure": 1,
                    "conflict_type": 1,
                    "reader_effect": ["希望"]
                }
            },
            "author_modifier": {},
            "tolerance": {
                 "主人公": {
                    "change_type": 1.0,
                    "causal_exposure": 1.0,
                    "conflict_type": 1.0,
                    "reader_effect": 1.0
                },
            }
        }
        flash("LLM設定が不完全なため、モックのideal_profileを生成しました。", "warning")
        document["ideal_profile"] = mock_ideal_profile
        save_user_data(session["user_id"], data)
        return jsonify({"success": True, "ideal_profile": mock_ideal_profile})

    try:
        ideal_profile_data, raw_llm_text, llm_response_json = generate_ideal_profile(
            document, ideal_profile_llm_config, session["user_id"]
        )
        print("Received ideal_profile_data from generate_ideal_profile function.")
        document["ideal_profile"] = ideal_profile_data
        print("Saving user data with new ideal_profile...")
        save_user_data(session["user_id"], data)
        print("User data saved successfully.")

        flash("Ideal Profileを生成しました。", "success")
        return jsonify({"success": True, "ideal_profile": ideal_profile_data})

    except Exception as e:
        flash(f"Ideal Profileの生成中にエラーが発生しました: {str(e)}", "error")
        return jsonify({"error": str(e)}), 500


@evaluation_bp.route("/document/<doc_id>/save_ideal_profile", methods=["POST"])
def save_ideal_profile_route(doc_id):
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = load_user_data(session["user_id"])
    document = find_document(data, doc_id)
    if document is None:
        return jsonify({"error": "Document not found"}), 404
    
    # Assuming the ideal_profile JSON is sent directly in the request body
    updated_ideal_profile = request.get_json()
    if not updated_ideal_profile:
        return jsonify({"error": "No ideal profile data provided."}), 400
    
    # Validate structure if necessary. For now, trust client.
    document["ideal_profile"] = updated_ideal_profile
    save_user_data(session["user_id"], data)
    
    flash("Ideal Profileを保存しました。", "success")
    return jsonify({"success": True, "ideal_profile": updated_ideal_profile})


@evaluation_bp.route("/document/<doc_id>/calculate_fit_stream", methods=["GET"])
def calculate_fit_stream_route(doc_id):
    if "user_id" not in session:
        # For SSE, return JSON error rather than redirect
        return jsonify({"error": "Unauthorized"}), 401

    current_user_id = session["user_id"] # Capture user_id here

    def generate(user_id_arg): # Modify generate to accept user_id_arg
        data = load_user_data(user_id_arg) # Use the passed user_id
        document = find_document(data, doc_id)

        if document is None:
            yield f"data: {json.dumps({'error': 'Document not found', 'message': 'ドキュメントが見つかりませんでした'})}\n\n"
            return
        
        ideal_profile_data = document.get("ideal_profile")
        if not ideal_profile_data or not ideal_profile_data.get("base_profile"):
            yield f"data: {json.dumps({'error': 'Ideal Profile is not set', 'message': '先にIdeal Profileを生成・設定してください'})}\n\n"
            return
        
        semantic_labels = document.get("semantic_labels")
        if not semantic_labels:
            yield f"data: {json.dumps({'error': 'Semantic labels are not available', 'message': '「評価」タブで先に意味ラベルを付与してください'})}\n\n"
            return

        try:
            evaluator = IdealProfileEvaluator()
            extractor = FeatureExtractor()
            candidates_numerical_features = extractor.create_numerical_features(semantic_labels)

            # Iterate through the generator from IdealProfileEvaluator
            for event_data in evaluator.evaluate_and_score_candidates_stream(
                candidates_numerical_features,
                ideal_profile_data
            ):
                if "fit_results" in event_data and event_data["complete"]:
                    # Save results once complete
                    document["numerical_features"] = candidates_numerical_features # Save for consistency
                    document["fit_results"] = event_data["fit_results"] # Save the final fit results
                    save_user_data(user_id_arg, data)
                    # No flash message here, client will handle completion notification
                
                yield f"data: {json.dumps(event_data)}\n\n"
                time.sleep(0.05) # Small delay to see progress updates for testing

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e), 'message': f'適合度計算中にエラーが発生しました: {str(e)}'})}\n\n"

    return Response(generate(current_user_id), mimetype='text/event-stream')
