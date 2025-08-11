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

# 強制的にUTF-8環境を設定
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

# 文字エンコーディング設定
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except:
        pass

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False  # 日本語JSON対応

# 設定
def safe_string(text, default="N/A"):
    """文字列を安全に処理する"""
    if text is None:
        return default
    try:
        if isinstance(text, bytes):
            return text.decode('utf-8', errors='replace')
        text_str = str(text)
        # 問題となる文字を除去・置換
        safe_text = text_str.encode('ascii', errors='ignore').decode('ascii')
        if not safe_text.strip():
            # ASCII文字がない場合は、安全な文字のみ保持
            safe_text = ''.join(c for c in text_str if ord(c) < 128)
        return safe_text if safe_text else default
    except Exception:
        return default

def safe_print(text):
    """安全なprint関数"""
    try:
        safe_text = safe_string(str(text))
        print(safe_text)
    except Exception as e:
        print(f"Print error: {safe_string(str(e))}")
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', 'AIzaSyC-nY_mkBTkQWwhcBWHCf-ng4as6_NaNSA')
EBAY_APP_ID = os.environ.get('EBAY_APP_ID', 'myappsal-PRD-30bd30580-765b58a1')
EBAY_CLIENT_SECRET = os.environ.get('EBAY_CLIENT_SECRET', '')  # 環境変数で設定
EBAY_OAUTH_TOKEN = os.environ.get('EBAY_OAUTH_TOKEN', '')  # 取得済みのOAuthトークン

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
            'X-EBAY-C-MARKETPLACE-ID': 'EBAY_US',  # アメリカマーケット
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
            'sort': 'newlyListed',  # 新着順
            'filter': 'buyingOptions:{FIXED_PRICE}',  # Buy It Now のみ
            'fieldgroups': 'MATCHING_ITEMS,EXTENDED'
        }
        
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            response.raise_for_status()
            
            # レスポンスのエンコーディングを確認・設定
            if response.encoding is None or response.encoding.lower() != 'utf-8':
                response.encoding = 'utf-8'
            
            result = response.json()
            return result
            
        except requests.exceptions.RequestException as e:
            safe_print(f"API request error: {safe_string(str(e))}")
            return None
        except json.JSONDecodeError as e:
            safe_print(f"JSON decode error: {safe_string(str(e))}")
            return None
        except Exception as e:
            safe_print(f"Parse error: {safe_string(str(e))}")
            return None
    
    def get_item_details(self, item_id):
        """商品詳細を取得"""
        url = f"{self.base_url}/item/{item_id}"
        
        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()
            
            if response.encoding is None or response.encoding.lower() != 'utf-8':
                response.encoding = 'utf-8'
                
            return response.json()
        except requests.exceptions.RequestException as e:
            safe_print(f"Item details error: {safe_string(str(e))}")
            return None
        except Exception as e:
            safe_print(f"Parse error: {safe_string(str(e))}")
            return None

class JapaneseProductAnalyzer:
    def __init__(self, model):
        self.model = model
    
    def analyze_product_data(self, products_data):
        """商品データを分析"""
        if not products_data:
            return "No data to analyze."
        
        # データを整理
        analysis_data = self._prepare_analysis_data(products_data)
        
        # 日本語を避けて英語でプロンプトを作成
        prompt = self._create_analysis_prompt_en(analysis_data)
        
        try:
            response = self.model.generate_content(prompt)
            result_text = response.text
            
            # 結果を安全な文字列に変換
            safe_result = safe_string(result_text, "Analysis completed but text encoding failed")
            return safe_result
            
        except Exception as e:
            error_msg = f"Analysis error: {safe_string(str(e))}"
            safe_print(error_msg)
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
            'shipping_info': {}
        }
        
        for item in products_data:
            # カテゴリー分析
            if 'categories' in item:
                for cat in item['categories']:
                    cat_name = cat.get('categoryName', 'Unknown')
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
            
            # キーワード分析
            title = item.get('title', '')
            if title:
                # 安全な文字列処理
                title = safe_string(title).lower()
                japanese_keywords = ['japanese', 'japan', 'kimono', 'sushi', 'anime', 'manga', 'zen', 'samurai']
                for keyword in japanese_keywords:
                    if keyword in title:
                        analysis_data['keywords'][keyword] = analysis_data['keywords'].get(keyword, 0) + 1
            
            # 出品者分析
            seller = safe_string(item.get('seller', {}).get('username', 'Unknown'))
            analysis_data['sellers'][seller] = analysis_data['sellers'].get(seller, 0) + 1
            
            # 商品状態分析
            condition = item.get('condition', 'Unknown')
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
        """英語での分析用プロンプトを作成（文字エンコーディング問題を回避）"""
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

