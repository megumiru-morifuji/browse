import os
import requests
import json
import time
from datetime import datetime
from flask import Flask, request, jsonify
import google.generativeai as genai
import re
import sys
import locale

# 強制的にUTF-8環境を設定（Renderでは無視されることもある）
os.environ['PYTHONIOENCODING'] = 'utf-8'
os.environ['LC_ALL'] = 'C.UTF-8'
os.environ['LANG'] = 'C.UTF-8'

# ロケール設定
try:
    locale.setlocale(locale.LC_ALL, 'C.UTF-8')
except:
    try:
        locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
    except:
        pass

# 出力エンコーディング設定（Renderでは無効な場合あり）
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except:
        pass

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False  # 日本語JSON対応

# 安全な文字列変換（必ずASCIIに落とす）
def safe_string(text, default="N/A"):
    if text is None:
        return default
    try:
        if isinstance(text, bytes):
            text = text.decode('utf-8', errors='replace')
        text_str = str(text)
        # ASCII以外を?に置き換え
        return text_str.encode('ascii', errors='replace').decode('ascii')
    except Exception:
        return default

# 安全なprint
def safe_print(text):
    try:
        safe_text = safe_string(text)
        print(safe_text)
    except:
        pass

# 環境変数
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', 'YOUR_KEY')
EBAY_APP_ID = os.environ.get('EBAY_APP_ID', 'YOUR_APP_ID')
EBAY_CLIENT_SECRET = os.environ.get('EBAY_CLIENT_SECRET', '')
EBAY_OAUTH_TOKEN = os.environ.get('EBAY_OAUTH_TOKEN', '')

# Gemini API初期化
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-pro')

class EBayBrowseAPI:
    def __init__(self, oauth_token):
        self.oauth_token = oauth_token
        self.base_url = "https://api.ebay.com/buy/browse/v1"
        self.headers = {
            'Authorization': f'Bearer {oauth_token}',
            'Content-Type': 'application/json',
            'X-EBAY-C-MARKETPLACE-ID': 'EBAY_US',
            'X-EBAY-C-ENDUSERCTX': 'affiliateCampaignId=<ePNCampaignId>,affiliateReferenceId=<referenceId>'
        }
    
    def search_japanese_items(self, keywords, limit=50, offset=0):
        url = f"{self.base_url}/item_summary/search"
        japanese_keywords = [
            "japanese", "japan", "kimono", "sushi", "anime", "manga", 
            "zen", "samurai", "ninja", "katana", "sake", "ramen",
            "origami", "bonsai", "furoshiki", "yukata", "geta", "zori",
            "daruma", "kokeshi", "noren", "tenugui"
        ]
        search_query = f"{keywords} (" + " OR ".join(japanese_keywords) + ")"
        
        params = {
            'q': search_query,
            'limit': limit,
            'offset': offset,
            'sort': 'newlyListed',
            'filter': 'buyingOptions:{FIXED_PRICE}',
            'fieldgroups': 'MATCHING_ITEMS,EXTENDED'
        }
        
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            response.raise_for_status()
            response.encoding = 'utf-8'
            return response.json()
        except Exception as e:
            safe_print(f"API request error: {e}")
            return None

    def get_item_details(self, item_id):
        url = f"{self.base_url}/item/{item_id}"
        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()
            response.encoding = 'utf-8'
            return response.json()
        except Exception as e:
            safe_print(f"Item details error: {e}")
            return None

