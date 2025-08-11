import os
import requests
import json
import time
import logging
import sys
from datetime import datetime
from flask import Flask, request, jsonify
import google.generativeai as genai

# エンコーディング設定を最優先で実行
os.environ['PYTHONIOENCODING'] = 'utf-8'
os.environ['LC_ALL'] = 'C.UTF-8'
os.environ['LANG'] = 'C.UTF-8'

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.StreamHandler(sys.stderr)
    ]
)

logger = logging.getLogger('ebay_analyzer')
logger.setLevel(logging.INFO)

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False

# 設定
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', 'AIzaSyC-nY_mkBTkQWwhcBWHCf-ng4as6_NaNSA')
EBAY_APP_ID = os.environ.get('EBAY_APP_ID', 'myappsal-PRD-30bd30580-765b58a1')
EBAY_CLIENT_SECRET = os.environ.get('EBAY_CLIENT_SECRET', '')
EBAY_OAUTH_TOKEN = os.environ.get('EBAY_OAUTH_TOKEN', '')

# Gemini API初期化
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-pro')

class MemoryLogger:
    def __init__(self):
        self.logs = []
        self.max_logs = 100
    
    def log(self, message):
        """UTF-8で安全にログを出力"""
        try:
            timestamp = datetime.now().strftime('%H:%M:%S')
            # ASCII文字のみでログエントリを作成
            safe_message = str(message).encode('ascii', errors='ignore').decode('ascii')
            log_entry = f"[{timestamp}] {safe_message}"
            self.logs.append(log_entry)
            
            # 安全な出力
            logger.info(safe_message)
            print(f"[EBAY_ANALYZER] {log_entry}", flush=True)
            sys.stdout.flush()
            
        except Exception as e:
            # ログ出力でエラーが発生した場合の緊急処理
            fallback_msg = f"[{timestamp}] Log encoding error: {str(e)}"
            print(fallback_msg, flush=True)
        
        # 古いログを削除
        if len(self.logs) > self.max_logs:
            self.logs = self.logs[-self.max_logs:]
    
    def get_recent_logs(self, count=20):
        return self.logs[-count:] if self.logs else []

memory_logger = MemoryLogger()

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
        """和風商品を検索（エンコーディング安全版）"""
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
            memory_logger.log(f"API request: {keywords} limit:{limit}")
            
            # セッションを使用してエンコーディングを制御
            session = requests.Session()
            session.headers.update(self.headers)
            
            response = session.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            # エンコーディングを明示的に設定
            response.encoding = 'utf-8'
            
            # レスポンステキストを安全に処理
            try:
                result = response.json()
            except json.JSONDecodeError:
                # JSONデコードに失敗した場合、テキストをクリーンアップ
                clean_text = response.text.encode('utf-8', errors='ignore').decode('utf-8')
                result = json.loads(clean_text)
            
            items_count = len(result.get('itemSummaries', []))
            memory_logger.log(f"API response: {items_count} items retrieved")
            
            # 日本語文字を含むデータをクリーンアップ
            cleaned_result = self._clean_response_data(result)
            return cleaned_result
            
        except requests.exceptions.RequestException as e:
            memory_logger.log(f"API request error: {str(e)}")
            return None
        except json.JSONDecodeError as e:
            memory_logger.log(f"JSON decode error: {str(e)}")
            return None
        except Exception as e:
            memory_logger.log(f"Parse error: {str(e)}")
            return None
    
    def _clean_response_data(self, data):
        """レスポンスデータから問題のある文字を除去"""
        try:
            # JSONを文字列に変換してからクリーンアップ
            json_str = json.dumps(data, ensure_ascii=True)
            return json.loads(json_str)
        except Exception as e:
            memory_logger.log(f"Data cleaning error: {str(e)}")
            # 最悪の場合、空のデータを返す
            return {"itemSummaries": []}
    
    def get_item_details(self, item_id):
        """商品詳細を取得"""
        url = f"{self.base_url}/item/{item_id}"
        
        try:
            session = requests.Session()
            session.headers.update(self.headers)
            response = session.get(url, timeout=30)
            response.raise_for_status()
            response.encoding = 'utf-8'
            return response.json()
        except Exception as e:
            memory_logger.log(f"Item details error: {str(e)}")
            return None

