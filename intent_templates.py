# intent_templates.py

COMMON_INTENTS = [
    ("genre", "ジャンル"),
    ("theme", "テーマ・主張"),
    ("audience", "想定読者"),
    ("tone", "文体・トーン"),
]

DOC_TYPE_INTENTS = {
    "小説": [
        ("worldview", "世界観"),
        ("era", "時代"),
        ("length", "長さ"),
    ],
    "脚本": [
        ("setting", "舞台"),
        ("duration", "想定尺"),
    ],
    "論文": [
        ("field", "分野"),
        ("research_question", "研究課題"),
        ("method", "研究手法"),
    ],
    "記事": [
        ("purpose", "目的"),
        ("angle", "切り口"),
    ],
    "随筆": [
        ("motif", "題材"),
    ],
}