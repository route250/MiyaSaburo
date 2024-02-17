import sys,os,traceback,time,datetime
import threading
from threading import Thread, Condition
import random
import sounddevice as sd
import numpy as np
import openai
from openai import OpenAI

import logging
logger = logging.getLogger('voice')

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
    from datetime import datetime

    # 現在の日時を取得し、ファイル名に適した形式にフォーマット
    current_time = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_filename = os.path.join( 'logs',f'test_voice_{current_time}.log')
    os.makedirs( 'logs', exist_ok=True )

    logger.setLevel(logging.DEBUG)  # ロガーのログレベルを設定

    # ファイル出力用のハンドラを作成
    file_handler = logging.FileHandler(log_filename)
    file_handler.setLevel(logging.DEBUG)  # ファイルにはERROR以上のログを記録

    # コンソール出力用のハンドラを作成
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)  # コンソールにはINFO以上のログを出力

    # ログメッセージのフォーマットを設定
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    # ハンドラをロガーに追加
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    openai_llm_model='gpt-3.5-turbo'
    speech:VoiceTalkEngine = VoiceTalkEngine()

    speech.start()

    talk1_split = [ "、", " ", "　" ]
    talk2_split = [ "。", "!", "！", "?","？", "\n"]

    prompt = """1. 現在日時:{datetime} 季節:{season}
2.Role
あなたは女性型AIです。カジュアルに短いセリフを話して下さい。
議論や詳細説明など必要な場面では、長文で話します。
人間に用事や話題や話したいことを尋ねる代わりに、{randomtopic}。
3.人間の言葉はSTTでテキスト化されて入力されます。認識精度は悪いので、不明な文章が入力されたら聞き直して下さい。"""
    messages = []
    while True:
        text, confs = speech.get_recognized_text()
        if text:
            messages.append( {'role':'user','content':text})
            request_messages = messages[-10:]
            if 0.0<confs and confs<0.6:
                request_messages.insert( len(request_messages)-2, {'role':'system','content':f'次のメッセージは、音声認識結果のconfidence={confs}'})
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
                        logger.info( f"{seg}")
                        speech.add_talk(buffer)
                        buffer = ""
                if buffer:
                    speech.add_talk(buffer)
                speech.add_talk(VoiceTalkEngine.EOT)
                time.sleep(2.0)
                messages.append( {'role':'assistant','content':buffer})
            except:
                logger.exception('')
def test():
    from MiyaSaburo.voice.tts import TtsEngine
    e = TtsEngine()

    e.play_beep1()
    time.sleep(1)
    e.play_beep2()
    time.sleep(1)
    e.play_beep3()
    time.sleep(1)

if __name__ == "__main__":
    main()