class JapaneseProductAnalyzer:
    def __init__(self, model):
        self.model = model
    
    def analyze_product_data(self, products_data):
        """商品データを分析（エンコーディング安全版）"""
        if not products_data:
            return "No data available for analysis."
        
        memory_logger.log("AI analysis started")
        analysis_data = self._prepare_analysis_data(products_data)
        
        # 英語でプロンプトを作成（エンコーディング問題回避）
        prompt = self._create_analysis_prompt_en(analysis_data)
        
        try:
            response = self.model.generate_content(prompt)
            result_text = response.text
            
            memory_logger.log("AI analysis completed successfully")
            return result_text
            
        except Exception as e:
            error_msg = f"Analysis error: {str(e)}"
            memory_logger.log(error_msg)
            return error_msg
    
    def _prepare_analysis_data(self, products_data):
        """分析用のデータを準備"""
        analysis_data = {
            'total_items': len(products_data),
            'categories': {},
            'price_ranges': {'0-10': 0, '10-50': 0, '50-100': 0, '100-500': 0, '500+': 0},
            'keywords': {},
            'sellers': {},
            'conditions': {},
        }
        
        for item in products_data:
            # カテゴリー分析（ASCII文字のみ処理）
            if 'categories' in item:
                for cat in item['categories']:
                    cat_name = str(cat.get('categoryName', 'Unknown'))
                    # ASCII文字のみに制限
                    cat_name = cat_name.encode('ascii', errors='ignore').decode('ascii')
                    if cat_name:
                        analysis_data['categories'][cat_name] = analysis_data['categories'].get(cat_name, 0) + 1
            
            # 価格帯分析
            price = self._extract_price(item.get('price', {}))
            if price:
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
            
            # キーワード分析（ASCII文字のみ）
            title = str(item.get('title', ''))
            title = title.encode('ascii', errors='ignore').decode('ascii').lower()
            if title:
                japanese_keywords = ['japanese', 'japan', 'kimono', 'sushi', 'anime', 'manga', 'zen', 'samurai']
                for keyword in japanese_keywords:
                    if keyword in title:
                        analysis_data['keywords'][keyword] = analysis_data['keywords'].get(keyword, 0) + 1
            
            # 出品者分析（ASCII文字のみ）
            seller = str(item.get('seller', {}).get('username', 'Unknown'))
            seller = seller.encode('ascii', errors='ignore').decode('ascii')
            if seller:
                analysis_data['sellers'][seller] = analysis_data['sellers'].get(seller, 0) + 1
            
            # 商品状態分析
            condition = str(item.get('condition', 'Unknown'))
            analysis_data['conditions'][condition] = analysis_data['conditions'].get(condition, 0) + 1
        
        return analysis_data
    
    def _extract_price(self, price_data):
        """価格情報を抽出"""
        if isinstance(price_data, dict):
            value = price_data.get('value')
            if value:
                try:
                    return float(value)
                except (ValueError, TypeError):
                    pass
        return None
    
    def _create_analysis_prompt_en(self, data):
        """英語での分析用プロンプトを作成（エンコーディング問題回避）"""
        return f"""
Analyze the following eBay Japanese-style product data and create a detailed market analysis report in English.

Data Overview:
- Total products: {data['total_items']} items
- Categories: {json.dumps(data['categories'], ensure_ascii=True, indent=2)}
- Price ranges (USD): {json.dumps(data['price_ranges'], ensure_ascii=True, indent=2)}
- Popular keywords: {json.dumps(data['keywords'], ensure_ascii=True, indent=2)}
- Top sellers: {json.dumps(dict(list(data['sellers'].items())[:10]), ensure_ascii=True, indent=2)}
- Condition breakdown: {json.dumps(data['conditions'], ensure_ascii=True, indent=2)}

Please analyze from the following perspectives:

## 1. Popular Japanese Product Categories Analysis
Most popular categories and their characteristics

## 2. Price Range Trend Analysis
Product counts by price range and market trends

## 3. Keyword Trend Analysis
Popular search keywords and trends

## 4. Seller Analysis
Individual vs business seller characteristics

## 5. Product Condition Trends
New vs used product trends

## 6. Marketing Opportunities and Recommendations
Business opportunities and market entry strategies

## 7. Competitive Analysis Insights
Competitor trends and differentiation points

Please provide detailed and practical analysis in English.
"""

def get_ebay_oauth_token(client_id, client_secret):
    """Application OAuthトークンを取得"""
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
        token_data = response.json()
        memory_logger.log("OAuth token retrieved successfully")
        return token_data.get('access_token')
    except Exception as e:
        memory_logger.log(f"OAuth token error: {str(e)}")
        return None

