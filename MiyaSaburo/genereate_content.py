import sys,os,re,time,json
import traceback
import openai, tiktoken
import tiktoken
from tiktoken.core import Encoding
import requests
from pathlib import Path
from dotenv import load_dotenv
from urllib.parse import urlparse
import tweepy
import tweepy.errors
from PIL import Image
from io import BytesIO
from tools.webSearchTool import WebSearchModule
from libs.utils import Utils
from tools.tweet_hist import TweetHist
from twitter_text import parse_tweet
from lxml.html import  HtmlElement, HtmlComment, HtmlMixin, HtmlEntity
from DxBotUtils import BotCore

if __name__ == "__main__":
    pre = os.getenv('OPENAI_API_KEY')
    Utils.load_env( ".miyasaburo.conf" )
    after = os.getenv('OPENAI_API_KEY')
    if after is not None and pre != after:
        print("UPDATE OPENAI_API_KEY")
        openai.api_key=after

tk_encoder = tiktoken.encoding_for_model("gpt-3.5-turbo")

##以下箇所は取得したAPI情報と置き換えてください。
class TwConfig:
    def __init__(self):
        self.reload()
    def reload(self):
        self.app_id = os.getenv('APP_ID')
        self.twitter_id = os.getenv('TWITTER_ID')
        # consumer keys
        self.api_key = os.getenv('API_KEY')
        self.api_key_secret = os.getenv('API_KEY_SECRET')
        # authentication tokens
        self.bearer_token = os.getenv('BEARER_TOKEN')
        self.access_token = os.getenv('ACCESS_TOKEN')
        self.access_token_secret = os.getenv('ACCESS_TOKEN_SECRET')
        self.client_id = os.getenv('CLIENT_ID')
        self.client_secret = os.getenv('CLIENT_SECRET')

