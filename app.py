import os
import requests
import json
import time
from datetime import datetime
from flask import Flask, request, jsonify
import google.generativeai as genai
from concurrent.futures import ThreadPoolExecutor, as_completed
import re
import sys
import locale

# 【重要な修正1】より強力なUTF-8環境設定
os.environ['PYTHONIOENCODING'] = 'utf-8'
os.environ['LC_ALL'] = 'C.UTF-8'
os.environ['LANG'] = 'C.UTF-8'
os.environ['PYTHONUNBUFFERED'] = '1'  # バッファリング無効化

# 【重要な修正2】標準出力を強制的にUTF-8に設定
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
elif hasattr(sys.stdout, 'buffer'):
    # Pythonの古いバージョンの場合の対応
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, errors='replace')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, errors='replace')

# ロケール設定（エラーを無視）
try:
    locale.setlocale(locale.LC_ALL, 'C.UTF-8')
except:
    try:
        locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
    except:
        pass  # ロケール設定に失敗しても続行

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False  # 日本語JSON対応

# 【重要な修正3】より安全な文字列処理関数
def safe_string(text, default="N/A", force_ascii=False):
    """文字列を安全に処理する"""
    if text is None:
        return default
    
    try:
        if isinstance(text, bytes):
            text = text.decode('utf-8', errors='replace')
        
        text_str = str(text)
        
        if force_ascii:
            # ASCII文字のみに制限する場合
            safe_text = text_str.encode('ascii', errors='ignore').decode('ascii')
            return safe_text if safe_text.strip() else default
        else:
            # UTF-8として処理（推奨）
            return text_str.encode('utf-8', errors='replace').decode('utf-8')
            
    except Exception as e:
        print(f"String encoding error: {str(e)}", file=sys.stderr)
        return default

def safe_print(text, force_ascii=False):
    """【重要な修正4】完全に安全なprint関数"""
    try:
        if text is None:
            text = "None"
        
        # 文字列に変換
        text_str = str(text)
        
        if force_ascii:
            # ASCII文字のみで出力（最も安全）
            safe_text = text_str.encode('ascii', errors='ignore').decode('ascii')
            print(safe_text)
        else:
            # UTF-8として処理を試す
            try:
                print(text_str)
            except UnicodeEncodeError:
                # UTF-8出力が失敗した場合はASCII文字のみで出力
                ascii_text = text_str.encode('ascii', errors='ignore').decode('ascii')
                print(f"[ASCII-ONLY] {ascii_text}")
                
    except Exception as e:
        try:
            print(f"Print error occurred: {str(e)}")
        except:
            print("Critical print error - unable to display message")

