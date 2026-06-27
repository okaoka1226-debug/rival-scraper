from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
import anthropic
import os
import json
import re

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class ScrapeRequest(BaseModel):
    url: str
    api_key: str

@app.get("/")
def root():
    return {"status": "ok", "message": "rival-scraper running"}

@app.post("/analyze")
async def analyze(req: ScrapeRequest):
    # シティヘブンのページを取得
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    }
    
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            response = await client.get(req.url, headers=headers)
            html = response.text
    except Exception as e:
        return {"error": f"ページの取得に失敗しました: {str(e)}"}

    # HTMLからテキストを抽出（簡易）
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'\s+', ' ', text).strip()
    text = text[:8000]  # Claudeに送るテキストを制限

    # Claude APIで解析
    prompt = f"""以下は風俗店のシティヘブンネット掲載ページのテキストです。
情報を抽出してJSON形式のみで回答してください（説明文・コードブロック不要）:

{{
  "name": "店舗名",
  "type": "deli または hotel または hybrid",
  "tel": "電話番号",
  "castCount": 在籍人数(数値またはnull),
  "price60": 60分通常価格(数値またはnull),
  "price60new": 60分新規最安値(数値またはnull),
  "price90": 90分価格(数値またはnull),
  "price120": 120分価格(数値またはnull),
  "shimei": 指名料(数値またはnull),
  "specialShimei": 特別指名料(数値またはnull),
  "entryFee": 入会金(数値またはnull),
  "totalReviews": 口コミ総数(数値またはnull),
  "scores": {{
    "hp": HPの作り込み・情報設計(0-100),
    "profile": プロフ画像クオリティ(0-100),
    "reviews": 口コミ数・信頼度(0-100),
    "price": 価格競争力(0-100),
    "cast": 在籍数・多様性(0-100)
  }},
  "aiTags": [{{"text": "タグ名", "type": "good または warn または bad"}}],
  "aiSummary": "200文字以内のAI総評"
}}

ページテキスト:
{text}"""

    try:
        client = anthropic.Anthropic(api_key=req.api_key)
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}]
        )
        result_text = message.content[0].text.strip()
        json_match = re.search(r'\{[\s\S]*\}', result_text)
        if not json_match:
            return {"error": "JSONの解析に失敗しました"}
        return json.loads(json_match.group())
    except Exception as e:
        return {"error": f"AI解析に失敗しました: {str(e)}"}