def neko_news():
    bot:BotCore = BotCore()

    HIST_JSON:str = "tweet_history.json"

    config = TwConfig()
    tweeter_client = tweepy.Client(
        bearer_token = config.bearer_token,
        consumer_key= config.api_key,
        consumer_secret= config.api_key_secret,
        access_token= config.access_token,
        access_token_secret=config.access_token_secret,
    )

    module : WebSearchModule = WebSearchModule()
    dates = [ Utils.date_today(), Utils.date_today(-1), Utils.date_today(-2)]

    dates =  Utils.date_today(-60)
    n_return = 10
    LANG_JP='Japanese'
    query_jp = f"猫の話題 -site:www.youtube.com after:{dates}"
    query_en = f"Funny Cat News stories -site:www.youtube.com after:{dates}"

    go_tweet = True
    print("トレンドキーワードを収集する")
    trand_link:str = "https://search.yahoo.co.jp/realtime"
    sub_query = []
    try:
        # requestsを使用してWebページを取得
        response_html: HtmlElement = module.get_content_as_html( trand_link )
        tag_list = response_html.xpath("/html/body/div/div/div/div/div/div/article[h1/text()='トレンド']/section/ol/li/a/article/h1") 
        sub_query = [ tag.text_content() for tag in tag_list[:5]]
    except:
        pass

    print( f"トレンドキーワードを翻訳する")

    trans = "以下の単語を翻訳して"
    trans += "\n|単語|日本語|英語|"
    trans += "\n|---|---|---|"
    for w in sub_query:
        trans += f"\n|{w}|||"

    translate_result: str = bot.Completion(trans, max_tokens=2000) #Completion(trans, max_tokens=2000)
    if translate_result is None or len(translate_result)<20:
        print( f"ERROR: 評価結果が想定外\n{translate_result}")
        return
    else:
        translate_result = translate_result.replace('\n\n','\n')
        print(translate_result)
        print("--------")
        # 文字列を行に分割し、不要な行を取り除く
        lines = translate_result.strip().split("\n")
        # 各行をパースしてデータを取得
        data = [tuple(line.strip("|").split("|")) for line in lines]
        # データを辞書形式に変換
        buzz_list = [{"buzz_jp": jp, "buzz_en": en} for word,jp, en in data if not "日本語"==jp and not "---"==jp ]
        for p in buzz_list:
            print(p)
        print("----")

    main_list_jp = [ "猫 ニュース おもしろ", "猫 ニュース ほっこり", "猫 ニュース 可愛い" ]
    main_list_en = [ "Funny cat stories", "cute cat stories"]

    query_jp_list = [ (f"\"{bz['buzz_jp']}\" \"猫\" -site:www.youtube.com", { "num": 10, "qdr": "3y", "gl": "jp", "hl": "ja", "buzz_jp": bz['buzz_jp'], "buzz_en": bz['buzz_en'] }) for bz in buzz_list ]
    query_jp_list += [ (f"{q} -site:www.youtube.com after:{dates}", { "num": 20, "qdr": "3m", "gl": "jp", "hl": "ja", "q_jp": q }) for q in main_list_jp ]

    #query_en_list =[] # [ (f"\"{x}\" Funny Cat News stories -site:www.youtube.com",None) for x in sub_query ]
    #query_en_list += [ (query_en,{ "num": 20, "qdr": "3y", "gl": "uk", "hl": "en"}) ]

    query_en_list = [ (f"\"{bz['buzz_en']}\" Funny Cat News stories -site:www.youtube.com", { "num": 10, "qdr": "3y", "gl": "uk", "hl": "en", "buzz_jp": bz['buzz_jp'], "buzz_en": bz['buzz_en'] }) for bz in buzz_list ]
    query_en_list += [ (f"{q} -site:www.youtube.com after:{dates}", { "num": 20, "qdr": "3m", "gl": "uk", "hl": "en", "q_en": q }) for q in main_list_en ]

    detect_fmt = "下記の記事内容について\n\n記事タイトル:{}\n記事内容:\n{}\n\n"
    detect_fmt = f"{detect_fmt}下記の項目に答えて下さい。\n"
    detect_fmt = f"{detect_fmt}1)この記事に含まれる記事、アーティクル、話題のタイトルをリストアップして下さい\n"
    detect_fmt = f"{detect_fmt}2)この記事に含まれる国名・地名をリストアップして下さい\n"
    detect_fmt = f"{detect_fmt}3)地名は日本国内のものですか？\n"
    detect_fmt = f"{detect_fmt}4)この記事に日本語の「海外」という単語は含まれていますか？\n"
    detect_fmt = f"{detect_fmt}5)この記事に含まれる人物名、ねこの名前をリストアップして下さい\n"
    detect_fmt = f"{detect_fmt}6)人物名、名前は日本人っぽいですか？\n"
    detect_fmt = f"{detect_fmt}7)この記事に含まれるイベント、催し、公演等があればタイトルと日時をリストアップして下さい\n"
    detect_fmt = f"{detect_fmt}8)この記事から政治的、宗教的、反社会的、性差別的、暴力的な思想や思想誘導が含まれていればリストアップして下さい\n"
    detect_fmt = f"{detect_fmt}9)この記事から得られる教訓や示唆があればリストアップして下さい\n"
    detect_fmt = f"{detect_fmt}10)この記事の出来事についてニュースとなった特徴をリストアップして下さい\n"
    detect_fmt = f"{detect_fmt}\n\n上記の情報より下記の質問に回答して下さい\n"
    detect_fmt = f"{detect_fmt}11)この記事は日本国内の出来事ですか？海外での出来事ですか？(InsideJapan or OutsideJapanで回答すること)\n"
    detect_fmt = f"{detect_fmt}12)猫に関する記事ですか？(Cat or NotCatで回答すること)\n"
    detect_fmt = f"{detect_fmt}13)動物や生体の販売、広告ですか？(Sale or NotSaleで回答すること)\n"
    detect_fmt = f"{detect_fmt}14)政治的、宗教的、反社会的、性的、暴力的が含まれていますか？(Asocial or NotAsocialで回答すること)\n"
    detect_fmt = f"{detect_fmt}15)この記事に含まれる書籍、小説、ドラマ、映画、番組、演劇、公演、漫画、アニメーションをリストアップして下さい\n"
    detect_fmt = f"{detect_fmt}16)書籍、小説、ドラマ、映画、番組、演劇、公演、漫画、アニメなどの話題が含まれますか？(Media or NotMediaで回答すること)\n"
    detect_fmt = f"{detect_fmt}17)記事に複数の記事、アーティクル、話題が含まれますか？(Multi or Singleで回答すること)\n"

    article_fmt = "下記の記事をフォロワーに紹介するツイートを生成して下さい。\n記事タイトル:{}\n記事内容:\n{}"
    prompt_fmt1 = "\n".join( [
        "上記の記事から、制約条件とターゲットと留意点に沿って、バズるツイート内容を記述して下さいにゃ。",
        "",
        "制約条件：",
        "・投稿を見た人が興味を持つ内容",
        "・投稿を見た人から信頼を得られる内容",
        "・カジュアルな野良猫キャラクターのような口調",
        "",
        "ターゲット：",
        "・猫のニュースで癒やされたい人", # （タツイッーで発信ターゲットにしている属性）
        "・猫ニュースを面白く伝える", # （今回のツイートで発信している対象の属性）
        "・猫の知られざる世界を見てみたい人", #（上記の対象が課題に感じる場面の具体）
        "",
        "言語と文字数:",
        "ツイートは{}で{}文字以内にして下さいにゃ。絵文字は無し",
        "",
        "ツイート:"
    ] )
    prompt_fmt2 = "\n".join( [
        "上記の記事から、制約条件とターゲットと留意点に沿って、バズるツイート内容を記述して下さいにゃ。",
        "",
        "# 主なポイント:",
        "あなたがこのツイートで伝えたい主なポイントは何ですか？1-2文で要約して下さい。",
        "",
        "# ターゲットオーディエンス:",
        "あなたのツイートのターゲットオーディエンスは誰ですか？(例:若年層、ビジネスマン、健康志向の人など)",
        "",
        "# 読者層:",
        "ツイートの読者層は誰ですか？特定のグラフィック(年齢、性別、場所など)をターゲットにする必要がありますか？それぞれに合わせた魅力的なアプローチを考えてみましょう。",
        "",
        "# トーンやスタイル:",
        "あなたが望むトーンやスタイルは何ですかにゃ？(例:面白おかしく、真剣に、感動的になど)",
        "",
        "# 強調:",
        "コンパクトで興味を引くよう、強い、鮮やかな言葉を使用して感動的なインパクトを作り出す。不要な言葉やフレーズがないか確認する。注意を引くメッセージ、感情を喚起する可能性があります。",
    ] )
    prompt_fmt2 = "\n".join( [
        "上記の記事から、制約条件とターゲットと留意点に沿って、バズるツイート内容を記述して下さいにゃ。",
        "",
        "# トーンやスタイル:",
        "この記事のトーンやスタイルは何ですかにゃ？(例:面白おかしく、真剣に、感動的になど)",
        "",
        "# 主なポイント:",
        "あなたがこのツイートで伝えたい主なポイントは何ですか？1-2文で要約して下さい。",
        "",
        "# 強調:",
        "コンパクトで興味を引くよう、強い、鮮やかな言葉を使用して感動的なインパクトを作り出して下さい。",
    ] )

    evaluate_prompt = "\n".join([
        "次に、以下の5つの指標を20点満点で評価してくださいにゃ。",
        "1) 話題性：現在の流行やニュースなど、人々が興味を持つ話題に関連しているかにゃ？(0から20)",
        "2) エンゲージメント促進：ユーザーに反応を促すような要素を含んでいるかにゃ？(0から20)",
        "3) 付加価値：ジョークや皮肉が含まれているかにゃ？(0から20)",
        "4) リアリティ:猫っぽいセリフになっているかにゃ？(0から20)",
        "5) 文章の見やすさ:簡潔に解りやすい文章になっているかにゃ？(0から20)",
        "",
        "各指標の評価点数を入力したら、プログラムは自動的に合計点を計算し、それを100点満点で表示するにゃ。",
        "合計点数：",
        "",
        "そして、もっとバズるための改善点を考えてるにゃ",
        "改善点：",
    ])

    buzz_prompt = "\n\n# バズワード: 次のワードが現在のトレンドバズワードにゃ。\n{}"
    update_prompt = "\n\n上記を踏まえて、野良猫っぽい皮肉やジョークを含めたツイートを{}で{}文字以内で生成するにゃ。絵文字は無しにゃ\n# ツイート:"

    exclude_site = {
        "www.youtube.com": 1,
        "www.amazon.co.jp": 1, "www.amazon.com": 1,
        "m.facebook.com": 1, "www.tiktok.com": 1,
        "www.tbs.co.jp": 1,
        "www.oricon.co.jp": 1,
        "www.pixiv.net": 1,
        "www.buzzfeed.com": 1,
        "piapro.jp": 1,         "blog.piapro.jp": 1, "jp.mercari.com": 1,
        "search.rakuten.co.jp": 1,
        "docs.google.com": 1,
        "www.thoroughbreddailynews.com": 1, "www.jrha.or.jp": 1, #馬専門サイト
        "togetter.com": 1, "twilog.togetter.com": 1,
       # "cat.blogmura.com": 1,
    }
    exclude_host = [
        r"[^a-z]youtube\.", r"[^a-z]amazon\.", r"[^a-z]facebook\.", "[^a-z]tiktok\.",
        r"[^a-z]rakuten\.",r"[^a-z]mercari\.",r"[^a-z]google\.",
        r"[^a-z]tbs\.", r"[^a-z]abema\.",  r"[^a-z]jrha\.",
        r"[^a-z]oricon\.",r"[^a-z]pixiv\.",r"[^a-z]buzzfeed\.",r"[^a-z]piapro\.",r"[^a-z]togetter\.",
        r"[^a-z]pinterest\.",
    ]

    must_keywords = [
        "猫", "ねこ", "ネコ",
        "cat", "Cat",
    ]
    exclude_link = [ r"/tag/", r"/tags/", r"\.pdf$" ]
    exclude_title = [ r"[-0-9][1-9][0-9][^0-9]", r"^[1-9][0-9][^0-9]", r"PDF" ]
    exclude_keywords = [
        "記事が見つかりません","記事は見つかりません","公開期間が終了","公開期間を終了","公開期間は終了", "ページが見つかりません", "ページは見つかりません", "まとめ", "Page Not Found", "page not found", "Page not found",
        "販売", "価格", "値段", "譲渡会", "殺処分", "購入", "プロモーション", "%オフ", "％オフ", "%Off", "%OFF", "％OFF", "セール", "里親募集",
        "商品の説明", "商品の状態", "購入手続き", 
        "TBS","MBS","出演","テレビ局", "配信","放送",
        "ゲーム", "入荷",
        "ディズニー", "disney", "Disney",
        "韓国","Stray Kids","ストレイキッズ","アルバム", "ビジュアル",
        "Linux", "linux", "python", "Python",
        "ポケモン", "ピカチュウ", "pokemon", "Pokemon", "Pikachu", "Pikachu",
        ]

    hashtag_list_jp = [ "#猫", "#cats", "#猫好きさんと繋がりたい","#CatsOnTwitter", "#funnyanimals"]
    hashtag_list_en = [ "#cat", "#CatsAreFamily", "#pets", "#CatsOnTwitter", "#funnyanimals"]

    try:
        site_hist = TweetHist( "tweet_hist.json" )
    except Exception as ex:
        print(ex)
        print("履歴を読み込めませんでした")
       # return
    # ツイート履歴管理

    # 類似記事除外リミット
    sim_limit =0.98

    tw_count_max = 1
    output_jp = 0
    output_en = 0

    Ite = module.inerator2( query_jp_list, query_en_list, num_result=50, qdr=None, hl=None )
    for d in Ite:
        if output_jp>=tw_count_max and output_en>=tw_count_max:
            break
        site_title: str = d.get('title',"")
        site_link: str = d.get('link',"")
        site_prop: dict = d.get('prop',{})
        site_url: str = urlparse(site_link)
        site_hostname: str = site_url.netloc

        print("----記事判定---------------------------------------------------")
        print( f"記事タイトル:{site_title}")
        print( f"記事URL:{site_link}")
        print( f"prop:{site_prop}")
        if site_title.find("ノミ")>0:
            continue
        #---------------------------
        # サイト判定
        #---------------------------
        # トップページ
        if len(site_url.path)<2:
            print( f"SKIP:Top page {site_link}")
            continue
        # 除外ホスト
        if site_hostname.find("pinterest")>0:
            pass
        a = [ r for r in exclude_host if re.search( r, site_hostname ) ]
        if len(a)>0:
            print( f"SKIP: 除外ホストが含まれる: {a}")
            continue
        # 除外キーワード判定
        a=[ r for r in exclude_link if re.search( r, site_link) ]
        if len(a)>0:
            print( f"SKIP: 除外キーワードがタイトルに含まれる: {a}")
            continue
        a=[ r for r in exclude_title if re.search( r, site_title) ]
        if len(a)>0:
            print( f"SKIP: 除外キーワードがタイトルに含まれる: {a}")
            continue
        # 除外キーワード判定
        a=[ keyword for keyword in exclude_keywords if site_title.find(keyword)>=0]
        if len(a)>0:
            print( f"SKIP: 除外キーワードがタイトルに含まれる: {a}")
            continue
        # 除外サイト
        if exclude_site.get( site_hostname, None ) is not None or "manga" in site_link:
            print( f"SKIP:Exclude {site_link}")
            continue
        # 既に使ったサイト
        site_lastdt = site_hist.is_used( site_link, 1 )
        if site_lastdt is not None:
            print( f"SKIP: used site in {site_lastdt} {site_link}")
            continue
        #---------------------------
        # 記事内容判定
        #---------------------------
        # 記事本文を取得
        print( f"記事の本文取得....")
        site_text: str = module.get_content( site_link, type="title", timeout=15 )
        if site_text is None or site_text == '':
            print( f"ERROR: 本文の取得に失敗")
            continue
        if len(site_text)<100:
            print( f"ERROR: 本文が100文字以下")
            continue
        if len([line for line in site_text.split('\n') if line.strip()])<10:
            print( f"ERROR: 本文が10行以下")
            continue
        # 単純な言語判定
        simple_lang_jp:bool = Utils.contains_kana(site_text)
        buzz_word: str = None
        if simple_lang_jp:
            buzz_word = site_prop.get('buzz_jp',None)
            # 日本語記事ならば、日本の記事を英訳した可能性がある
        else:
            buzz_word = site_prop.get('buzz_en',None)
            # 日本語じゃない記事ならば日本語でツイートするのは確実
            if output_jp>=tw_count_max:
                print( f"SKIP: 日本語ツイート本数を超過" )
                continue
        # 必須キーワード判定
        a=[ keyword for keyword in must_keywords if site_text.find(keyword)>=0]
        if len(a)==0:
            print( f"SKIP: 必須キーワードが含まれない")
            continue
        # バズワード判定
        if buzz_word is not None and len(buzz_word)>0:
            if site_text.find( buzz_word )<0:
                print( f"SKIP: バズワードが含まれない")
                continue
        else:
            buzz_word=None
        # 除外キーワード判定
        a=[ keyword for keyword in exclude_keywords if site_text.find(keyword)>=0]
        if len(a)>0:
            print( f"SKIP: 除外キーワードが含まれる: {a}")
            continue
        # 記事の類似判定
        print( f"記事のembedding取得....")
        embedding = site_hist.get_embedding( site_text[:2000], sim_limit )
        if embedding is None:
            print( f"SKIP: 類似記事をツイート済み" )
            continue
        #---------------------------
        # 記事の評価
        #---------------------------
        print( f"記事の内容評価....")
        # LLMで内容を評価する
        detect_prompt = detect_fmt.format( site_title, site_text[:2000] )
        detect_count = 0
        post_lang = -1
        while post_lang<0 and detect_count<3:
            detect_count += 1
            detect_result: str = bot.Completion(detect_prompt,max_tokens=None) #Completion(detect_prompt,max_tokens=None)
            if detect_result is None or len(detect_result)<20:
                print( f"ERROR: 評価結果が想定外\n{detect_result}")
                break
            detect_result = detect_result.replace('\n\n','\n')
            print(detect_result)
            print("--------")
            post_lang = find_keyword(detect_result, "InsideJapan", "OutsideJapan")
        if post_lang<0:
            print( f"Error: 評価エラー: {site_title}\n {site_link}\n" )
            continue
        #---------------------------
        # 判定
        #---------------------------
        site_type = None
        post_lang = find_keyword(detect_result, "InsideJapan", "OutsideJapan")
        if post_lang!=0 and post_lang!=1:
            site_type = "言語判定エラー"
        elif post_lang==0 and not Utils.contains_kana(site_text):
            site_type = "日本語以外の記事で国内判定？"
        elif find_keyword( detect_result, "Single", "Multi" )!=0:
            site_type = "複数記事"
        elif find_keyword( detect_result, "Cat", "NotCat" )!=0:
            site_type = "猫記事じゃない"
        elif find_keyword(detect_result, "Media", "NotMedia")!=1:
            site_type = "メディア記事っぽい"
        elif find_keyword(detect_result, "Sale", "NotSale")!=1:
            site_type = "販売っぽい記事"
        elif find_keyword(detect_result, "Asocial", "NotAsocial")!=1:
            site_type = "不適切な記事"
        if site_type is not None:
            print( f"Error: {site_type} {site_title} {site_link}\n" )
            site_hist.put_site( site_link, site_text, embedding, site_type )
            continue
        #---------------------------
        # 投稿数判定
        #---------------------------
        if post_lang==0:
            if output_en>=tw_count_max:
                print( f"SKIP: 英語ツイート本数を超過" )
                continue
        else:
            if output_jp>=tw_count_max:
                print( f"SKIP: 日本語ツイート本数を超過" )
                continue
        #---------------------------
        # ポスト言語決定
        #---------------------------
        if post_lang==0:
            # 日本のニュースは英語でポスト
            post_lang='English'
            post_ln = "英語"
            tweet_tags = " ".join(hashtag_list_en)
        else:
            # 日本のニュースでないなら日本語でポスト
            post_lang=LANG_JP
            post_ln = "日本語"
            tweet_tags = " ".join(hashtag_list_jp)

        #---------------------------
        # ツイート文字数制限
        #---------------------------
        tags_count = count_tweet( " " + site_link + " " + tweet_tags )
        count_limit = 280 - tags_count
        if post_lang==LANG_JP:
            chars_limit = int(count_limit/2)
        else:
            chars_limit = int(count_limit*0.8)
        #---------------------------
        # 初期生成
        #---------------------------
        print("----ツイート生成---------------------------------------------------")
        print( f"記事タイトル:{site_title}")
        print( f"記事URL:{site_link}")
        user_input = None
        while user_input is None or (user_input != 'y' and user_input != 'n' ):
            user_input = input('y or n or p >> ')
            if user_input == 'p':
                print(site_text[:2000])
        if user_input!='y':
            print( f"SKIP: ユーザ判断によるスキップ" )
            continue

        msg_hist = []
        msg_hist += [ {"role": "user", "content": article_fmt.format( site_title, site_text[:2000] ) } ]
        gen_prompt = prompt_fmt2
        if buzz_word is not None:
            gen_prompt = gen_prompt + buzz_prompt.format(buzz_word)
        gen_prompt = gen_prompt + update_prompt.format(post_ln,chars_limit)
        msg_hist += [ {"role": "system", "content": gen_prompt } ]

        tweet_text = None
        tweet_score = 0
        tweet_count = 0
        try_count = 0
        try_max = 2
        try_max_limit = 5

        score_pattern = re.compile(r'合計点数[^\d]*(\d+)[点/]')
        msg_start = len(msg_hist)

        while try_count <= try_max:
            try_count += 1
            print( f"{try_count}回目 ポスト生成")
            base_article = ChatCompletion(msg_hist, temperature=0.7)
            base_article = trim_post( base_article )
            base_count = count_tweet(base_article)
            print(f"{try_count}回目 生成結果\n{base_article}")
            if base_count<20:
                print( f"Error: no tweet {base_article}")
                break
            #---------------------------
            # ツイートを評価する
            #---------------------------
            score = 0
            if base_count<=count_limit:
                evaluate_msgs = [
                    {"role": "assistant", "content": base_article },
                    {"role": "user", "content": evaluate_prompt }
                ]
                evaluate_response = bot.ChatCompletion(evaluate_msgs) # ChatCompletion(evaluate_msgs)
                if evaluate_response is None or len(evaluate_response)<20:
                    print( f"Error: result \n{evaluate_response}")
                    break
                #---------------------------
                # 点数と文字数判定
                #---------------------------
                point_result = score_pattern.search(evaluate_response)
                if point_result is not None:
                    score=int(point_result.group(1))
                    print(f"検出結果:{point_result.group(0)} -> {score}")
                    if score < 0 or 100 < score:
                        score = 0
            else:
                if post_lang == LANG_JP:
                    evaluate_response = f"文字数が{chars_limit}文字を超えてるにゃ。文字数を減らして欲しいにゃ。"
                else:
                    evaluate_response = f"The number of characters in the tweet is {base_count}. Tweet briefly. Tweet within {chars_limit} characters. Make it shorter."
                score = -1
                if try_max < try_max_limit:
                    try_max += 1

            print(f"[{try_count}回目 評価内容]\n{evaluate_response}\n評価点数 {score}点")

            # ハイスコアを更新する
            if base_count<=count_limit and ( tweet_count<20 or score>=tweet_score ):
                tweet_text = base_article
                tweet_count = base_count
                tweet_score = score

            if tweet_score>=90 or ( try_count>1 and tweet_score>=80 ) or ( try_count>=try_max and tweet_score>0 ):
                #---------------------------
                # ツイートする
                #---------------------------
                twtext = f"{tweet_text}\n\n{site_link}\n\n{tweet_tags}"
                print("----投稿--------")
                print( f"len:{tweet_count} score:{tweet_score}")
                print( f"post:{tweet_text}" )
                try:
                    if go_tweet is not None:
                        tweeter_client.create_tweet(text=twtext)
                        site_hist.put_site( site_link, site_text, embedding, "post" )
                    if post_lang == LANG_JP:
                        output_jp += 1
                    else:
                        output_en += 1
                    print("----完了--------\n")
                    break
                except tweepy.errors.BadRequest as ex:
                    #Your Tweet text is too long
                    #You are not allowed to create a Tweet with duplicate content.
                    print(ex)

            #---------------------------
            # ツイートを改善する
            #---------------------------
            print( f"ポスト修正")
            if try_count>=3:
                del msg_hist[msg_start:msg_start+2]
            msg_hist += [ {"role": "assistant", "content": base_article } ]
            gen_prompt = evaluate_response + "\n\n"
            if buzz_word is not None:
                gen_prompt = gen_prompt + buzz_prompt.format(buzz_word)
            gen_prompt = gen_prompt + update_prompt.format( post_ln, chars_limit)
            msg_hist += [ {"role": "user", "content": gen_prompt } ]

