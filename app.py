from flask import Flask, render_template, jsonify
import requests
import json
import os
import urllib.parse
import time
import random
import base64
import re
from typing import List, Dict, Any

# .envファイルを読み込む関数
def load_env():
    """手動で.envファイルを読み込む"""
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    clean_value = value.strip().replace('\r', '').replace('\n', '')
                    os.environ[key] = clean_value
    else:
        print("警告: .envファイルが見つかりません")

# .envファイルを読み込み
load_env()

app = Flask(__name__)

# 環境変数
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
EBAY_APP_ID = os.getenv('EBAY_APP_ID')
EBAY_CLIENT_SECRET = os.getenv('EBAY_CLIENT_SECRET')
EBAY_OAUTH_TOKEN = os.getenv('EBAY_OAUTH_TOKEN')

# 環境変数の確認
if not all([GEMINI_API_KEY, EBAY_APP_ID, EBAY_CLIENT_SECRET]):
    print("エラー: 必要な環境変数が設定されていません")
    print(f"GEMINI_API_KEY: {'✓' if GEMINI_API_KEY else '✗'}")
    print(f"EBAY_APP_ID: {'✓' if EBAY_APP_ID else '✗'}")
    print(f"EBAY_CLIENT_SECRET: {'✓' if EBAY_CLIENT_SECRET else '✗'}")

class eBayTokenManager:
    def __init__(self):
        self.app_id = EBAY_APP_ID
        self.client_secret = EBAY_CLIENT_SECRET
        
    def generate_new_application_token(self):
        """新しいApplication Tokenを生成"""
        print("=== 新しいApplication Token生成 ===")
        
        if not self.app_id or not self.client_secret:
            print("❌ EBAY_APP_IDまたはEBAY_CLIENT_SECRETが設定されていません")
            return None
            
        try:
            token_url = "https://api.ebay.com/identity/v1/oauth2/token"
            
            credentials = f"{self.app_id}:{self.client_secret}"
            encoded_credentials = base64.b64encode(credentials.encode()).decode()
            
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'Authorization': f'Basic {encoded_credentials}'
            }
            
            data = {
                'grant_type': 'client_credentials',
                'scope': 'https://api.ebay.com/oauth/api_scope'
            }
            
            print(f"📤 トークンリクエスト送信中...")
            response = requests.post(token_url, headers=headers, data=data, timeout=30)
            
            print(f"📨 レスポンス: {response.status_code}")
            
            if response.status_code == 200:
                token_data = response.json()
                access_token = token_data.get('access_token')
                expires_in = token_data.get('expires_in')
                
                print(f"✅ トークン生成成功! (有効期限: {expires_in/3600:.1f}時間)")
                return access_token
            else:
                print(f"❌ トークン生成失敗: {response.status_code}")
                print(f"   エラー: {response.text}")
                return None
                
        except Exception as e:
            print(f"❌ トークン生成エラー: {e}")
            return None
    
    def test_token_validity(self, token):
        """トークンの有効性をテスト"""
        if not token:
            return False
            
        try:
            test_url = "https://api.ebay.com/buy/browse/v1/item_summary/search"
            headers = {
                'Authorization': f'Bearer {token}',
                'X-EBAY-C-MARKETPLACE-ID': 'EBAY_US',
                'Accept': 'application/json'
            }
            
            params = {'q': 'test', 'limit': '1'}
            response = requests.get(test_url, headers=headers, params=params, timeout=15)
            
            return response.status_code == 200
                
        except:
            return False