# 設定（環境変数から取得）
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', 'AIzaSyC-nY_mkBTkQWwhcBWHCf-ng4as6_NaNSA')
EBAY_APP_ID = os.environ.get('EBAY_APP_ID', 'myappsal-PRD-30bd30580-765b58a1')
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
        """和風商品を検索"""
        url = f"{self.base_url}/item_summary/search"
        
        # 和風関連のキーワード
        japanese_keywords = [
            "japanese", "japan", "kimono", "sushi", "anime", "manga", 
            "zen", "samurai", "ninja", "katana", "sake", "ramen",
            "origami", "bonsai", "furoshiki", "yukata", "geta", "zori",
            "daruma", "kokeshi", "noren", "tenugui", "furoshiki"
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
            
            # レスポンスのエンコーディングを明示的にUTF-8に設定
            response.encoding = 'utf-8'
            result = response.json()
            return result
            
        except requests.exceptions.RequestException as e:
            safe_print(f"API request error: {safe_string(str(e), force_ascii=True)}", force_ascii=True)
            return None
        except json.JSONDecodeError as e:
            safe_print(f"JSON decode error: {safe_string(str(e), force_ascii=True)}", force_ascii=True)
            return None
        except Exception as e:
            safe_print(f"Parse error: {safe_string(str(e), force_ascii=True)}", force_ascii=True)
            return None
    
    def get_item_details(self, item_id):
        """商品詳細を取得"""
        url = f"{self.base_url}/item/{item_id}"
        
        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()
            response.encoding = 'utf-8'
            return response.json()
        except requests.exceptions.RequestException as e:
            safe_print(f"Item details error: {safe_string(str(e), force_ascii=True)}", force_ascii=True)
            return None
        except Exception as e:
            safe_print(f"Parse error: {safe_string(str(e), force_ascii=True)}", force_ascii=True)
            return None

class JapaneseProductAnalyzer:
    def __init__(self, model):
        self.model = model
    
    def analyze_product_data(self, products_data):
        """【重要な修正5】商品データを分析（エンコード問題対応）"""
        if not products_data:
            return "No data to analyze."
        
        # データを整理
        analysis_data = self._prepare_analysis_data(products_data)
        
        # 英語でプロンプトを作成（日本語を避ける）
        prompt = self._create_analysis_prompt_en(analysis_data)
        
        try:
            response = self.model.generate_content(prompt)
            result_text = response.text
            
            # 【重要】結果を安全な文字列に変換してprint問題を回避
            safe_result = safe_string(result_text, "Analysis completed but text encoding failed", force_ascii=True)
            
            # コンソール出力も安全に実行
            safe_print("Analysis completed successfully", force_ascii=True)
            
            return safe_result
            
        except Exception as e:
            error_msg = f"Analysis error: {safe_string(str(e), force_ascii=True)}"
            safe_print(error_msg, force_ascii=True)
            return error_msg
    
    def _prepare_analysis_data(self, products_data):
        """分析用のデータを準備（エンコード安全版）"""
        analysis_data = {
            'total_items': len(products_data),
            'categories': {},
            'price_ranges': {'0-10': 0, '10-50': 0, '50-100': 0, '100-500': 0, '500+': 0},
            'keywords': {},
            'sellers': {},
            'conditions': {},
            'shipping_info': {}
        }
        
        for item in products_data:
            # カテゴリー分析（安全な文字列処理）
            if 'categories' in item:
                for cat in item['categories']:
                    cat_name = safe_string(cat.get('categoryName', 'Unknown'), force_ascii=True)
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
            title = item.get('title', '')
            if title:
                title = safe_string(title, force_ascii=True).lower()
                japanese_keywords = ['japanese', 'japan', 'kimono', 'sushi', 'anime', 'manga', 'zen', 'samurai']
                for keyword in japanese_keywords:
                    if keyword in title:
                        analysis_data['keywords'][keyword] = analysis_data['keywords'].get(keyword, 0) + 1
            
            # 出品者分析（安全な文字列処理）
            seller = safe_string(item.get('seller', {}).get('username', 'Unknown'), force_ascii=True)
            analysis_data['sellers'][seller] = analysis_data['sellers'].get(seller, 0) + 1
            
            # 商品状態分析
            condition = safe_string(str(item.get('condition', 'Unknown')), force_ascii=True)
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
        """英語での分析用プロンプトを作成（ASCII文字のみ使用）"""
        return f"""
Please analyze the following eBay Japanese-style products data. Return analysis in English only, using ASCII characters.

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

Provide detailed and practical analysis in English only using standard ASCII characters.
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
        return token_data.get('access_token')
    except requests.exceptions.RequestException as e:
        safe_print(f"OAuth token error: {safe_string(str(e), force_ascii=True)}", force_ascii=True)
        return None
    except Exception as e:
        safe_print(f"OAuth parse error: {safe_string(str(e), force_ascii=True)}", force_ascii=True)
        return None

@app.route('/analyze-japanese-products', methods=['GET', 'POST'])
def analyze_japanese_products():
    """【重要な修正6】和風商品分析のメインエンドポイント（エンコード安全版）"""
    try:
        # パラメータ取得
        search_terms = request.args.get('search', 'collectibles')
        max_items = min(int(request.args.get('limit', 100)), 200)
        
        safe_print("=== eBay Japanese Products Analysis Start ===", force_ascii=True)
        safe_print(f"Search keywords: {search_terms}", force_ascii=True)
        safe_print(f"Max items: {max_items}", force_ascii=True)
        safe_print(f"Execution time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", force_ascii=True)
        
        # OAuthトークンの確認/取得
        oauth_token = EBAY_OAUTH_TOKEN
        if not oauth_token:
            safe_print("Getting new OAuth token...", force_ascii=True)
            oauth_token = get_ebay_oauth_token(EBAY_APP_ID, EBAY_CLIENT_SECRET)
            if not oauth_token:
                return jsonify({"error": "Failed to get OAuth token"}), 500
        
        # eBay API初期化
        ebay_api = EBayBrowseAPI(oauth_token)
        analyzer = JapaneseProductAnalyzer(model)
        
        # 商品データ収集
        safe_print("--- Collecting product data ---", force_ascii=True)
        all_products = []
        batch_size = 50
        
        for offset in range(0, max_items, batch_size):
            current_limit = min(batch_size, max_items - offset)
            safe_print(f"Batch {offset//batch_size + 1}: Getting {current_limit} items...", force_ascii=True)
            
            search_result = ebay_api.search_japanese_items(
                search_terms, 
                limit=current_limit, 
                offset=offset
            )
            
            if search_result and 'itemSummaries' in search_result:
                products = search_result['itemSummaries']
                all_products.extend(products)
                safe_print(f"Retrieved: {len(products)} items", force_ascii=True)
                time.sleep(1)
            else:
                safe_print("No search results found", force_ascii=True)
                break
        
        safe_print(f"Total items retrieved: {len(all_products)}", force_ascii=True)
        
        if not all_products:
            result = {"error": "No Japanese products found", "products_found": 0}
            safe_print("Result: No products found", force_ascii=True)
            return jsonify(result)
        
        # データ分析実行
        safe_print("--- AI Analysis in progress ---", force_ascii=True)
        analysis_result = analyzer.analyze_product_data(all_products)
        
        # 結果をコンソールに出力（安全版）
        safe_print("=" * 60, force_ascii=True)
        safe_print("eBay Japanese Products AI Analysis Result", force_ascii=True)
        safe_print("=" * 60, force_ascii=True)
        safe_print(analysis_result, force_ascii=True)
        safe_print("=" * 60, force_ascii=True)
        
        # サンプル商品情報も出力（安全な文字列処理）
        safe_print("Sample products (first 5 items):", force_ascii=True)
        for i, product in enumerate(all_products[:5], 1):
            try:
                title = safe_string(product.get('title', 'Unknown title'), force_ascii=True)
                price_val = product.get('price', {}).get('value', 'N/A')
                currency = product.get('price', {}).get('currency', '')
                seller = safe_string(product.get('seller', {}).get('username', 'N/A'), force_ascii=True)
                url = product.get('itemWebUrl', 'N/A')
                
                safe_print(f"{i}. {title}", force_ascii=True)
                safe_print(f"   Price: {price_val} {currency}", force_ascii=True)
                safe_print(f"   Seller: {seller}", force_ascii=True)
                safe_print(f"   URL: {url}", force_ascii=True)
            except Exception as e:
                safe_print(f"{i}. Product display error: {safe_string(str(e), force_ascii=True)}", force_ascii=True)
                continue
        
        # レスポンス作成（JSON内の日本語は問題ない）
        result = {
            "success": True,
            "analysis": analysis_result,
            "products_analyzed": len(all_products),
            "search_terms": search_terms,
            "timestamp": datetime.now().isoformat(),
            "sample_products": all_products[:10]
        }
        
        return jsonify(result)
        
    except Exception as e:
        error_msg = f"Analysis error occurred: {str(e)}"
        safe_print(f"Error: {error_msg}", force_ascii=True)
        return jsonify({"error": error_msg}), 500

@app.route('/health')
def health_check():
    """ヘルスチェック"""
    return jsonify({
        "status": "healthy", 
        "service": "eBay Japanese Products Analyzer",
        "timestamp": datetime.now().isoformat()
    })

@app.route('/')
def home():
    """ホームページ"""
    return jsonify({
        "service": "eBay Japanese Products Analyzer",
        "endpoints": {
            "/analyze-japanese-products": "GET/POST - Japanese products analysis",
            "/health": "GET - Health check"
        },
        "parameters": {
            "search": "Search keywords (default: 'collectibles')",
            "limit": "Max items (default: 100, max: 200)"
        },
        "example": "/analyze-japanese-products?search=anime&limit=50"
    })

if __name__ == '__main__':
    # 環境変数チェック
    required_vars = ['GEMINI_API_KEY', 'EBAY_APP_ID']
    missing_vars = [var for var in required_vars if not os.environ.get(var)]
    
    if missing_vars:
        safe_print(f"Warning: Missing environment variables: {missing_vars}", force_ascii=True)
        safe_print("Please set environment variables or specify directly in code.", force_ascii=True)
    
    # Renderのポート設定
    port = int(os.environ.get('PORT', 5000))
    
    safe_print("Starting eBay Japanese Products Analysis Server...", force_ascii=True)
    safe_print(f"Port: {port}", force_ascii=True)
    safe_print("Usage:", force_ascii=True)
    safe_print("  GET /analyze-japanese-products?search=kimono&limit=100", force_ascii=True)
    safe_print("  GET /health", force_ascii=True)
    
    app.run(host='0.0.0.0', port=port, debug=False)
