import json
import os
import uuid
from typing import Dict, Any, List, Optional
from user_files import get_user_data_path, load_user_data, save_user_data

class DraftManager:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.data = self._load_and_init()

    def _load_and_init(self) -> Dict[str, Any]:
        """データを読み込み、manuscript構造がない場合は初期化する"""
        data = load_user_data(self.user_id)
        
        # manuscriptの初期化
        if "manuscript" not in data:
            data["manuscript"] = {
                "chapters": []
            }
        
        # settingsの初期化（要件にある設定パスを確保）
        if "settings" not in data:
            data["settings"] = {
                "llm_servers": {
                    "draft": {
                        "provider": "openai",
                        "model": "gpt-4o",
                        "api_key": ""
                    }
                }
            }
        elif "llm_servers" not in data["settings"]:
            data["settings"]["llm_servers"] = {
                "draft": {
                    "provider": "openai",
                    "model": "gpt-4o",
                    "api_key": ""
                }
            }
        elif "draft" not in data["settings"]["llm_servers"]:
            data["settings"]["llm_servers"]["draft"] = {
                "provider": "openai",
                "model": "gpt-4o",
                "api_key": ""
            }
            
        return data

    def save(self):
        """現在のデータを保存する"""
        save_user_data(self.user_id, self.data)

    def generate_id(self, prefix: str = "") -> str:
        """ユニークなIDを生成する"""
        return f"{prefix}{uuid.uuid4().hex[:8]}"

    def find_chapter(self, chapter_id: str) -> Optional[Dict[str, Any]]:
        """指定されたIDの章を探す"""
        for chap in self.data["manuscript"]["chapters"]:
            if chap["chapter_id"] == chapter_id:
                return chap
        return None

    def find_scene(self, chapter_id: str, scene_id: str) -> Optional[Dict[str, Any]]:
        """指定されたIDのシーンを探す"""
        chapter = self.find_chapter(chapter_id)
        if not chapter:
            return None
        for scene in chapter.get("scenes", []):
            if scene["scene_id"] == scene_id:
                return scene
        return None

    def add_chapter(self, title: str, order: Optional[int] = None) -> Dict[str, Any]:
        """新しい章を追加する"""
        chapters = self.data["manuscript"]["chapters"]
        if order is None:
            order = len(chapters) + 1
        
        new_chapter = {
            "chapter_id": self.generate_id("chap_"),
            "title": title,
            "order": order,
            "chapter_level_drafts": [],
            "scenes": []
        }
        chapters.append(new_chapter)
        # orderでソート
        chapters.sort(key=lambda x: x["order"])
        return new_chapter

    def add_scene(self, chapter_id: str, title: str, order: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """章に新しいシーンを追加する"""
        chapter = self.find_chapter(chapter_id)
        if not chapter:
            return None
        
        scenes = chapter.get("scenes", [])
        if order is None:
            order = len(scenes) + 1
            
        new_scene = {
            "scene_id": self.generate_id("scene_"),
            "title": title,
            "order": order,
            "structure_snapshot": {},
            "drafts": []
        }
        scenes.append(new_scene)
        scenes.sort(key=lambda x: x["order"])
        chapter["scenes"] = scenes
        return new_scene

    def add_chapter_draft(self, chapter_id: str, content: str, prompt_used: str):
        """章レベルの下書きを追加する"""
        chapter = self.find_chapter(chapter_id)
        if not chapter:
            return None
        
        draft = {
            "draft_id": self.generate_id("drft_"),
            "content": content,
            "prompt_used": prompt_used,
            "created_at": uuid.uuid4().hex # 簡易的なタイムスタンプ代わり
        }
        chapter["chapter_level_drafts"].append(draft)
        return draft

    def add_scene_draft(self, chapter_id: str, scene_id: str, content: str, prompt_used: str, structure_snapshot: Dict[str, Any]):
        """シーンの下書きを追加する"""
        scene = self.find_scene(chapter_id, scene_id)
        if not scene:
            return None
        
        draft = {
            "draft_id": self.generate_id("drft_"),
            "content": content,
            "prompt_used": prompt_used,
            "structure_snapshot": structure_snapshot,
            "created_at": uuid.uuid4().hex
        }
        scene["drafts"].append(draft)
        # スナップショットをシーン本体にも保存（最新状態として）
        scene["structure_snapshot"] = structure_snapshot
        return draft
