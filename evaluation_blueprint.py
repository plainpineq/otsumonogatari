from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, flash, Response
import json
import os
from datetime import datetime
import time 


from user_files import load_user_data, save_user_data, get_user_data_path
import evaluation_engine
from services.services import find_document
from feature_extractor import FeatureExtractor

evaluation_bp = Blueprint('evaluation_bp', __name__, template_folder='templates')

@evaluation_bp.route("/document/<doc_id>/save_criteria", methods=["POST"])
def save_criteria(doc_id):
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = load_user_data(session["user_id"])
    document = find_document(data, doc_id)
    if document is None:
        return jsonify({"error": "Document not found"}), 404

    criteria = request.get_json()
    if not criteria:
        return jsonify({"error": "No criteria data provided"}), 400

    document["evaluation_criteria"] = criteria
    save_user_data(session["user_id"], data)
    
    return jsonify({"success": True})


@evaluation_bp.route("/document/<doc_id>/calculate_fit_stream", methods=["GET"])
def calculate_fit_stream_route(doc_id):
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    current_user_id = session["user_id"]

    def generate(user_id_arg):
        data = load_user_data(user_id_arg)
        document = find_document(data, doc_id)

        if document is None:
            yield f"data: {json.dumps({'error': 'Document not found'})}\n\n"
            return
        
        candidates = document.get("numerical_features")
        if not candidates:
            yield f"data: {json.dumps({'error': 'No candidates', 'message': '先に意味ラベルを付与・数値化してください'})}\n\n"
            return

        criteria = document.get("evaluation_criteria", {})
        targets_dict = criteria.get("global_target", {})
        category_weights = criteria.get("category_weights", {})

        try:
            extractor = FeatureExtractor()
            label_order = extractor.global_label_order
            
            # --- 保存された基準からグローバルターゲットベクトルを構築 ---
            target_vec = []
            for classification, label_key in label_order:
                val = targets_dict.get(classification, {}).get(label_key, 0)
                target_vec.append(val)
            # -----------------------------------------------------------

            system_tolerance = 0.0 # システム固定
            processed_candidates = []
            total = len(candidates)
            
            yield f"data: {json.dumps({'progress': 0, 'message': '適合度計算を開始しました'})}\n\n"

            for i, cand in enumerate(candidates):
                cand_features = cand.get("features", {})
                cand_vec = extractor.to_global_vector(cand_features)
                
                eval_result = evaluation_engine.evaluate(
                    cand_vec, target_vec, category_weights, label_order, system_tolerance
                )
                
                cand["fit"] = {
                    "best_fit_element": "Global Target",
                    "score": eval_result["adjusted_distance"],
                    "raw_distance": eval_result["raw_distance"],
                    "global_vector": cand_vec
                }
                
                processed_candidates.append(cand)
                
                progress = int((i + 1) / total * 100)
                yield f"data: {json.dumps({'progress': progress, 'message': f'{i+1}/{total} 候補を評価中...'})}\n\n"
                time.sleep(0.01)

            document["fit_results"] = processed_candidates
            save_user_data(user_id_arg, data)
            
            yield f"data: {json.dumps({'progress': 100, 'message': '適合度計算が完了しました', 'complete': True, 'fit_results': processed_candidates})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e), 'message': f'エラー: {str(e)}'})}\n\n"

    return Response(generate(current_user_id), mimetype='text/event-stream')
