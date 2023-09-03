import sys,os,re
import traceback
import openai, tiktoken
from openai.embeddings_utils import cosine_similarity
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

if __name__ == "__main__":
    Utils.load_env( ".miyasaburo.conf" )

def to_embedding( input ):
    res = openai.Embedding.create(input=input, model="text-embedding-ada-002")
    return [data.get('embedding',None) for data in res.get('data',[])]

tk_encoder = tiktoken.encoding_for_model("gpt-3.5-turbo")

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

def neko_neko_network():
    #baselist=["猫が迷子","猫が行方不明","猫が家出","猫が帰ってきました","猫を探して"]
    #base_emg_list  = to_embedding(baselist)
    
    module : WebSearchModule = WebSearchModule()
    dates = [ Utils.date_today(), Utils.date_today(-1), Utils.date_today(-2)]

    query = f"( 猫 OR ねこ OR ネコ) ( 迷子 OR 脱走 OR 行方不明 )"
    query = f"( 猫 OR ねこ OR ネコ) ( 迷子 OR 脱走 OR 行方不明 ) ( {' OR '.join(dates)} )"

    n_return = 10
    search_results = module.search_meta( query, num_result = n_return )
    print( f"result:{len(search_results)}")


    prompt = "上記の文章から迷い猫の情報を以下の表にまとめて下さい。"
    table = "|日付|場所|猫の名前|猫の特徴|状況、行方不明,見つかりました,里親募集,里親決定|その他|\n|----|----|----|----|----|\n|2023-08-03|東京都多摩川区|みーちゃん|真っ白な毛並み|行方不明|ふらっと出掛けたきり帰って来ません|\n|2023-08-03|大阪府西成区|こてつ|虎縞|見つかりました|難波で飲みつぶれているところを保護しました|\n"
    prompt = "上記の文章から迷い猫の情報を下記の例に従って抽出して下さい。"
    filters = {
        "日付": "2023/08/04 又は 不明",
        "状況":"行方不明、見つかりました、里親募集、里親決定、など",
        "場所":"市町村など",
        "名前":"猫の名前 又は 未定",
        "品種":"雑種 ベンガル等",
        "毛色":"三毛、白、黒、とら縞など",
        "性別":"オス 又は メス",
        "年齢":"推定１歳８ヶ月",
        "その他特徴":"呼びかけると「おっす」と返事します。セミを取りに行くと出ていったきり帰ってきません",
        "掲載サイト":"情報へのリンクがあれば記載" 
    }
    table ="例)"
    for k,v in filters.items():
        table = f"{table}\n{k}: {v}"

    info_list = []

    for d in search_results:
        site_title = d.get('title',"")
        site_link = d.get('link',"")
        if len(site_title)==0 or len(site_link)==0:
            continue
        print("----")
        print( f"{site_title} {site_link}")
        site_text = module.get_content( site_link )
        if site_text is None:
            continue
        print( f"--- split" )
        split_contents = fsplit_contents( site_text )
        idx = 0
        for tokens, context in split_contents:
            idx += 1
            print(f"--- completion:{idx}/{len(split_contents)}")
            try:
                completion = openai.ChatCompletion.create( model = "gpt-3.5-turbo",  
                        messages = [
                            { "role":"user", "content": prompt + "\n\n\n" + context+ "\n\n\n" + prompt + "\n\n" + table },
                            # { "role":"system", "content": f"{prompt}\n{table}" },
                        ],
                        max_tokens  = 3400-tokens, n = 1, stop = None, temperature = 0.0, 
                )
            except Exception as ex:
                print(ex)
                continue
            
            # 応答
            response = completion.choices[0].message.content
            # 集計
            print(f"--- parse:{idx}/{len(split_contents)}")
            info = {}
            for line in response.split("\n"):
                kv = line.split(':',1)
                key: str = None
                value: str = ''
                if len(kv)==2:
                    key = kv[0].strip()
                    value = kv[1].strip()
                    if key=="日付":
                        value = Utils.date_from_str(value)
                    elif not value or "不明"==value or "未定"==value:
                        value = ''
                if key and key in filters:
                    if value and len(value)>0:
                        print( f"hit    {line}")
                        info[key] = value
                    else:
                        print( f"skip   {line}")
                else:
                        print( f"ignore {line}")
                        if len(info)>0 and "日付" in info:
                            info['title'] = site_title
                            info['link'] = site_link
                            info_list.append(info)
                            info = {}
            if len(info)>0:
                info_list.append(info)
                info = {}
    for info in info_list:
        if info.get('日付',"") in dates:
            print("\n\n")
            print(info)

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

    dates =  Utils.date_today()
    LANG_JP='Japanese'
    query_jp = f"猫の話題 -site:www.youtube.com after: {dates}"
    query_en = f"Funny Cat News stories -site:www.youtube.com after: {dates}"
    n_return = 10
    print( f"検索中: {query_jp}")
    search_results_jp = module.search_meta( query_jp, num_result = n_return )
    print( f"検索中: {query_en}")
    search_results_en = module.search_meta( query_en, num_result = n_return )
    # print( f"result:{len(search_results)}")
    search_results = [x for pair in zip(search_results_jp, search_results_en) for x in pair]
    search_results.extend(search_results_jp[len(search_results_en):])  # AがBより長い場合の残りの要素
    search_results.extend(search_results_en[len(search_results_jp):])  # BがAより長い場合の残りの要素

    detect_fmt = "下記の記事内容について\n\n記事タイトル:{}\n記事内容:\n{}\n\n"
    detect_fmt = f"{detect_fmt}下記の項目に答えて下さい。\n"
    detect_fmt = f"{detect_fmt}1)この記事に含まれる国名・地名をリストアップして下さい\n"
    detect_fmt = f"{detect_fmt}2)地名は日本国内のものですか？\n"
    detect_fmt = f"{detect_fmt}3)この記事に日本語の「海外」という単語は含まれていますか？\n"
    detect_fmt = f"{detect_fmt}4)この記事に含まれる人物名、ねこの名前をリストアップして下さい\n"
    detect_fmt = f"{detect_fmt}5)人物名、名前は日本人っぽいですか？\n"
    detect_fmt = f"{detect_fmt}6)この記事に含まれる物語、書籍、小説、ドラマ、映画・演劇、公演、アニメーションをリストアップして下さい\n"
    detect_fmt = f"{detect_fmt}7)この記事に含まれるイベント、催し、公演等があればタイトルと日時をリストアップして下さい\n"
    detect_fmt = f"{detect_fmt}8)この記事から政治的、宗教的、反社会的な思想や思想誘導が含まれていればリストアップして下さい\n"
    detect_fmt = f"{detect_fmt}9)この記事から得られる教訓や示唆があればリストアップして下さい\n"
    detect_fmt = f"{detect_fmt}10)この記事の出来事についてニュースとなった特徴をリストアップして下さい\n"
    detect_fmt = f"{detect_fmt}\n\n上記の情報より下記の質問に回答して下さい\n"
    detect_fmt = f"{detect_fmt}11)この記事は日本国内の出来事ですか？海外での出来事ですか？(InsideJapan or OutsideJapanで回答すること)\n"
    detect_fmt = f"{detect_fmt}12)猫に関する記事ですか？(Cat or NotCatで回答すること)\n"
    detect_fmt = f"{detect_fmt}13)動物や生体の販売、広告ですか？(Sale or NotSaleで回答すること)\n"
    detect_fmt = f"{detect_fmt}14)政治的、宗教的、反社会的が含まれていますか？(Asocial or NotAsocialで回答すること)\n"

    article_fmt = "下記の記事をフォロワーに紹介するツイートを生成して下さい。\n記事タイトル:{}\n記事内容:\n{}"
    prompt_fmt = "\n".join( [
        "上記の記事から、制約条件とターゲットと留意点に沿って、バズるツイート内容を記述して下さいにゃ。",
        "",
        "制約条件：",
        "・投稿を見た人が興味を持つ内容",
        "・投稿を見た人から信頼を得られる内容",
        "・カジュアルな口調で",
        "・猫がニュースを見た感想を述べる",
        # "・最後にCall to Action(いいねなど)を短く入れる",
        "",
        "ターゲット：",
        "・猫のニュースで癒やされたい人", # （タツイッーで発信ターゲットにしている属性）
        "・猫ニュースを面白く伝える", # （今回のツイートで発信している対象の属性）
        "・猫の知られざる世界を見てみたい人", #（上記の対象が課題に感じる場面の具体）
        "",
        "出力言語:{}",
        "文字数制限:{}",
        "",
        "出力文:"
    ] )

    evaluate_prompt = "\n".join([
        "次に、以下の5つの指標を20点満点で評価してくださいにゃ。",
        "①話題性：ツイートのトピックが、現在の流行やニュースなど、人々が興味を持つ話題に関連しているかにゃ？",
        "②エンゲージメント促進：ツイートが、ユーザーに反応を促すような要素を含んでいるかにゃ？",
        "③付加価値：猫の視点、猫の感想が含まれているかにゃ？",
        "④リアリティ:具体的な例や体験が入り信ぴょう性高く独自性があるかにゃ？",
        "⑤文章の見やすさ:行変えと箇条書きを使い全ての文が20字以内でまとまっているかにゃ？",
        "",
        "各指標の評価点数を入力したら、プログラムは自動的に合計点を計算し、それを100点満点で表示するにゃ。",
        "合計点数：",
        "",
        "そして、もっとバズるための改善点を考えてるにゃ",
        "改善点：",
    ])

    update_prompt = "上記の改善点を踏まえて、猫っぽい出力ツイートを{}で{}文字以内で生成するにゃ\n\n出力文:"


    exclude_site = {
        "www.youtube.com": 1,
        "cat.blogmura.com": 1,
        "www.thoroughbreddailynews.com": 1
    }

    must_keywords = [
        "猫", "ねこ", "ネコ",
        "cat", "Cat",
    ]
    exclude_keywords = [
        "記事が見つかりません","公開期間が終了",
        "販売", "価格", "値段",
        "譲渡会",
        "ディズニー", "disney", "Disney",
        ]

    hashtag_list_jp = [ "#猫", "#cats", "#猫好きさんと繋がりたい","#animals", "#funnyanimals"]
    hashtag_list_en = [ "#cat", "#CatsAreFamily", "#pets", "#animals", "#funnyanimals"]

    site_hist = {}

    tw_count_max = 1
    count_jp = 0
    count_en = 0
    for d in search_results:
        site_title = d.get('title',"")
        site_link = d.get('link',"")
        site_top = urlparse(site_link).netloc

        #---------------------------
        # 除外判定
        #---------------------------
        if exclude_site.get( site_top, None ) is not None:
            print( f"Exclude {site_link}")
            continue

        if site_hist.get( site_top, None ) is not None:
            print( f"Skip {site_link}")
            continue

        site_text: str = module.get_content( site_link, type="title" )
        if site_text is None or site_text == '':
            print( f"Error: no article\n{site_title}\n{site_link}\n")
            continue

        a=[ keyword for keyword in must_keywords if site_text.find(keyword)>=0]
        if len(a)==0:
            print( f"Error: not found 猫\n{site_title}\n{site_link}\n")
            print(site_text)
            continue

        a=[ keyword for keyword in exclude_keywords if site_text.find(keyword)>=0]
        if len(a)>0:
            print( f"Skip: found {a}\n{site_title}\n{site_link}\n")
            continue
        #---------------------------
        # 記事の内容判定
        #---------------------------
        print("-------------------------------------------------------")
        print( f"記事判定:{site_title}")
        print( f"{site_link}")
        if count_jp>=tw_count_max and not Utils.contains_kana(site_text):
            print( f"Skip by lang en {site_title} {site_link}\n" )
            continue
        
        detect_hist = []
        detect_hist += [ {"role": "user", "content": detect_fmt.format( site_title, site_text[:2000] ) } ]
        detect_result: str = ChatCompletion(detect_hist)
        if detect_result is None or len(detect_result)<20:
            print( f"Error: no result for detect {site_title} {site_link}\n{detect_result}")
            continue
        detect_result = detect_result.replace('\n\n','\n')
        print("-------------------------------------------------------")
        print(detect_result)
        print("-------------------------------------------------------")

        if find_keyword( detect_result, "Cat", "NotCat" )!=0:
            print( f"Error: 猫記事じゃない {site_title} {site_link}\n" )
            continue
        if find_keyword(detect_result, "Sale", "NotSale")!=0:
            print( f"Error: 不適切な記事 {site_title} {site_link}\n" )
            continue
        if find_keyword(detect_result, "Asocial", "NotAsocial")!=0:
            print( f"Error: 不適切な記事 {site_title} {site_link}\n" )
            continue

        #---------------------------
        # ポスト言語判定
        #---------------------------
        post_lang = find_keyword(detect_result, "InsideJapan", "OutsideJapan")
        if post_lang==0 and Utils.contains_kana(site_text):
            if count_en>=tw_count_max:
                print( f"Skip by lang en {site_title} {site_link}\n" )
                continue
            # 日本のニュースは英語でポスト
            post_lang='English'
            post_limit = 229
        elif post_lang==1:
            if count_jp>=tw_count_max:
                print( f"Skip by lang jp {site_title} {site_link}\n" )
                continue
            # 日本のニュースでないなら日本語でポスト
            post_lang=LANG_JP
            post_limit = 129
        #---------------------------
        # 初期生成
        #---------------------------
        print("-------------------------------------------------------")
        print( f"生成:{site_title}")
        print( f"{site_link}")
        msg_hist = []
        msg_hist += [ {"role": "user", "content": article_fmt.format( site_title, site_text[:2000] ) } ]
        msg_hist += [ {"role": "system", "content": prompt_fmt.format( post_lang, post_limit) } ]
        base_article = ChatCompletion(msg_hist, temperature=0.7)
        base_article = trim_post( base_article )
        if base_article is None or len(base_article)<20:
            print( f"Error: no tweet {base_article}")
            continue

        tweet_text = None
        tweet_score = 0
        nn = 0
        nn_max = 3
        nn_limit = 5
        print(f"{nn}回目ツイート内容:{site_link}\n{base_article}")

        msg_start = len(msg_hist)
        while nn <= nn_max and nn <= nn_limit:
            nn += 1
            base_article0 = base_article
            #---------------------------
            # ツイートを評価する
            #---------------------------
            if len(base_article0)<=post_limit:
                evaluate_msgs = [
                    {"role": "assistant", "content": base_article0 },
                    {"role": "system", "content": evaluate_prompt }
                ]
                evaluate_response = ChatCompletion(evaluate_msgs)
                if evaluate_response is None or len(evaluate_response)<20:
                    print( f"Error: result {site_title} {site_link}\n{evaluate_response}")
                    break
            else:
                if post_lang == LANG_JP:
                    evaluate_response = f"文字数が{post_limit}文字を超えてるにゃ。文字数を減らして欲しいにゃ。"
                else:
                    evaluate_response = f"The number of characters in the tweet is {len(base_article0)}. Tweet briefly. Tweet within {post_limit} characters. Make it shorter."
                nn_max += 1

            print(f"[{nn}回目評価内容]\n{evaluate_response}")

            #---------------------------
            # 点数と文字数判定
            #---------------------------
            score = 0
            pattern = re.compile(r'合計点数[^\d]*(\d+)[点/]')
            point_result = pattern.search(evaluate_response)
            if point_result is not None:
                score=int(point_result.group(1))
                print(f"検出結果:{point_result.group(0)} -> {score}")
                if score < 0 or 100 < score:
                    score = 0

            if len(base_article0)<=post_limit:
                if score>=tweet_score:
                    tweet_text = base_article0
                    tweet_score = score
                    if score>=90 or ( nn>1 and score>=80):
                        break

            #---------------------------
            # ツイートを改善する
            #---------------------------
            if nn>=3:
                del msg_hist[msg_start:msg_start+3]
            msg_hist += [ {"role": "assistant", "content": base_article0 } ]
            msg_hist += [ {"role": "system", "content": evaluate_response } ]
            msg_hist += [ {"role": "user", "content": update_prompt.format( post_lang, post_limit) } ]

            base_article = ChatCompletion(msg_hist, temperature=0.7)
            base_article = trim_post( base_article )
            print(f"[{nn}回目ツイート内容]\n{base_article}")

        if Utils.str_length( tweet_text ) < 20:
            print( f"Error: no tweet" )
            continue
        if tweet_text is None or len(tweet_text)>post_limit:
            print( f"Error: tweet too long" )
            continue

        if post_lang == LANG_JP:
            tweet_tags = " ".join(hashtag_list_jp)
        else:
            tweet_tags = " ".join(hashtag_list_en)

        tx = f"{tweet_text}\n\n{site_link}\n\n{tweet_tags}"
        print("----------------------------------------------")
        print( f"{tweet_text}" )
        print( f"{site_link}")
        print( f"{tweet_tags}" )
        print("----------------------------------------------")

        # 投稿
        try:
            tweeter_client.create_tweet(text=tx)
            site_hist[site_top] = 1
            if post_lang == LANG_JP:
                count_jp += 1
            else:
                count_en += 1
            if count_jp>=tw_count_max and count_en>=tw_count_max:
                break
        except tweepy.errors.BadRequest as ex:
            print(ex)

def find_keyword( content:str, a:str, b:str ) -> int:
    if content is not None:
        if content.find(a)>=0:
            return 0
        if content.find(b)>=0:
            return 1
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

def ChatCompletion( mesg_list, temperature=0 ):
    try:

        #print( f"openai.api_key={openai.api_key}")
        #print( f"OPENAI_API_KEY={os.getenv('OPENAI_API_KEY')}")
        if openai.api_key is None:
            openai.api_key=os.getenv('OPENAI_API_KEY')
        response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                temperature = temperature,
                messages=mesg_list
            )

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
    except Exception as ex:
        traceback.print_exc()
        return None

    return content

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

