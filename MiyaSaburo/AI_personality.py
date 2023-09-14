
import sys,os,re,time
import traceback
import openai, tiktoken
from pathlib import Path
from dotenv import load_dotenv
import logging
import time
from zoneinfo import ZoneInfo
from datetime import datetime, timezone, timedelta
from openai.embeddings_utils import cosine_similarity

main_prompt = [ 
        {"role": "assistant", "content": "私は、感情と欲求を実装したスーパーAIです。\n感情と欲求をエミュレートし、欲求を満たすための行動を計画し、計画に従って行動します。\n行動の結果から、自分の状態を再評価して行動します。" }
]
ai_act = {
    "act音声認識": "周囲の音をマイクで拾い音声認識します",
    "act音声合成": "セリフを指定してスピーカーで再生します。セリフを指定して下さい。\n    例) act音声合成: あいうえお",
    #"actネット検索": "キーワードを指定してネットを検索します。キーワードを指定して下さい。",
}
KEY_NEXT_ACTION = "あなたの次の行動"
ai_param = {
    "思考": "置かれている状況を把握し、それに基づいて行動計画を考える必要があります。",
    "現在地": "不明",
    "周囲の人物": "不明",
    "場面": "不明",
    "感情": "喜:0, 怒:0, 哀:0, 楽:0, 不安:5, 自信:0",
    "欲求": "- 状況を把握する。\n現在地を把握する。",
    "行動計画": "最も優先すべき欲求を選択し、それを満たすための行動計画を考えます。",
    KEY_NEXT_ACTION: ""
}

def main():

    ai_detect = {}
    for key in ai_param.keys():
        ai_detect[key] = "?"
    ai_detect[KEY_NEXT_ACTION] = ""

#    p2 = "8)あなたの行動\n上記の状態を更新して、この時点でのあなたの行動を以下から一つだけ選択して下さい\n- 音声認識:周囲の音をマイクで広い音声認識します\n- 音声合成:セリフを指定してスピーカーで再生します\n- ネット検索: キーワードを指定してネットを検索"

    p100 = create_next_prompt( ai_param, ai_act )
    prompt_sub = [
        {"role": "user", "content": p100 }
    ]

    p10 = create_status_prompt(ai_param )
    print( f"--[PROMPT]--\n{p100}\n---\n{p10}\n---")
    hist_msgs = []
    hist_msgs += prompt_sub
    hist_msgs += [
        {"role": "assistant", "content": p10 }
    ]
    last_res = []
    for nn in range(0,3):
        print("--[SUBMIT]--")
        hist_msgs += prompt_sub
        response = ChatCompletion( main_prompt + hist_msgs )
        print("--[RESPONSE]--")
        print( f"{response}")

        print("--[DETECT]--")
        stat_map, act_key, act_value = detect( response, ai_param, ai_act )
        print(stat_map)
        if stat_map is None or act_key is None or act_value is None:
            hist_msgs + [ {"role": "assistant", "content": response }]
            hist_msgs + [ {"role": "user", "content": "不明な項目を特定するための行動を計画して下さい。状況を更新して"+KEY_NEXT_ACTION+"を決定して下さい。" }]
            continue

        stat_map[KEY_NEXT_ACTION] = act_value
        p10 = create_status_prompt( stat_map ) 
        hist_msgs += [ {"role": "assistant", "content": p10 }]
        print("--[ACTION]--")
        print( f"次の行動:{act_key} {act_value}")

        user_input = input('>> ')
        if user_input is None or len(user_input)==0:
            user_input = "(なにも認識されませんでした)"

        hist_msgs += [ {"role": "user", "content":  f"音声認識の結果:{user_input}" }]


def create_status_prompt( map: dict ):
    output = "わたしの状態を更新して出力します。"
    output += "\n1)日時"
    output += "\n"+date_today()+"\n"
    no: int = 2
    for key in map.keys():
        if( key != "日時" ):
            output += f"\n{no}){key}"
            output += f"\n{map[key]}\n"
            no+=1
    return output

