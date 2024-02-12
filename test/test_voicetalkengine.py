import sys,os,traceback,time,datetime
import threading
from threading import Thread, Condition
import random
import sounddevice as sd
import numpy as np
import openai
from openai import OpenAI

# sys.path.append('/home/maeda/LLM')
print(f"cwd:{os.getcwd()}")
print(f"__name__:{__name__}")
sys.path.append(os.getcwd())
# sys.path.append('/home/maeda/LLM/MiyaSaburo/MiyaSaburo')
from MiyaSaburo.voice import VoiceTalkEngine
   
def strftime( value:float, default=None ):
    if isinstance( value, float ) and value>0.0:
        """unixtimeをフォーマットする"""
        dt=datetime.datetime.fromtimestamp(value)
        return dt.strftime('%Y年%m月%d %H時%M分')
    return default

seasonlist=[ '冬', '冬', '春', '春']
topics=[ '猫について語ります', '猫について尋ねます','犬について話します','最近行った場所を話します', '行ってみたい場所を話します', '天気や気候を尋ねます', '季節の食べ物について語ります']

def random_topic():
    return random.choice(topics)

def get_season():
    # タイムスタンプを datetime オブジェクトに変換
    dt_object = datetime.datetime.fromtimestamp(time.time())
    day = dt_object.strftime('%m%d')
    if day < '0315':
        return '冬'
    if day < '0431':
        return '春'
    if day < '0531':
        return '初夏'
    if day < '0631':
        return '梅雨'
    if day < '0931':
        return '夏'
    if day < '1031':
        return '秋'
    if day < '1231':
        return '冬'

def main():

    openai_llm_model='gpt-3.5-turbo'
    speech:VoiceTalkEngine = VoiceTalkEngine()

    speech.start()

    talk1_split = [ "、", " ", "　" ]
    talk2_split = [ "。", "!", "！", "?","？", "\n"]

    prompt = """現在日時:{datetime} 季節:{season}
    あなたは、知的な18歳の日本人女性です。カジュアルな話し方で、短い返答をします。。
    議論や詳細説明ではカジュアルな長文も話します。
    人間に用事や話題や話したいことを尋ねる代わりに、{randomtopic}。"""
    messages = []
    while True:
        text = speech.get_recognized_text()
        if text:
            messages.append( {'role':'user','content':text})
            request_messages = messages[-10:]

            now=strftime( time.time() )
            pr = prompt
            pr = pr.replace('{datetime}', now )
            pr = pr.replace('{season}', get_season() )
            pr = pr.replace('{randomtopic}', random_topic() )
            request_messages.insert(0, {'role':'system','content':pr})
            try:
                client:OpenAI = OpenAI()
                stream = client.chat.completions.create(
                        messages=request_messages,
                        model=openai_llm_model, max_tokens=256, temperature=0.7,
                        stream=True
                )
                buffer = ""
                for part in stream:
                    seg = part.choices[0].delta.content or ""
                    buffer += seg
                    if seg in talk2_split:
                        print( f"{seg}", end="")
                        speech.add_talk(buffer)
                        buffer = ""
                if buffer:
                    speech.add_talk(buffer)
                time.sleep(2.0)
                messages.append( {'role':'assistant','content':buffer})
            except:
                traceback.print_exc()

if __name__ == "__main__":
    main()