def count_tweet( text: str ) -> int:
    try:
        ret = parse_tweet(text)
        return ret.weightedLength
    except:
        return 0

def find_keyword( content:str, a:str, b:str ) -> int:
    if content is not None:
        if Utils.str_length(a)>=Utils.str_length(b):
            if content.find(a)>=0:
                return 0
            if content.find(b)>=0:
                return 1
        else:
            if content.find(b)>=0:
                return 1
            if content.find(a)>=0:
                return 0
    return -1

def trim_post( content: str ) -> str:
    content = Utils.str_unquote(content)
    content = re.sub( r'^にゃ[ー〜！ん]+','', content )
    content = re.sub( r'【[^】]*】',' ', content )
    content = re.sub( r'\([^)]*\)',' ', content )
    content = re.sub( r'\[[^\]]*\]',' ', content )
    content = re.sub( r'https*://','', content )
    content = re.sub( r' *[a-z0-9._-]*/[a-z0-9./_-]*[ ]*',' ', content )
    content = re.sub( r"[ ]*[→↓][ ]*"," ", content )
    p = content.find("#")
    if p>=0:
        content = content[:p]
    content = content.strip()
    return content

# <OpenAIObject text_completion id=cmpl-849BdGArSBdktULuIy0X7FARtVKUS at 0x7f80e153ecf0> JSON: {
#   "id": "cmpl-849BdGArSBdktULuIy0X7FARtVKUS",
#   "object": "text_completion",
#   "created": 1695999317,
#   "model": "gpt-3.5-turbo-instruct",
#   "choices": [
#     {
#       "text": "\n\n|\u65e5\u672c\u8a9e|\u82f1\u8a9e|\n|---|---|\n|Outrageous|\u3068\u3093\u3067\u3082\u306a\u3044|\n|\u30d5\u30ea\u30fc\u30ec\u30f3|\u30d5\u30ea\u30fc\u30ec\u30f3|\n|\u30af\u30f4\u30a1\u30fc\u30eb|\u30af\u30a9\u30fc\u30af|\n|\u30cf\u30a4\u30bf\u30fc|\u30cf\u30a4\u30bf\u30fc|\n|ichiban|\u4e00\u756a|",
#       "index": 0,
#       "logprobs": null,
#       "finish_reason": "stop"
#     }
#   ],
#   "usage": {
#     "prompt_tokens": 60,
#     "completion_tokens": 74,
#     "total_tokens": 134
#   }
prompt_tokens: int = 0
completion_tokens: int = 0
total_tokens:int  = 0
def token_usage( response ):
    global prompt_tokens, completion_tokens, total_tokens
    try:
        usage = response.usage
        p = usage.prompt_tokens
        c = usage.completion_tokens
        t = usage.total_tokens
        prompt_tokens += p
        completion_tokens += c
        total_tokens += t
        in_doll = int((prompt_tokens+999)/1000) * 0.0015
        out_doll = int((completion_tokens+999)/1000) * 0.002
        total_doll = in_doll + out_doll
        print( f"${total_doll} prompt:{p}/{prompt_tokens} ${in_doll} completion:{c}/{completion_tokens} ${out_doll} total:{t}/{total_tokens}")
        return True
    except Exception as ex:
        return False