class JapaneseProductAnalyzer:
    def __init__(self, model):
        self.model = model
    
    def analyze_product_data(self, products_data):
        if not products_data:
            return "No data to analyze."
        analysis_data = self._prepare_analysis_data(products_data)
        prompt = self._create_analysis_prompt_en(analysis_data)
        try:
            response = self.model.generate_content(prompt)
            return safe_string(response.text, "Analysis completed but text encoding failed")
        except Exception as e:
            safe_print(f"Analysis error: {e}")
            return f"Analysis error: {safe_string(str(e))}"
    
    def _prepare_analysis_data(self, products_data):
        analysis_data = {
            'total_items': len(products_data),
            'categories': {},
            'price_ranges': {'0-10': 0, '10-50': 0, '50-100': 0, '100-500': 0, '500+': 0},
            'keywords': {},
            'sellers': {},
            'conditions': {}
        }
        for item in products_data:
            if 'categories' in item:
                for cat in item['categories']:
                    cat_name = cat.get('categoryName', 'Unknown')
                    analysis_data['categories'][cat_name] = analysis_data['categories'].get(cat_name, 0) + 1
            price = self._extract_price(item.get('price', {}))
            if price is not None:
                if price < 10:
                    analysis_data['price_ranges']['0-10'] += 1
                elif price < 50:
                    analysis_data['price_ranges']['10-50'] += 1
                elif price < 100:
                    analysis_data['price_ranges']['50-100'] += 1
                elif price < 500:
                    analysis_data['price_ranges']['100-500'] += 1
                else:
                    analysis_data['price_ranges']['500+'] += 1
            title = safe_string(item.get('title', '')).lower()
            for keyword in ['japanese', 'japan', 'kimono', 'sushi', 'anime', 'manga', 'zen', 'samurai']:
                if keyword in title:
                    analysis_data['keywords'][keyword] = analysis_data['keywords'].get(keyword, 0) + 1
            seller = safe_string(item.get('seller', {}).get('username', 'Unknown'))
            analysis_data['sellers'][seller] = analysis_data['sellers'].get(seller, 0) + 1
            condition = safe_string(item.get('condition', 'Unknown'))
            analysis_data['conditions'][condition] = analysis_data['conditions'].get(condition, 0) + 1
        return analysis_data
    
    def _extract_price(self, price_data):
        if isinstance(price_data, dict):
            value = price_data.get('value')
            try:
                return float(value)
            except:
                return None
        return None
    
    def _create_analysis_prompt_en(self, data):
        return f"""
Please analyze the following eBay Japanese-style products data. Return analysis in English.

Data Summary:
- Total items: {data['total_items']}
- Categories: {json.dumps(data['categories'], ensure_ascii=True)}
- Price ranges (USD): {json.dumps(data['price_ranges'], ensure_ascii=True)}
- Popular keywords: {json.dumps(data['keywords'], ensure_ascii=True)}
- Top sellers: {json.dumps(dict(list(data['sellers'].items())[:10]), ensure_ascii=True)}
- Item conditions: {json.dumps(data['conditions'], ensure_ascii=True)}

Please analyze from these perspectives:
1. Most popular Japanese product categories
2. Price range trends and market insights
3. Popular keyword trends
4. Seller characteristics (individual vs business)
5. Item condition trends
6. Marketing opportunities and recommendations
7. Competitive analysis insights
"""

def get_ebay_oauth_token(client_id, client_secret):
    import base64
    url = "https://api.ebay.com/identity/v1/oauth2/token"
    credentials = f"{client_id}:{client_secret}"
    credentials_b64 = base64.b64encode(credentials.encode()).decode('ascii')
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Authorization': f'Basic {credentials_b64}'
    }
    data = {
        'grant_type': 'client_credentials',
        'scope': 'https://api.ebay.com/oauth/api_scope'
    }
    try:
        response = requests.post(url, headers=headers, data=data, timeout=30)
        response.raise_for_status()
        return response.json().get('access_token')
    except Exception as e:
        safe_print(f"OAuth token error: {e}")
        return None

@app.route('/analyze-japanese-products', methods=['GET', 'POST'])
def analyze_japanese_products():
    try:
        search_terms = request.args.get('search', 'collectibles')
        max_items = min(int(request.args.get('limit', 100)), 200)
        
        safe_print(f"=== eBay Japanese Products Analysis Start ===")
        safe_print(f"Search keywords: {search_terms}")
        safe_print(f"Max items: {max_items}")
        safe_print(f"Execution time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        oauth_token = EBAY_OAUTH_TOKEN or get_ebay_oauth_token(EBAY_APP_ID, EBAY_CLIENT_SECRET)
        if not oauth_token:
            return jsonify({"error": "Failed to get OAuth token"}), 500
        
        ebay_api = EBayBrowseAPI(oauth_token)
        analyzer = JapaneseProductAnalyzer(model)
        
        all_products = []
        batch_size = 50
        for offset in range(0, max_items, batch_size):
            current_limit = min(batch_size, max_items - offset)
            search_result = ebay_api.search_japanese_items(search_terms, limit=current_limit, offset=offset)
            if search_result and 'itemSummaries' in search_result:
                products = search_result['itemSummaries']
                all_products.extend(products)
                time.sleep(1)
            else:
                break
        
        if not all_products:
            return jsonify({"error": "No Japanese products found", "products_found": 0})
        
        analysis_result = analyzer.analyze_product_data(all_products)
        
        return jsonify({
            "success": True,
            "analysis": analysis_result,
            "products_analyzed": len(all_products),
            "search_terms": search_terms,
            "timestamp": datetime.now().isoformat(),
            "sample_products": all_products[:10]
        })
        
    except Exception as e:
        return jsonify({"error": f"分析中にエラーが発生しました: {safe_string(str(e))}"}), 500

@app.route('/health')
def health_check():
    return jsonify({
        "status": "healthy",
        "service": "eBay Japanese Products Analyzer",
        "timestamp": datetime.now().isoformat()
    })

@app.route('/')
def home():
    return jsonify({
        "service": "eBay Japanese Products Analyzer",
        "endpoints": {
            "/analyze-japanese-products": "GET/POST - 和風商品分析実行",
            "/health": "GET - ヘルスチェック"
        },
        "parameters": {
            "search": "検索キーワード (デフォルト: 'collectibles')",
            "limit": "最大取得件数 (デフォルト: 100, 最大: 200)"
        },
        "example": "/analyze-japanese-products?search=anime&limit=50"
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    safe_print("Starting eBay Japanese Products Analysis Server...")
    safe_print(f"Port: {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