Provide detailed and practical analysis in English only.
"""

def get_ebay_oauth_token(client_id, client_secret):
    """Application OAuthトークンを取得"""
    import base64
    
    url = "https://api.ebay.com/identity/v1/oauth2/token"
    
    # Base64エンコーディング
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
        safe_print(f"OAuth token error: {safe_string(str(e))}")
        return None
    except Exception as e:
        safe_print(f"OAuth parse error: {safe_string(str(e))}")
        return None

@app.route('/analyze-japanese-products', methods=['GET', 'POST'])
def analyze_japanese_products():
    """和風商品分析のメインエンドポイント"""
    try:
        # パラメータ取得
        search_terms = request.args.get('search', 'collectibles')
        max_items = min(int(request.args.get('limit', 100)), 200)  # 最大200件
        
        safe_print(f"=== eBay Japanese Products Analysis Start ===")
        safe_print(f"Search keywords: {search_terms}")
        safe_print(f"Max items: {max_items}")
        safe_print(f"Execution time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # OAuthトークンの確認/取得
        oauth_token = EBAY_OAUTH_TOKEN
        if not oauth_token:
            safe_print("Getting new OAuth token...")
            oauth_token = get_ebay_oauth_token(EBAY_APP_ID, EBAY_CLIENT_SECRET)
            if not oauth_token:
                return jsonify({"error": "Failed to get OAuth token"}), 500
        
        # eBay API初期化
        ebay_api = EBayBrowseAPI(oauth_token)
        analyzer = JapaneseProductAnalyzer(model)
        
        # 商品データ収集
        safe_print("\n--- Collecting product data ---")
        all_products = []
        batch_size = 50
        
        for offset in range(0, max_items, batch_size):
            current_limit = min(batch_size, max_items - offset)
            safe_print(f"Batch {offset//batch_size + 1}: Getting {current_limit} items...")
            
            search_result = ebay_api.search_japanese_items(
                search_terms, 
                limit=current_limit, 
                offset=offset
            )
            
            if search_result and 'itemSummaries' in search_result:
                products = search_result['itemSummaries']
                all_products.extend(products)
                safe_print(f"Retrieved: {len(products)} items")
                
                # API制限を考慮して待機
                time.sleep(1)
            else:
                safe_print("No search results found")
                break
        
        safe_print(f"\nTotal items retrieved: {len(all_products)}")
        
        if not all_products:
            result = {"error": "No Japanese products found", "products_found": 0}
            safe_print("Result: No products found")
            return jsonify(result)
        
        # データ分析実行
        safe_print("\n--- AI Analysis in progress ---")
        analysis_result = analyzer.analyze_product_data(all_products)
        
        # 結果をコンソールに出力
        safe_print("\n" + "="*60)
        safe_print("eBay Japanese Products AI Analysis Result")
        safe_print("="*60)
        safe_print(analysis_result)
        safe_print("="*60)
        
        # サンプル商品情報も出力（安全な文字列処理）
        safe_print(f"\nSample products (first 5 items):")
        for i, product in enumerate(all_products[:5], 1):
            try:
                title = safe_string(product.get('title', 'Unknown title'))
                price_val = product.get('price', {}).get('value', 'N/A')
                currency = product.get('price', {}).get('currency', '')
                seller = safe_string(product.get('seller', {}).get('username', 'N/A'))
                url = product.get('itemWebUrl', 'N/A')
                
                safe_print(f"\n{i}. {title}")
                safe_print(f"   Price: {price_val} {currency}")
                safe_print(f"   Seller: {seller}")
                safe_print(f"   URL: {url}")
            except Exception as e:
                safe_print(f"\n{i}. Product display error: {safe_string(str(e))}")
                continue
        
        # レスポンス作成
        result = {
            "success": True,
            "analysis": analysis_result,
            "products_analyzed": len(all_products),
            "search_terms": search_terms,
            "timestamp": datetime.now().isoformat(),
            "sample_products": all_products[:10]  # サンプルとして最初の10件
        }
        
        return jsonify(result)
        
    except Exception as e:
        error_msg = f"分析中にエラーが発生しました: {str(e)}"
        print(f"❌ エラー: {error_msg}")
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
    # 環境変数チェック
    required_vars = ['GEMINI_API_KEY', 'EBAY_APP_ID']
    missing_vars = [var for var in required_vars if not os.environ.get(var)]
    
    if missing_vars:
        safe_print(f"Warning: Missing environment variables: {missing_vars}")
        safe_print("Please set environment variables or specify directly in code.")
    
    # Renderのポート設定
    port = int(os.environ.get('PORT', 5000))
    
    safe_print("Starting eBay Japanese Products Analysis Server...")
    safe_print(f"Port: {port}")
    safe_print("Usage:")
    safe_print("  GET /analyze-japanese-products?search=kimono&limit=100")
    safe_print("  GET /health")
    
    app.run(host='0.0.0.0', port=port, debug=False)