@app.route('/analyze-japanese-products', methods=['GET', 'POST'])
def analyze_japanese_products():
    """和風商品分析のメインエンドポイント（エンコーディング安全版）"""
    try:
        search_terms = request.args.get('search', 'collectibles')
        max_items = min(int(request.args.get('limit', 50)), 100)  # 初期制限を下げる
        
        memory_logger.log("=== eBay Japanese Products Analysis Start ===")
        memory_logger.log(f"Search keywords: {search_terms}")
        memory_logger.log(f"Max items: {max_items}")
        
        # OAuthトークンの確認/取得
        oauth_token = EBAY_OAUTH_TOKEN
        if not oauth_token:
            memory_logger.log("Getting new OAuth token...")
            oauth_token = get_ebay_oauth_token(EBAY_APP_ID, EBAY_CLIENT_SECRET)
            if not oauth_token:
                error_msg = "Failed to get OAuth token"
                memory_logger.log(error_msg)
                return jsonify({"error": error_msg}), 500
        
        # eBay API初期化
        ebay_api = EBayBrowseAPI(oauth_token)
        analyzer = JapaneseProductAnalyzer(model)
        
        # 商品データ収集
        memory_logger.log("--- Collecting product data ---")
        all_products = []
        batch_size = 25  # バッチサイズを小さく
        
        for offset in range(0, max_items, batch_size):
            current_limit = min(batch_size, max_items - offset)
            memory_logger.log(f"Batch {offset//batch_size + 1}: Getting {current_limit} items...")
            
            search_result = ebay_api.search_japanese_items(
                search_terms, 
                limit=current_limit, 
                offset=offset
            )
            
            if search_result and 'itemSummaries' in search_result:
                products = search_result['itemSummaries']
                all_products.extend(products)
                time.sleep(2)  # API制限対応
            else:
                memory_logger.log("No search results found")
                break
        
        memory_logger.log(f"Total items retrieved: {len(all_products)}")
        
        if not all_products:
            error_msg = "No Japanese-style products found"
            memory_logger.log(error_msg)
            result = {"error": error_msg, "products_found": 0}
            return jsonify(result)
        
        # データ分析実行
        memory_logger.log("--- AI Analysis in progress ---")
        analysis_result = analyzer.analyze_product_data(all_products)
        
        # レスポンス作成（ASCII文字のみで安全）
        result = {
            "success": True,
            "analysis": analysis_result,
            "products_analyzed": len(all_products),
            "search_terms": search_terms,
            "timestamp": datetime.now().isoformat(),
            "sample_products": all_products[:5],  # サンプル数を減らす
            "logs": memory_logger.get_recent_logs(5)
        }
        
        memory_logger.log("Analysis completed successfully")
        return jsonify(result)
        
    except Exception as e:
        error_msg = f"Analysis error: {str(e)}"
        memory_logger.log(f"Error: {error_msg}")
        return jsonify({"error": error_msg, "logs": memory_logger.get_recent_logs(3)}), 500

@app.route('/logs')
def get_logs():
    """実行ログを取得するエンドポイント"""
    count = int(request.args.get('count', 50))
    return jsonify({
        "logs": memory_logger.get_recent_logs(count),
        "total_logs": len(memory_logger.logs)
    })

@app.route('/health')
def health_check():
    """ヘルスチェック"""
    memory_logger.log("Health check requested")
    return jsonify({
        "status": "healthy", 
        "service": "eBay Japanese Products Analyzer",
        "timestamp": datetime.now().isoformat()
    })

@app.route('/')
def home():
    """ホームページ"""
    memory_logger.log("Homepage accessed")
    return jsonify({
        "service": "eBay Japanese Products Analyzer (Encoding Safe)",
        "endpoints": {
            "/analyze-japanese-products": "GET/POST - Japanese product analysis",
            "/logs": "GET - Get execution logs",
            "/health": "GET - Health check"
        },
        "parameters": {
            "search": "Search keywords (default: 'collectibles')",
            "limit": "Max items to analyze (default: 50, max: 100)"
        },
        "example": "/analyze-japanese-products?search=anime&limit=25"
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    
    memory_logger.log("eBay Japanese Products Analysis Server starting...")
    memory_logger.log(f"Port: {port}")
    print("=== ENCODING SAFE SERVER STARTING ===", flush=True)
    
    app.run(host='0.0.0.0', port=port, debug=False)
