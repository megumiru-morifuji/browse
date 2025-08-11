import os
import requests
import json
import time
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai
import sys

# 最小限のエンコーディング設定
os.environ['PYTHONIOENCODING'] = 'utf-8'

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False  # 日本語JSON対応

# CORS設定を追加（重要！）
CORS(app, origins=[
    "https://browse-ursn.onrender.com",  # あなたのサイト
    "https://*.onrender.com",  # 全てのRenderドメイン
    "http://localhost:*",  # ローカル開発用
    "https://localhost:*"  # ローカル開発用（HTTPS）
])

# 設定
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', 'AIzaSyC-nY_mkBTkQWwhcBWHCf-ng4as6_NaNSA')
EBAY_APP_ID = os.environ.get('EBAY_APP_ID', 'myappsal-PRD-30bd30580-765b58a1')
EBAY_CLIENT_SECRET = os.environ.get('EBAY_CLIENT_SECRET', '')
EBAY_OAUTH_TOKEN = os.environ.get('EBAY_OAUTH_TOKEN', '')

# Gemini API初期化
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-pro')

# ログ機能（コンソール出力なし、メモリに保存）
class Logger:
    def __init__(self):
        self.logs = []
        self.max_logs = 100
    
    def log(self, message):
        """ログをメモリに保存（完全に安全な文字列処理）"""
        try:
            timestamp = datetime.now().strftime('%H:%M:%S')
            
            # 文字列を安全に処理（日本語やUnicode文字を除去）
            if message is None:
                message = "None"
            
            # 文字列に変換し、ASCII文字のみ保持
            message_str = str(message)
            safe_message = message_str.encode('ascii', errors='ignore').decode('ascii')
            
            # 空文字列の場合のデフォルト
            if not safe_message.strip():
                safe_message = "Message contained non-ASCII characters"
            
            log_entry = f"[{timestamp}] {safe_message}"
            self.logs.append(log_entry)
            
            # 古いログを削除
            if len(self.logs) > self.max_logs:
                self.logs = self.logs[-self.max_logs:]
                
        except Exception as e:
            # ログ処理自体でエラーが発生した場合
            timestamp = datetime.now().strftime('%H:%M:%S')
            error_log = f"[{timestamp}] Log processing error occurred"
            self.logs.append(error_log)
    
    def get_recent_logs(self, count=20):
        """最新のログを取得"""
        return self.logs[-count:] if self.logs else []

# グローバルログインスタンス
logger = Logger()

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
            logger.log(f"API request started with limit: {limit}")
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            response.raise_for_status()
            response.encoding = 'utf-8'
            
            result = response.json()
            items_count = len(result.get('itemSummaries', []))
            logger.log(f"API response received: {items_count} items")
            
            return result
            
        except requests.exceptions.RequestException as e:
            logger.log(f"API request failed: HTTP error occurred")
            return None
        except json.JSONDecodeError as e:
            logger.log(f"JSON parsing failed: Invalid response format")
            return None
        except Exception as e:
            logger.log(f"Unexpected error: API call failed")
            return None
    
    def get_item_details(self, item_id):
        """商品詳細を取得"""
        url = f"{self.base_url}/item/{item_id}"
        
        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()
            response.encoding = 'utf-8'
            return response.json()
        except Exception as e:
            logger.log(f"Item details request failed")
            return None