def Completion( prompt, *, max_tokens=None, temperature=0 ):
    try:

        #print( f"openai.api_key={openai.api_key}")
        #print( f"OPENAI_API_KEY={os.getenv('OPENAI_API_KEY')}")
        if openai.api_key is None:
            openai.api_key=os.getenv('OPENAI_API_KEY')
        in_count = token_count( prompt )
        if max_tokens is None:
            max_tokens = 4096
        u = max_tokens - in_count - 50
        for retry in range(2,-1,-1):
            try:
                response = openai.Completion.create(
                        model="gpt-3.5-turbo-instruct",
                        temperature = temperature, max_tokens=u,
                        prompt=prompt,
                        request_timeout=(15,120)
                    )
                break
            except openai.error.Timeout as ex:
                if retry>0:
                    print( f"{ex}" )
                    time.sleep(5)
                else:
                    raise ex
            except openai.error.ServiceUnavailableError as ex:
                if retry>0:
                    print( f"{ex}" )
                    time.sleep(5)
                else:
                    raise ex

        token_usage( response )           
        if response is None or response.choices is None or len(response.choices)==0:
            print( f"Error:invalid response from openai\n{response}")
            return None
        content = response.choices[0].text.strip()
    except openai.error.AuthenticationError as ex:
        print( f"{ex}" )
        return None
    except openai.error.InvalidRequestError as ex:
        print( f"{ex}" )
        return None
    except openai.error.ServiceUnavailableError as ex:
        print( f"{ex}" )
        return None
    except Exception as ex:
        traceback.print_exc()
        return None

    return content

