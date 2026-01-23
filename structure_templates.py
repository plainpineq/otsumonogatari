STRUCTURE_TEMPLATES = {
    "小説": [
        "導入", "日常", "事件", "葛藤", "転機", "クライマックス", "結末"
    ],
    "論文": [
        "Abstract", "Introduction", "Methods",
        "Results", "Discussion", "Conclusion"
    ],
    "記事": [
        "はじめに", "背景・課題", "解決策の概要",
        "実装・手順", "注意点・ハマりどころ", "まとめ"
    ],
    "脚本": [
        "登場人物", "舞台設定", "シーン1", "シーン2", "結末"
    ],
    "随筆": [
        "テーマ提示", "エピソード1", "考察", "結論"
    ]
}

COMPOSITION_ELEMENTS_META = {
  "version": "1.0",
  "description": "LLMが生成し、最適化・選別される作品構成要素のメタ定義",

  "common_categories": [
    {
      "id": "theme",
      "label": "テーマ・問い",
      "multiple": True,
      "description": "作品全体を貫く問いや主題",
      "llm_generate": True,
      "optimize": True
    },
    {
      "id": "value",
      "label": "価値観",
      "multiple": True,
      "description": "肯定・否定される価値",
      "llm_generate": True,
      "optimize": True
    },
    {
      "id": "constraint",
      "label": "制約条件",
      "multiple": True,
      "description": "表現・設定上の制約",
      "llm_generate": False,
      "optimize": False
    }
  ],

  "doc_types": {
    "novel": {
      "label": "小説",
      "categories": [
        {
          "id": "scene",
          "label": "シーン案",
          "multiple": True,
          "instance_structure": {
            "phase": {
              "type": "enum",
              "values": [
                "導入",
                "日常",
                "事件",
                "葛藤",
                "転機",
                "クライマックス",
                "結末"
              ]
            },
            "summary": {
              "type": "text"
            },
            "emotion_shift": {
              "type": "text",
              "description": "感情の変化"
            }
          },
          "llm_generate": True,
          "optimize": True
        },
        {
          "id": "character",
          "label": "キャラクター案",
          "multiple": True,
          "instance_structure": {
            "role": {
              "type": "enum",
              "values": [
                "主人公",
                "相棒",
                "対立者",
                "補助キャラ"
              ]
            },
            "personality": {
              "type": "text"
            },
            "desire": {
              "type": "text"
            },
            "weakness": {
              "type": "text"
            }
          },
          "llm_generate": True,
          "optimize": True
        },
        {
          "id": "foreshadowing",
          "label": "伏線案",
          "multiple": True,
          "instance_structure": {
            "setup_scene": {
              "type": "text"
            },
            "payoff_scene": {
              "type": "text"
            },
            "description": {
              "type": "text"
            }
          },
          "llm_generate": True,
          "optimize": True
        }
      ]
    },

    "script": {
      "label": "脚本",
      "categories": [
        {
          "id": "scene",
          "label": "シーン",
          "multiple": True,
          "instance_structure": {
            "location": {
              "type": "text"
            },
            "purpose": {
              "type": "text"
            },
            "conflict": {
              "type": "text"
            }
          },
          "llm_generate": True,
          "optimize": True
        },
        {
          "id": "beat",
          "label": "ビート",
          "multiple": True,
          "instance_structure": {
            "trigger": {
              "type": "text"
            },
            "change": {
              "type": "text"
            }
          },
          "llm_generate": True,
          "optimize": True
        }
      ]
    },

    "paper": {
      "label": "論文",
      "categories": [
        {
          "id": "section",
          "label": "セクション案",
          "multiple": True,
          "instance_structure": {
            "section_type": {
              "type": "enum",
              "values": [
                "問題提起",
                "関連研究",
                "手法",
                "結果",
                "考察",
                "結論"
              ]
            },
            "key_point": {
              "type": "text"
            }
          },
          "llm_generate": True,
          "optimize": True
        }
      ]
    },

    "article": {
      "label": "記事",
      "categories": [
        {
          "id": "headline",
          "label": "見出し案",
          "multiple": True,
          "instance_structure": {
            "style": {
              "type": "enum",
              "values": [
                "疑問形",
                "結論先出し",
                "数字入り",
                "共感型"
              ]
            },
            "text": {
              "type": "text"
            }
          },
          "llm_generate": True,
          "optimize": True
        }
      ]
    },

    "essay": {
      "label": "随筆",
      "categories": [
        {
          "id": "motif",
          "label": "モチーフ",
          "multiple": True,
          "instance_structure": {
            "trigger": {
              "type": "text"
            },
            "reflection": {
              "type": "text"
            }
          },
          "llm_generate": True,
          "optimize": True
        }
      ]
    }
  }
}