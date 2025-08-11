import os
import requests
import json
import time
from datetime import datetime
from flask import Flask, request, jsonify
import google.generativeai as genai
from concurrent.futures import ThreadPoolExecutor, as_completed
import re

app = Flask(__name__)

# 設定
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
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"API request error: {e}")
            return None
    
    def get_item_details(self, item_id):
        """商品詳細を取得"""
        url = f"{self.base_url}/item/{item_id}"
        
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Item details error: {e}")
            return None

class JapaneseProductAnalyzer:
    def __init__(self, model):
        self.model = model
    
    def analyze_product_data(self, products_data):
        """商品データを分析"""
        if not products_data:
            return "分析するデータがありません。"
        
        # データを整理
        analysis_data = self._prepare_analysis_data(products_data)
        
        # Geminiで分析
        prompt = self._create_analysis_prompt(analysis_data)
        
        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            print(f"Analysis error: {e}")
            return f"分析中にエラーが発生しました: {str(e)}"
    
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
            title = item.get('title', '').lower()
            japanese_keywords = ['japanese', 'japan', 'kimono', 'sushi', 'anime', 'manga', 'zen', 'samurai']
            for keyword in japanese_keywords:
                if keyword in title:
                    analysis_data['keywords'][keyword] = analysis_data['keywords'].get(keyword, 0) + 1
            
            # 出品者分析
            seller = item.get('seller', {}).get('username', 'Unknown')
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
    
    def _create_analysis_prompt(self, data):
        """分析用のプロンプトを作成"""
        return f"""
以下のeBayの和風商品データを詳細に分析してください。日本語で分析結果を返してください。

データ概要:
- 総商品数: {data['total_items']}
- カテゴリー分布: {json.dumps(data['categories'], ensure_ascii=False, indent=2)}
- 価格帯分布 (USD): {json.dumps(data['price_ranges'], ensure_ascii=False, indent=2)}
- 人気キーワード: {json.dumps(data['keywords'], ensure_ascii=False, indent=2)}
- 出品者分析: {json.dumps(dict(list(data['sellers'].items())[:10]), ensure_ascii=False, indent=2)}
- 商品状態: {json.dumps(data['conditions'], ensure_ascii=False, indent=2)}

以下の観点で分析してください:
1. 最も人気のある和風商品カテゴリー
2. 価格帯の傾向と市場動向
3. 人気キーワードから見るトレンド
4. 出品者の特徴（個人 vs 業者）
5. 商品状態の傾向
6. マーケティングの機会と推奨事項
7. 競合分析の観点

詳細で実用的な分析を日本語で提供してください。
"""

def get_ebay_oauth_token(client_id, client_secret):
    """Application OAuthトークンを取得"""
    url = "https://api.ebay.com/identity/v1/oauth2/token"
    
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Authorization': f'Basic {client_id}:{client_secret}'
    }
    
    data = {
        'grant_type': 'client_credentials',
        'scope': 'https://api.ebay.com/oauth/api_scope'
    }
    
    try:
        response = requests.post(url, headers=headers, data=data)
        response.raise_for_status()
        token_data = response.json()
        return token_data.get('access_token')
    except requests.exceptions.RequestException as e:
        print(f"OAuth token error: {e}")
        return None

@app.route('/analyze-japanese-products', methods=['GET', 'POST'])
def analyze_japanese_products():
    """和風商品分析のメインエンドポイント"""
    try:
        # パラメータ取得
        search_terms = request.args.get('search', 'collectibles')
        max_items = min(int(request.args.get('limit', 100)), 200)  # 最大200件
        
        print(f"=== eBay和風商品分析開始 ===")
        print(f"検索キーワード: {search_terms}")
        print(f"最大取得件数: {max_items}")
        print(f"実行時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # OAuthトークンの確認/取得
        oauth_token = EBAY_OAUTH_TOKEN
        if not oauth_token:
            print("OAuthトークンを新規取得中...")
            oauth_token = get_ebay_oauth_token(EBAY_APP_ID, EBAY_CLIENT_SECRET)
            if not oauth_token:
                return jsonify({"error": "OAuthトークンの取得に失敗しました"}), 500
        
        # eBay API初期化
        ebay_api = EBayBrowseAPI(oauth_token)
        analyzer = JapaneseProductAnalyzer(model)
        
        # 商品データ収集
        print("\n--- 商品データ収集中 ---")
        all_products = []
        batch_size = 50
        
        for offset in range(0, max_items, batch_size):
            current_limit = min(batch_size, max_items - offset)
            print(f"バッチ {offset//batch_size + 1}: {current_limit}件取得中...")
            
            search_result = ebay_api.search_japanese_items(
                search_terms, 
                limit=current_limit, 
                offset=offset
            )
            
            if search_result and 'itemSummaries' in search_result:
                products = search_result['itemSummaries']
                all_products.extend(products)
                print(f"取得完了: {len(products)}件")
                
                # API制限を考慮して待機
                time.sleep(1)
            else:
                print("検索結果が取得できませんでした")
                break
        
        print(f"\n総取得件数: {len(all_products)}件")
        
        if not all_products:
            result = {"error": "和風商品が見つかりませんでした", "products_found": 0}
            print("結果: 商品が見つかりませんでした")
            return jsonify(result)
        
        # データ分析実行
        print("\n--- AI分析実行中 ---")
        analysis_result = analyzer.analyze_product_data(all_products)
        
        # 結果をコンソールに出力
        print("\n" + "="*60)
        print("🎌 eBay和風商品 AI分析結果")
        print("="*60)
        print(analysis_result)
        print("="*60)
        
        # サンプル商品情報も出力
        print(f"\n📊 取得した商品サンプル (最初の5件):")
        for i, product in enumerate(all_products[:5], 1):
            print(f"\n{i}. {product.get('title', 'タイトル不明')}")
            print(f"   価格: {product.get('price', {}).get('value', 'N/A')} {product.get('price', {}).get('currency', '')}")
            print(f"   出品者: {product.get('seller', {}).get('username', 'N/A')}")
            print(f"   URL: {product.get('itemWebUrl', 'N/A')}")
        
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
        print(f"⚠️ 警告: 以下の環境変数が設定されていません: {missing_vars}")
        print("環境変数を設定するか、コード内で直接指定してください。")
    
    # Renderのポート設定
    port = int(os.environ.get('PORT', 5000))
    
    print("🚀 eBay和風商品分析サーバーを起動中...")
    print(f"Port: {port}")
    print("利用方法:")
    print("  GET /analyze-japanese-products?search=kimono&limit=100")
    print("  GET /health")
    
    app.run(host='0.0.0.0', port=port, debug=False)
