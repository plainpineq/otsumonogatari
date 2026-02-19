from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, flash, Response
import json
import os
from datetime import datetime
import time # For simulating work and testing progress updates
import glob # Import glob for file pattern matching


from user_files import load_user_data, save_user_data, get_user_data_path
import evaluation_engine
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
    document.setdefault("numerical_features", []) # Used for fit calculation
    document.setdefault("semantic_labels", []) # Used for fit calculation
    document.setdefault("fit_results", []) # NEW: Ensure fit_results has a default

    user_config = {
        "suggestion_count": session.get("suggestion_count", 3)
    }

    return render_template(
        "evaluation.html",
        document=document,
        user_config=user_config
    )


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
        
        # 候補者リストの取得
        candidates = document.get("numerical_features")
        if not candidates:
            yield f"data: {json.dumps({'error': 'No candidates', 'message': '「評価」タブで先に意味ラベルを付与・数値化してください'})}\n\n"
            return

        try:
            extractor = FeatureExtractor()
            label_order = extractor.global_label_order
            
            # --- 暫定的なターゲットと重みの設定 (将来的にUIから設定可能にする) ---
            # 全次元 0 のターゲットベクトル
            target_vec = [0] * len(label_order)
            # 全分類 1.0 の重み
            category_weights = {classification: 1.0 for classification, _ in label_order}
            system_tolerance = 0.0 # システム固定値
            # -----------------------------------------------------------

            processed_candidates = []
            total = len(candidates)
            
            yield f"data: {json.dumps({'progress': 0, 'message': '適合度計算を開始しました'})}\n\n"

            for i, cand in enumerate(candidates):
                # 候補のグローバルベクトルを取得
                cand_features = cand.get("features", {})
                
                # FeatureExtractorを使用して確実にグローバルベクトルに変換
                cand_vec = extractor.to_global_vector(cand_features)
                
                # 新しい評価エンジンで計算
                eval_result = evaluation_engine.evaluate(
                    cand_vec, target_vec, category_weights, label_order, system_tolerance
                )
                
                # 結果の格納 (既存UIとの互換性のために fit スコアとして保存)
                cand["fit"] = {
                    "best_fit_element": "Global Target", # 固定
                    "score": eval_result["adjusted_distance"],
                    "raw_distance": eval_result["raw_distance"],
                    "global_vector": cand_vec
                }
                
                processed_candidates.append(cand)
                
                progress = int((i + 1) / total * 100)
                yield f"data: {json.dumps({'progress': progress, 'message': f'{i+1}/{total} 候補を評価中...'})}\n\n"
                time.sleep(0.02)

            # 最終結果の保存
            document["fit_results"] = processed_candidates
            save_user_data(user_id_arg, data)
            
            yield f"data: {json.dumps({'progress': 100, 'message': '適合度計算が完了しました', 'complete': True, 'fit_results': processed_candidates})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e), 'message': f'適合度計算中にエラーが発生しました: {str(e)}'})}\n\n"

    return Response(generate(current_user_id), mimetype='text/event-stream')