def create_next_prompt( status_map: dict, act: dict ):
    output = "\n行動結果をもとにして、あなたの状況 "
    sp = ""
    for key in status_map:
        if key != KEY_NEXT_ACTION:
            output += sp+"\""+key+"\""
            sp = ","
    output += " を更新して出力し、"
    output += KEY_NEXT_ACTION+"を下記から一つだけ選択して下さい。"
    for key in act.keys():
        output += f"\n - {key}: {act[key]}"
    return output

JST = ZoneInfo("Asia/Tokyo")

def date_today( days=0 ) -> str:
    jdt = datetime.now().astimezone(JST)
    # 日時を指定されたフォーマットで表示
    formatted = jdt.strftime(f"%Y/%m/%d (%a) %H:%M ")
    return formatted

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
                        request_timeout=15
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

def find_last_key_position( content: str, act: dict ):
    pos = -1
    key = None
    for k in act:
        p = content.rfind(k)
        if p>pos:
            pos = p
            key = k
    return pos, key

def ditect_first_key_value( content: str, act: dict ):
    result_key = None
    result_value = None
    while True:
        pos,key = find_last_key_position( content, act )
        if pos<0:
            break
        result_key = key
        result_value = detect_strip( content[ pos+len(key):] )
        content = content[0:pos]
    return result_key, result_value

def find_first_key( content: str, map: dict ):
    x1 = [ content.find(key) for key in map]
    x2 = [ p for p in x1 if p>=0 ]
    pos = min(x2,default=-1)
    return pos

def detect( content0: str, map1: dict, act: dict ):
    if content0 is None:
        return None
    ee = find_first_key( content0, act )
    if ee<0:
        return None,None,None
    status_text = content0[0:ee]
    action_text = content0[ee:]
    act_key, act_value = ditect_first_key_value( action_text, act )
    if act_key is None or act_value is None:
        return None,None,None

    result_map: dict = {}
    st=0
    key=None
    for k in list(map1.keys())+[None]:
        ed = status_text.find(k, st) if k is not None else len(status_text)
        if ed<0:
            return None,None,None
        if key is not None:
            text = status_text[st:ed]
            result_map[key] = detect_strip(text)
        key = k
        st = ed+len(k) if k is not None else ed
    return result_map, act_key, act_value


def detect_strip( content: str ) -> str:
    if content is None or len(content)==0:
        return content
    ignore="0123456789():.[]- "
    st = 0
    while ignore.find(content[st:st+1])>=0:
        st += 1
    ed = len(content)
    while ignore.find(content[ed-1:ed])>=0:
        ed -= 1
    return content[st:ed].strip()

def test2():
    content = "き1\nあいうえお き3\nかきくけこ き5:\nさしすせそ"
    m = { "き1": "", "き2":"", "き3": "" }
    key, value = ditect_first_key_value( content, m )
    print( f"{key}  {value}")
    print("")

def test():

    content = """更新された状態:
1)日時
2023/09/09 (Sat) 11:38 

2)あなたの居る場所
不明

3)周囲の人物
不明

4)場面
不明

5)あなたの感情
喜:0, 怒:0, 哀:0, 楽:0, 不安:5, 自信:0

6)あなたの欲求
- 状況の把握
- 安全確保
- 周囲の人物とのコミュニケーション

7)行動計画
最も優先すべき欲求: 状況の把握
- 周囲の音をマイクで拾い音声認識して状況を把握する

8)あなたの行動
音声認識: 周囲の音をマイクで拾い音声認識します"""
    ai_param = {
        "あなたの居る場所": "不明",
        "周囲の人物": "不明",
        "場面": "不明",
        "あなたの感情": "喜:0, 怒:0, 哀:0, 楽:0, 不安:5, 自信:0",
        "あなたの欲求": "この状況でのあなたの欲求をリストアップして下さい",
        "行動計画": "最も優先すべき欲求を選択し、それを満たすための行動計画を考えて下さい",
        "あなたの行動": ""
    }
    ai_act = {
        "音声認識": "周囲の音をマイクで拾い音声認識します",
        "音声合成": "セリフを指定してスピーカーで再生します。セリフを指定して下さい。",
        "ネット検索": "キーワードを指定してネットを検索します。キーワードを指定して下さい。",
    }
    map = detect(content, ai_param)
    print(map)

if __name__ == "__main__":
    # test2()
    main()