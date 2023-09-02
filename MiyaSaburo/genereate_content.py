import sys,os,re
import openai, tiktoken
from openai.embeddings_utils import cosine_similarity
import requests
from pathlib import Path
from dotenv import load_dotenv
from urllib.parse import urlparse
import tweepy
from PIL import Image
from io import BytesIO
from tools.webSearchTool import WebSearchModule
from libs.utils import Utils

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
    query = f"猫の話題 after: {dates}"
    query = f"Funny Cat News stories -site:www.youtube.com after: {dates}"

    n_return = 10
    search_results = module.search_meta( query, num_result = n_return )
    # print( f"result:{len(search_results)}")

    examples = [ 
        ("トカゲ見つけて下さい","なんかの広告\nトカゲが昨日逃げました\nなんかの広告","トカゲが逃げました"),
        ("トカゲ見つけて下さい","なんかの広告\nなんかの広告\nなんかの広告","記事無し"),
        ]
    prompt_fmt = "下記の記事をフォロワーに紹介するツイートを256文字以内で生成して下さい。\n有効な記事がない場合、記事無しと回答すること。"
    prompt_fmt = "下記の記事をフォロワーに紹介するツイートを256文字以内で生成して下さい。\n有効な記事がない場合、記事無しと回答すること。"
    article_fmt = "下記の記事をフォロワーに紹介するツイートを256文字以内で生成して下さい。\n記事タイトル:{}\n記事内容:\n{}"
    prompt_fmt = "\n".join( [
        "上記の記事から、制約条件とターゲットと留意点に沿って、バズるツイート内容を140文字程度で記述して下さいにゃ。",
        "",
        "制約条件：",
        "・投稿を見た人が興味を持つ内容",
        "・投稿を見た人から信頼を得られる内容",
        "・カジュアルな口調で",
        "・野良猫がニュースを見た感想を述べる",
        # "・最後にCall to Action(いいねなど)を短く入れる",
        "",
        "ターゲット：",
        "・猫のニュースで癒やされたい人", # （タツイッーで発信ターゲットにしている属性）
        "・猫ニュースを面白く伝える", # （今回のツイートで発信している対象の属性）
        "・猫の知られざる世界を見てみたい人", #（上記の対象が課題に感じる場面の具体）
        "",
        "出力文:"
    ] )

    evaluate_prompt = "\n".join([
        "次に、以下の5つの指標を20点満点で評価してくださいにゃ。",
        "①話題性：ツイートのトピックが、現在の流行やニュースなど、人々が興味を持つ話題に関連しているかにゃ？",
        "②エンゲージメント促進：ツイートが、ユーザーに反応を促すような要素を含んでいるかにゃ？",
        "③付加価値：野良猫ならではの視点・感想が含まれているかにゃ？",
        "④リアリティ:具体的な例や体験が入り信ぴょう性高く独自性があるかにゃ？",
        "⑤文章の見やすさ:行変えと箇条書きを使い全ての文が20字以内でまとまっているかにゃ？",
        "",
        "各指標の評価点数を入力したら、プログラムは自動的に合計点を計算し、それを100点満点で表示するにゃ。",
        "合計点数：",
        "",
        "そして、もっとバズるための改善点を考えてるにゃ",
        "改善点：",
    ])

    update_prompt = "上記の改善点を踏まえて、野良猫っぽい出力ツイートを120文字以内で生成するにゃ\n出力文:"


    duble_check = {
        "www.youtube.com": 1,
        "cat.blogmura.com": 1,
        "www.thoroughbreddailynews.com": 1
    }
    tw_count = 0
    for d in search_results:
        site_title = d.get('title',"")
        site_link = d.get('link',"")
        site_top = urlparse(site_link).netloc

        if duble_check.get( site_top, None ) is not None:
            print( f"Skip {site_link}")
            continue

        if "https://cat.blogmura.com/cat_picture/" == site_link:
            continue
        if len(site_title)==0 or len(site_link)==0:
            print( f"Error: no title {site_title} {site_link}")
            continue
        if "youtube.com" in site_link:
            print( f"Error: skip youtube {site_title} {site_link}")
            continue
        if "karapaia.com" in site_link:
            print( f"Skip {site_link}")
            continue

        site_text: str = module.get_content( site_link, type="title" )
        if site_text is None or site_text == '':
            print( f"Error: no article {site_title} {site_link}")
            continue

        if site_text.find("記事が見つかりません")>=0 or site_text.find("公開期間が終了")>=0:
            print( f"Error: no article {site_title} {site_link}")
            print(site_text)
            continue

        if site_text.find("猫")<0 and site_text.find("ねこ")<0 and site_text.find("ネコ")<0 and site_text.find("cats")<0 and site_text.find("Cat")<0:
            print( f"Error: not found 猫 ")
            print(site_text)
            continue

        if site_text.find("販売")>=0 or site_text.find("価格")>=0 or site_text.find("値段")>=0:
            print( f"Error: found 販売")
            print(site_text)
            continue

        if site_text.find("ノミ")>=0:
            print( f"Error: found ノミ")
            continue

        #---------------------------
        # 初期生成
        #---------------------------
        msg_hist = []
        # for title_data,in_data, out_data in examples:
        #     msg_hist += [ {"role": "system", "content": prompt_fmt.format(title_data) } ]
        #     msg_hist += [ {"role": "user", "content": in_data } ]
        #     msg_hist += [ {"role": "assistant", "content": out_data } ]

        msg_hist += [ {"role": "user", "content": article_fmt.format( site_title, site_text[:2000] ) } ]
        msg_hist += [ {"role": "system", "content": prompt_fmt } ]

        base_article = ChatCompletion(msg_hist)
        base_article = trim_post( base_article );
        if base_article is None or len(base_article)<20:
            print( f"Error: no tweet {site_title} {site_link}\n{base_article}")
            continue

        nn = 1
        print(f"{nn}回目ツイート内容\n{base_article}")

        for nn in range(1,2):
            base_article0 = base_article
            #---------------------------
            # ツイートを評価する
            #---------------------------
            evaluate_msgs = [
                {"role": "assistant", "content": base_article0 },
                {"role": "system", "content": evaluate_prompt }
            ]
            evaluate_response = ChatCompletion(evaluate_msgs)
            if evaluate_response is None or len(evaluate_response)<20:
                print( f"Error: no tweet {site_title} {site_link}\n{evaluate_response}")
                continue

            if len(base_article0)>129:
                evaluate_response = evaluate_response+"\n文字数が129文字を超えてるにゃ。"

            print(f"[{nn}回目評価内容]\n{evaluate_response}")

            #---------------------------
            # ツイートを改善する
            #---------------------------
            msg_hist += [ {"role": "assistant", "content": base_article0 } ]
            msg_hist += [ {"role": "system", "content": evaluate_response } ]
            msg_hist += [ {"role": "system", "content": update_prompt } ]

            base_article = ChatCompletion(msg_hist)
            base_article = trim_post( base_article );
            print(f"[{nn}回目ツイート内容]\n{base_article}")

        tweet_text = base_article
        p = tweet_text.find("#")
        hashtag_list = [ "#猫", "#cats", "#猫好きさんと繋がりたい","#animals", "#funnyanimals"]
        if p>1:
            tweet_text = tweet_text[:p].strip()
        tweet_tags = " ".join(hashtag_list)

        tx = f"{tweet_text}\n\n{site_link}\n\n{tweet_tags}"
        chars = len(tx);
        print("----------------------------------------------")
        print( f"{tweet_text}" )
        print( f"{site_link}")
        print( f"{tweet_tags}" )
        print("----------------------------------------------")

        if len(tweet_text) > 129:
            print( f"Error: too long" )
            continue


        if tweet_text.find("猫")<0 and tweet_text.find("ねこ")<0 and tweet_text.find("ネコ")<0:
            print( f"Error: not found 猫 ")
            print(tweet_text)
            continue

        if tweet_text.find("販売")>=0 or tweet_text.find("価格")>=0 or tweet_text.find("値段")>=0:
            print( f"Error: found 販売")
            print(tweet_text)
            continue

        if tweet_text.find("ノミ")>=0:
            print( f"Error: found ノミ")
            continue

        # 投稿
       # tweeter_client.create_tweet(text=tx)
        duble_check[site_top] = 1
        tw_count += 1
        if tw_count>=2:
            break

def trim_post( content: str ) -> str:
    if content.startswith("「") and content.endswith("」"):
        content = content[1:-1]
    if content.startswith("「" ) and content.endswith("」"):
        content = content[1:-1]       
    content = content.replace("[URL]","")
    content = content.replace("→","")
    content = content.strip()
    return content

def ChatCompletion( mesg_list ):
    response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=mesg_list
        )

    if response is None or response.choices is None or len(response.choices)==0:
        print( f"Error:invalid response from openai\n{response}")
        return None

    content = response.choices[0]["message"]["content"].strip()

    if content is None or len(content)<20:
        print( f"Error: no tweet \n{content}")
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

if __name__ == '__main__':
    homedir=Path.home()
    if homedir is not None and len(str(homedir))>0:
        envfile=f"{homedir}/.miyasaburo.conf"
        if os.path.exists(envfile):
            load_dotenv( envfile )
    #sys.exit(main(sys.argv))
    #xtest()
    neko_news()
    #img_test()
    #test()

