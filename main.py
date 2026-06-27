from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
import anthropic
import re
import json
 
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
 
async def fetch_page(url: str) -> str:
    # 複数のUser-Agentとヘッダーを試す
    headers_list = [
        {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ja-JP,ja;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://www.google.co.jp/",
        },
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
            "Referer": "https://www.cityheaven.net/",
        },
        {
            "User-Agent": "Googlebot/2.1 (+http://www.google.com/bot.html)",
            "Accept": "text/html",
        }
    ]
    
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        for headers in headers_list:
            try:
                response = await client.get(url, headers=headers)
                text = response.text
                # ブロックされてるか確認
                if len(text) > 3000 and "料金" in text or "在籍" in text or "デリヘル" in text:
                    return text
            except Exception:
                continue
    return ""
 
@app.post("/analyze")
async def analyze(req: ScrapeRequest):
    html = await fetch_page(req.url)
    
    # HTMLからテキストを抽出
    text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    text = text[:10000]
 
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
 
{'ページテキスト:' + text if text else 'ページの取得ができませんでした。URLから推測できる情報のみで回答してください。URL: ' + req.url}"""
 
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