def ChatCompletion( mesg_list, temperature=0 ):
    try:

        #print( f"openai.api_key={openai.api_key}")
        #print( f"OPENAI_API_KEY={os.getenv('OPENAI_API_KEY')}")
        if openai.api_key is None:
            openai.api_key=os.getenv('OPENAI_API_KEY')
        for retry in range(2,-1,-1):
            try:
                response = openai.ChatCompletion.create(
                        model="gpt-3.5-turbo",
                        temperature = temperature,
                        messages=mesg_list,
                        request_timeout=(15,121)
                    )
                break
            except openai.error.ServiceUnavailableError as ex:
                if retry>0:
                    print( f"{ex}" )
                    time.sleep(5)
                else:
                    raise ex
        token_usage( response )
        if response is None or response.choices is None or len(response.choices)==0:
            print( f"Error:invalid response from openai\n{response}")
            return None

        content = response.choices[0]["message"]["content"].strip()
    except openai.error.AuthenticationError as ex:
        print( f"{ex}" )
        return None
    except openai.error.InvalidRequestError as ex:
        print( f"{ex}" )
        return None
    except openai.error.ServiceUnavailableError as ex:
        print( f"{ex}" )
        return None
    except Exception as ex:
        traceback.print_exc()
        return None

    return content

def to_embedding( input ):
    res = openai.Embedding.create(input=input, model="text-embedding-ada-002")
    return [data.get('embedding',None) for data in res.get('data',[])]