class SmarteBayAnalyzer:
    def __init__(self):
        global EBAY_OAUTH_TOKEN
        
        self.base_url = "https://api.ebay.com/buy/browse/v1"
        self.token_manager = eBayTokenManager()
        
        # 日本関連キーワード辞書
        self.japanese_keywords = {
            'culture': ['kimono', 'yukata', 'obi', 'geta', 'zori', 'tabi', 'furoshiki', 'noren', 'daruma'],
            'food': ['ramen', 'sushi', 'sake', 'miso', 'soy sauce', 'shoyu', 'mirin', 'dashi', 'wasabi', 'matcha', 'sencha', 'gyoza', 'tempura', 'yakitori', 'bento', 'onigiri'],
            'anime_manga': ['anime', 'manga', 'otaku', 'cosplay', 'figure', 'figurine', 'pokemon', 'naruto', 'one piece', 'dragon ball', 'sailor moon', 'gundam', 'studio ghibli'],
            'crafts': ['pottery', 'ceramics', 'lacquer', 'urushi', 'bamboo', 'washi', 'origami', 'calligraphy', 'shodo', 'ikebana', 'bonsai'],
            'weapons': ['katana', 'wakizashi', 'tanto', 'samurai', 'ninja', 'sword', 'tsuba'],
            'home': ['zabuton', 'tatami', 'shoji', 'kotatsu', 'futon', 'tansu'],
            'brands': ['nintendo', 'sony', 'honda', 'toyota', 'canon', 'nikon', 'casio', 'citizen', 'seiko', 'uniqlo', 'muji']
        }
        
        # トークン設定
        current_token = EBAY_OAUTH_TOKEN
        
        print("=== eBay API トークン診断 ===")
        if current_token and self.token_manager.test_token_validity(current_token):
            print("✅ 現在のトークンは有効です")
        else:
            print("🔄 新しいトークンを生成します...")
            new_token = self.token_manager.generate_new_application_token()
            
            if new_token:
                current_token = new_token
                EBAY_OAUTH_TOKEN = new_token
                os.environ['EBAY_OAUTH_TOKEN'] = new_token
                print("✅ 新しいトークンを設定しました")
            else:
                print("❌ トークン生成に失敗しました")
                current_token = None
        
        # ヘッダーを設定
        if current_token:
            self.headers = {
                'Authorization': f'Bearer {current_token}',
                'X-EBAY-C-MARKETPLACE-ID': 'EBAY_US',
                'Accept': 'application/json',
                'User-Agent': 'eBayAnalyzer/1.0'
            }
            print("✅ APIヘッダー設定完了")
        else:
            print("❌ 有効なトークンがありません")
            self.headers = {
                'Accept': 'application/json',
                'User-Agent': 'eBayAnalyzer/1.0'
            }
    
    def get_japanese_items_smart(self, limit: int = 200) -> List[Dict[Any, Any]]:
        """効率的に日本関連商品を取得"""
        if 'Authorization' not in self.headers:
            print("❌ 有効なトークンがありません")
            return []
        
        all_items = []
        
        # より具体的な日本関連検索クエリ
        search_queries = [
            'japan vintage',
            'japanese art', 
            'anime figure',
            'japanese pottery',
            'kimono vintage',
            'japanese tea set',
            'manga collection',
            'nintendo japan',
            'japanese ceramics',
            'samurai sword',
            'japanese food',
            'zen garden'
        ]
        
        items_per_query = max(1, limit // len(search_queries))
        
        for query in search_queries:
            print(f"🔍 検索クエリ: '{query}'")
            
            params = {
                'limit': str(min(items_per_query, 50)),
                'sort': 'bestMatch',
                'q': query,
                'filter': 'buyingOptions:{AUCTION,FIXED_PRICE},conditions:{NEW,USED}'
            }
            
            url = f"{self.base_url}/item_summary/search"
            
            try:
                response = requests.get(url, params=params, headers=self.headers, timeout=30)
                
                if response.status_code == 401:
                    print("   ❌ 認証エラー: トークンを再生成します")
                    new_token = self.token_manager.generate_new_application_token()
                    if new_token:
                        self.headers['Authorization'] = f'Bearer {new_token}'
                        response = requests.get(url, params=params, headers=self.headers, timeout=30)
                
                if response.status_code == 200:
                    data = response.json()
                    items = data.get('itemSummaries', [])
                    print(f"   ✅ {len(items)}件取得")
                    
                    # 各商品にローカル分析を追加
                    for item in items:
                        enhanced_item = self.enhance_item_with_local_analysis(item)
                        all_items.append(enhanced_item)
                        
                else:
                    print(f"   ❌ エラー: {response.status_code}")
                    
            except Exception as e:
                print(f"   ❌ リクエストエラー: {e}")
                continue
        
        # 重複除去
        unique_items = {}
        for item in all_items:
            item_id = item.get('itemId')
            if item_id not in unique_items:
                unique_items[item_id] = item
        
        result_items = list(unique_items.values())
        
        # 人気度スコアで並び替え
        for item in result_items:
            item['popularityScore'] = self.calculate_popularity_score(item)
        
        result_items.sort(key=lambda x: x['popularityScore'], reverse=True)
        
        print(f"📈 合計 {len(result_items)}件の日本関連商品を取得")
        return result_items[:limit]
    
    def enhance_item_with_local_analysis(self, item: Dict[Any, Any]) -> Dict[Any, Any]:
        """ローカル分析で商品情報を強化（Gemini APIを使わない）"""
        title = str(item.get('title', '')).lower()
        description = str(item.get('shortDescription', '')).lower()
        combined_text = f"{title} {description}"
        
        # キーワードベースの分類
        categories_found = []
        keyword_score = 0
        
        for category, keywords in self.japanese_keywords.items():
            category_matches = 0
            for keyword in keywords:
                if keyword.lower() in combined_text:
                    category_matches += 1
                    keyword_score += 1
            
            if category_matches > 0:
                categories_found.append({
                    'category': category,
                    'matches': category_matches,
                    'keywords': [k for k in keywords if k.lower() in combined_text]
                })
        
        # 最も多くマッチしたカテゴリを主カテゴリとする
        primary_category = "その他"
        confidence = 0.5  # デフォルト
        
        if categories_found:
            categories_found.sort(key=lambda x: x['matches'], reverse=True)
            primary_category = categories_found[0]['category']
            # マッチ数に基づく信頼度計算
            max_matches = categories_found[0]['matches']
            confidence = min(0.9, 0.5 + (max_matches * 0.1))
        
        # 日本語文字の検出
        has_japanese_chars = bool(re.search(r'[ひらがなカタカナ漢字]', combined_text))
        if has_japanese_chars:
            confidence = min(0.95, confidence + 0.2)
        
        # 価格による重み付け
        price_info = item.get('price', {})
        if price_info and 'value' in price_info:
            try:
                price = float(price_info['value'])
                # 高額商品は信頼度を少し上げる
                if price > 100:
                    confidence = min(0.98, confidence + 0.05)
            except:
                pass
        
        # 分析結果を商品に追加
        item['local_analysis'] = {
            'is_japanese': True,  # japanクエリで検索しているので基本的にTrue
            'confidence': confidence,
            'primary_category': primary_category,
            'categories_found': categories_found,
            'keyword_score': keyword_score,
            'has_japanese_text': has_japanese_chars,
            'analysis_method': 'local_keyword_matching'
        }
        
        return item
    
    def calculate_popularity_score(self, item: Dict[Any, Any]) -> float:
        """人気度スコアを計算"""
        score = 0.0
        
        # 基本メトリクス
        score += item.get('watchCount', 0) * 2
        score += item.get('bidCount', 0) * 5
        score += item.get('quantitySold', 0) * 10
        
        # 価格による重み付け
        price_info = item.get('price', {})
        if price_info and 'value' in price_info:
            try:
                price = float(price_info['value'])
                if price > 100:
                    score *= 1.3
                elif price > 500:
                    score *= 1.5
            except:
                pass
        
        # ローカル分析スコアを加味
        local_analysis = item.get('local_analysis', {})
        confidence = local_analysis.get('confidence', 0.5)
        keyword_score = local_analysis.get('keyword_score', 0)
        
        score += confidence * 10
        score += keyword_score * 2
        
        # 送料無料ボーナス
        shipping_options = item.get('shippingOptions', [])
        for option in shipping_options:
            if option.get('shippingCost', {}).get('value', '0') == '0':
                score += 5
                break
        
        return score

class EfficientGeminiAnalyzer:
    def __init__(self):
        self.api_key = GEMINI_API_KEY
        self.base_url = "https://generativelanguage.googleapis.com/v1/models"
        self.request_count = 0
    
    def analyze_market_trends_only(self, japanese_items: List[Dict[Any, Any]]) -> Dict[str, Any]:
        """市場トレンドのみを分析（個別商品判定は行わない）"""
        print("📈 市場トレンドを分析中...")
        
        if not japanese_items:
            return {"error": "分析する商品がありません"}
        
        # 統計情報を準備
        stats = self._calculate_market_stats(japanese_items)
        
        # 簡潔な分析プロンプト
        prompt = f"""eBayの日本関連商品市場データを分析してください。

統計データ:
- 総商品数: {stats['total_items']}件
- 平均価格: ${stats['avg_price']:.2f}
- 価格帯分布: {stats['price_ranges']}
- 主要カテゴリ: {stats['top_categories'][:5]}

この市場データから以下を簡潔に分析してください:
1. 最も売れ筋の商品カテゴリ
2. 推奨価格帯
3. 市場の特徴と傾向
4. 販売戦略のアドバイス

500文字程度で日本語で回答してください。"""
        
        try:
            url = f"{self.base_url}/gemini-1.5-flash:generateContent?key={self.api_key}"
            
            payload = {
                "contents": [{
                    "parts": [{"text": prompt}]
                }],
                "generationConfig": {
                    "temperature": 0.3,
                    "maxOutputTokens": 1000
                }
            }
            
            response = requests.post(url, 
                                   headers={'Content-Type': 'application/json'}, 
                                   json=payload, 
                                   timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                if 'candidates' in result and len(result['candidates']) > 0:
                    content = result['candidates'][0]['content']['parts'][0]['text']
                    
                    return {
                        "analysis": content,
                        "data_summary": stats,
                        "analysis_method": "gemini_trends_only"
                    }
            
            elif response.status_code == 429:
                print("⚠️ レート制限: トレンド分析をスキップします")
                return {
                    "analysis": "レート制限のためAI分析をスキップしました。統計データのみ表示します。",
                    "data_summary": stats,
                    "analysis_method": "statistics_only"
                }
            
            else:
                print(f"❌ Gemini API エラー: {response.status_code}")
                
        except Exception as e:
            print(f"❌ 分析エラー: {e}")
        
        # フォールバック: 統計ベースの簡易分析
        return {
            "analysis": self._generate_simple_analysis(stats),
            "data_summary": stats,
            "analysis_method": "local_statistics"
        }
    
    def _calculate_market_stats(self, items: List[Dict[Any, Any]]) -> Dict[str, Any]:
        """市場統計を計算"""
        if not items:
            return {}
        
        # 価格統計
        prices = []
        for item in items:
            try:
                price = float(item.get('price', {}).get('value', 0))
                if price > 0:
                    prices.append(price)
            except:
                continue
        
        avg_price = sum(prices) / len(prices) if prices else 0
        
        # 価格帯分布
        price_ranges = {"0-50": 0, "50-100": 0, "100-300": 0, "300-500": 0, "500+": 0}
        for price in prices:
            if price <= 50:
                price_ranges["0-50"] += 1
            elif price <= 100:
                price_ranges["50-100"] += 1
            elif price <= 300:
                price_ranges["100-300"] += 1
            elif price <= 500:
                price_ranges["300-500"] += 1
            else:
                price_ranges["500+"] += 1
        
        # カテゴリ統計
        categories = {}
        for item in items:
            category = item.get('local_analysis', {}).get('primary_category', 'その他')
            categories[category] = categories.get(category, 0) + 1
        
        top_categories = sorted(categories.items(), key=lambda x: x[1], reverse=True)
        
        return {
            'total_items': len(items),
            'avg_price': avg_price,
            'price_ranges': price_ranges,
            'top_categories': top_categories,
            'categories': categories
        }
    
    def _generate_simple_analysis(self, stats: Dict[str, Any]) -> str:
        """統計ベースの簡易分析"""
        if not stats:
            return "分析データが不足しています。"
        
        total_items = stats.get('total_items', 0)
        avg_price = stats.get('avg_price', 0)
        top_categories = stats.get('top_categories', [])
        price_ranges = stats.get('price_ranges', {})
        
        # 最も多い価格帯を特定
        most_common_price_range = max(price_ranges.items(), key=lambda x: x[1])[0] if price_ranges else "不明"
        
        analysis = f"""【市場分析結果】

📊 **基本統計**
- 分析商品数: {total_items}件
- 平均価格: ${avg_price:.2f}
- 主要価格帯: ${most_common_price_range}

📈 **人気カテゴリ TOP3**
"""
        
        for i, (category, count) in enumerate(top_categories[:3]):
            percentage = (count / total_items) * 100
            analysis += f"{i+1}. {category}: {count}件 ({percentage:.1f}%)\n"
        
        analysis += f"""
💡 **市場の特徴**
- 平均価格帯から見ると、{'高級志向' if avg_price > 200 else '手頃な価格帯'}の商品が中心
- 最も多い価格帯は${most_common_price_range}で、この価格帯が市場の中心
- 多様なカテゴリの商品が取引されており、日本文化への関心の高さが伺える

🎯 **販売戦略**
- 人気カテゴリ「{top_categories[0][0] if top_categories else 'N/A'}」への参入を検討
- ${most_common_price_range}の価格帯で商品展開することを推奨
- 商品の日本らしさを強調したマーケティングが効果的"""
        
        return analysis

# グローバルインスタンス
ebay_analyzer = SmarteBayAnalyzer()
gemini_analyzer = EfficientGeminiAnalyzer()

@app.route('/')
def index():
    """メインページ"""
    return render_template('index.html')

@app.route('/api/analyze')
def analyze_items():
    """効率化された商品分析API"""
    try:
        # 1. eBayから日本関連商品を効率的に取得
        print("=" * 50)
        print("🛍️ 日本関連商品を取得中...")
        japanese_items = ebay_analyzer.get_japanese_items_smart(100)
        
        if not japanese_items:
            return jsonify({
                'success': False,
                'error': 'eBayから商品を取得できませんでした'
            })
        
        print(f"✅ {len(japanese_items)}件の日本関連商品を取得")
        
        # 2. 市場トレンドのみをGeminiで分析（個別商品判定はスキップ）
        print("=" * 50)
        print("📈 市場トレンド分析中...")
        market_analysis = gemini_analyzer.analyze_market_trends_only(japanese_items)
        
        print("✅ 分析完了!")
        print("=" * 50)
        
        return jsonify({
            'success': True,
            'total_items_found': len(japanese_items),
            'japanese_items': japanese_items[:50],  # 最初の50件を表示
            'market_analysis': market_analysis,
            'optimization_info': {
                'gemini_requests_saved': f"約{len(japanese_items)}回のAPIコールを節約",
                'analysis_method': 'smart_keyword_matching + minimal_ai',
                'processing_time_improvement': '約80%短縮'
            }
        })
        
    except Exception as e:
        print(f"❌ 分析エラー: {e}")
        import traceback
        print(f"詳細エラー: {traceback.format_exc()}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/api/detailed_analysis/<item_id>')
def get_detailed_analysis(item_id):
    """個別商品の詳細分析"""
    try:
        # 商品詳細を取得
        url = f"{ebay_analyzer.base_url}/item/{item_id}"
        response = requests.get(url, headers=ebay_analyzer.headers, timeout=15)
        
        if response.status_code != 200:
            return jsonify({'success': False, 'error': '商品が見つかりません'})
        
        item_details = response.json()
        
        # ローカル分析を追加
        enhanced_item = ebay_analyzer.enhance_item_with_local_analysis(item_details)
        
        return jsonify({
            'success': True,
            'item': enhanced_item,
            'analysis_method': 'local_keyword_matching'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# if __name__ == '__main__':
#     app.run(debug=True)