class JapaneseProductAnalyzer:
    def __init__(self, model):
        self.model = model
    
    def analyze_product_data(self, products_data):
        """商品データを分析（コンソール出力なし）"""
        if not products_data:
            return "データがありません。"
        
        logger.log("AI analysis started")
        analysis_data = self._prepare_analysis_data(products_data)
        
        # 日本語でプロンプトを作成（問題なし）
        prompt = self._create_analysis_prompt_jp(analysis_data)
        
        try:
            response = self.model.generate_content(prompt)
            result_text = response.text
            
            logger.log("AI analysis completed successfully")
            
            # 日本語の結果をそのまま返す（JSON APIレスポンスなので問題なし）
            return result_text
            
        except Exception as e:
            error_msg = f"分析エラー: {str(e)}"
            logger.log(error_msg)
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
                title = title.lower()
                japanese_keywords = ['japanese', 'japan', 'kimono', 'sushi', 'anime', 'manga', 'zen', 'samurai']
                for keyword in japanese_keywords:
                    if keyword in title:
                        analysis_data['keywords'][keyword] = analysis_data['keywords'].get(keyword, 0) + 1
            
            # 出品者分析
            seller = item.get('seller', {}).get('username', 'Unknown')
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
    
    def _create_analysis_prompt_jp(self, data):
        """日本語での分析用プロンプトを作成（完全に問題なし）"""
        return f"""
以下のeBay和風商品データを分析して、詳細なマーケット分析レポートを日本語で作成してください。

データ概要:
- 総商品数: {data['total_items']}件
- カテゴリー別: {json.dumps(data['categories'], ensure_ascii=False, indent=2)}
- 価格帯別（USD）: {json.dumps(data['price_ranges'], ensure_ascii=False, indent=2)}
- 人気キーワード: {json.dumps(data['keywords'], ensure_ascii=False, indent=2)}
- 上位出品者: {json.dumps(dict(list(data['sellers'].items())[:10]), ensure_ascii=False, indent=2)}
- 商品状態別: {json.dumps(data['conditions'], ensure_ascii=False, indent=2)}

以下の観点から分析してください:

## 1. 人気和風商品カテゴリー分析
最も人気のあるカテゴリーとその特徴

## 2. 価格帯トレンド分析
各価格帯の商品数と市場の傾向

## 3. キーワードトレンド分析
検索で使われている人気キーワードの傾向

## 4. 出品者分析
個人出品者とビジネス出品者の特徴

## 5. 商品状態トレンド
新品・中古品などの状態別トレンド

## 6. マーケティング機会と推奨事項
ビジネス機会と参入戦略の提案

## 7. 競合分析インサイト
競合他社の動向と差別化ポイント

詳細で実践的な分析を日本語で提供してください。
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
        logger.log("OAuth token retrieved successfully")
        return token_data.get('access_token')
    except Exception as e:
        logger.log("OAuth token request failed")
        return None

@app.route('/analyze-japanese-products', methods=['GET', 'POST'])
def analyze_japanese_products():
    """和風商品分析のメインエンドポイント（コンソール出力なし版）"""
    try:
        # パラメータ取得
        search_terms = request.args.get('search', 'collectibles')
        max_items = min(int(request.args.get('limit', 100)), 200)
        
        logger.log("=== eBay Japanese Products Analysis Start ===")
        logger.log(f"Search keywords: {search_terms}")
        logger.log(f"Max items: {max_items}")
        
        # OAuthトークンの確認/取得
        oauth_token = EBAY_OAUTH_TOKEN
        if not oauth_token:
            logger.log("Getting new OAuth token...")
            oauth_token = get_ebay_oauth_token(EBAY_APP_ID, EBAY_CLIENT_SECRET)
            if not oauth_token:
                return jsonify({"error": "Failed to get OAuth token"}), 500
        
        # eBay API初期化
        ebay_api = EBayBrowseAPI(oauth_token)
        analyzer = JapaneseProductAnalyzer(model)
        
        # 商品データ収集
        logger.log("--- Collecting product data ---")
        all_products = []
        batch_size = 50
        
        for offset in range(0, max_items, batch_size):
            current_limit = min(batch_size, max_items - offset)
            logger.log(f"Batch {offset//batch_size + 1}: Getting {current_limit} items...")
            
            search_result = ebay_api.search_japanese_items(
                search_terms, 
                limit=current_limit, 
                offset=offset
            )
            
            if search_result and 'itemSummaries' in search_result:
                products = search_result['itemSummaries']
                all_products.extend(products)
                time.sleep(1)  # API制限対応
            else:
                logger.log("No search results found")
                break
        
        logger.log(f"Total items retrieved: {len(all_products)}")
        
        if not all_products:
            result = {"error": "和風商品が見つかりませんでした", "products_found": 0}
            return jsonify(result)
        
        # データ分析実行（日本語結果をそのまま取得）
        logger.log("--- AI Analysis in progress ---")
        analysis_result = analyzer.analyze_product_data(all_products)
        
        # レスポンス作成（日本語も含めて全て問題なし）
        result = {
            "success": True,
            "analysis": analysis_result,  # 日本語分析結果
            "products_analyzed": len(all_products),
            "search_terms": search_terms,
            "timestamp": datetime.now().isoformat(),
            "sample_products": all_products[:10],
            "logs": logger.get_recent_logs(10)  # 最新10件のログも含める
        }
        
        logger.log("Analysis completed successfully")
        return jsonify(result)
        
    except Exception as e:
        error_msg = f"分析中にエラーが発生しました: {str(e)}"
        logger.log(f"Error: {error_msg}")
        return jsonify({"error": error_msg, "logs": logger.get_recent_logs(5)}), 500

@app.route('/logs')
def get_logs():
    """実行ログを取得するエンドポイント"""
    count = int(request.args.get('count', 50))
    return jsonify({
        "logs": logger.get_recent_logs(count),
        "total_logs": len(logger.logs)
    })

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
            "/logs": "GET - 実行ログ取得",
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
    
    # 起動メッセージだけは最小限でprint（英語のみ）
    print("eBay Japanese Products Analysis Server starting...")
    print(f"Port: {port}")
    
    app.run(host='0.0.0.0', port=port, debug=False)