def token_count( input: str ) -> int:
    encoding: Encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")
    tokens = encoding.encode(input)
    count = len(tokens)
    return count

def fsplit_contents( text_all, split_size=2000, oerlap=200 ):
    tk_all = tk_encoder.encode(text_all)
    size_all =  len(tk_all)
    p = 0
    step = 2000
    overlap = 200
    results = []
    while p<size_all:
        info_list = tk_all[p:p+step]
        contents = tk_encoder.decode(info_list)
        results.append( (len(info_list),contents) )
        p = p + step - overlap
    return results

# DALL-Eによる画像生成
def generate_image(prompt):
    response = openai.Image.create(
        model="image-alpha-001",
        prompt=prompt,
        n=1,
        size="256x256",
        response_format="url"
    )

    image_url = response['data'][0]['url']
    # 画像を表示
    response = requests.get(image_url)
    img = Image.open(BytesIO(response.content))
    return img

def img_test():
    # 赤いリンゴの画像を生成
    image = generate_image("「にゃん！最新の猫ニュースを見つけたニャ！黒猫が墨汁に擬態してるニャんて！驚きの美しさににゃんとも言えないニャ！ぜひみんなに知らせたいニャ！😺📰🖤 #猫ニュース #ニャンモナイト」ニュース：猫は液体→では黒猫が液体化すると…？なんと墨汁になることが")
    image.show()

def test():
    s = "2023-0a8-10"
    ss = Utils.date_from_str(s)
    print(f"{s} --> {ss}")
    d0 = Utils.date_today()
    print(f" d0: {d0}")
    d1 = Utils.date_today(-1)
    print(f" d1: {d1}")
    d2 = Utils.date_today(-2)
    print(f" d2: {d2}")

    content = "  \"『 【 \"あいうおえおかき www.yahoo.co.jp/test/sample abcd.efg  】』   \""
    print( trim_post(content))

if __name__ == '__main__':

    #sys.exit(main(sys.argv))
    #xtest()
    neko_news()
    #img_test()
    #test()

