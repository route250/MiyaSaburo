import openai, tiktoken
from openai.embeddings_utils import cosine_similarity
import requests
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

def neko_news():
    
    module : WebSearchModule = WebSearchModule()
    dates = [ Utils.date_today(), Utils.date_today(-1), Utils.date_today(-2)]

    dates = "2023/8/12"
    query = f"猫の話題 after: {dates}"


    n_return = 10
    search_results = module.search_meta( query, num_result = n_return )
    # print( f"result:{len(search_results)}")

    for d in search_results:
        site_title = d.get('title',"")
        site_link = d.get('link',"")
        if len(site_title)==0 or len(site_link)==0:
            continue
        if "youtube.com" in site_link:
            continue

        site_text = module.get_content( site_link, type="title" )
        if site_text is None:
            continue

        prompt1 = "URL:{site_link}\nTITLE:{site_title}"
        prompt1 = f"{prompt1}\n\n記事内容\n{site_text[:2000]}"
        prompt1 = f"{prompt1}\n\上記のネット記事から、タイトル「{site_title}」に関係ない部分を削除して下さい。\n"

        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "user", "content": prompt1 },
            ],
        )

        base_article = response.choices[0]["message"]["content"].strip()
        # print( f"{base_article}" )

        prompt1 = "URL:{site_link}\nTITLE:{site_title}"
        prompt1 = f"{prompt1}\n\n記事内容\n{base_article[:2000]}"
        prompt1 = f"{prompt1}\n\野良猫がこのニュースを読んだときの反応は？"
        prompt1 = f"{prompt1}\n【チャットボットの現在の感情パラメーター】"
        prompt1 = f"{prompt1}\n喜び:0〜5\n怒り:0〜5\n悲しみ:0〜5\n楽しさ:0〜5\n自信:0〜5\n困惑:0〜5\n恐怖:0〜5"

        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "user", "content": prompt1 },
            ],
        )

        param = response.choices[0]["message"]["content"].strip()
        prompt2 = "野良猫がこの記事の紹介をツイートするセリフを生成して下さい\n"

        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "user", "content": prompt1 },
                {"role": "assistant", "content": param },
                {"role": "user", "content": prompt2 },
            ],
        )
        article_text = response.choices[0]["message"]["content"].strip()

        print("----------------------------------------------")
        print( f"{article_text}" )
        print( f"ニュース：{site_title} {site_link}")
        print("----------------------------------------------")

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
    #sys.exit(main(sys.argv))
    #xtest()
    neko_news()
    #img_test()
    #test()
