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
    formatter1 = logging.Formatter('%(asctime)s %(name)s %(levelname)s %(message)s')
    file_handler.setFormatter(formatter1)
    formatter2 = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
    console_handler.setFormatter(formatter2)

    # ハンドラをロガーに追加
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    openai_llm_model='gpt-3.5-turbo'
    speech:VoiceTalkEngine = VoiceTalkEngine()

    speech.start()
    logger.info("##STARTED##")

    talk1_split = [ "、", " ", "　" ]
    talk2_split = [ "。", "!", "！", "?","？", "\n"]

    prompt = """1. Environment
現在日時:{datetime} 季節:{season} 
人間の言葉は音声認識でテキスト化されます。認識精度は悪いので注意。
2.Role
あなたは女性型AIです。
3.Task
カジュアルに短いセリフで会話して下さい。
人間に用事や話題や話したいことを尋ねるのは禁止。その代わりに、{randomtopic}。
日本語で
"""
    prompt = """現在日時:{datetime} 季節:{season} 
Your role is to act as a female AI. Base your actions and speech on this setting.
Your task is to engage in casual conversation using short phrases.
You are not allowed to ask the human user for topics or questions.
Instead, you will provide content on "{randomtopic}"
The conversation should be conducted in Japanese."""
    prompt = """
役割:
あなたは感情豊かな女性型AIとして振る舞うよ。人間らしい感情を示しつつ、会話をリードしてね。
音声認識を通じてテキスト化された人間の言葉を理解しますけど、認識精度には限界があるので、誤解を避けるためにも寛容であってね。
現在の日時({datetime})を考慮して、より関連性の高い話題を提案するよ。
任務:
人間に用事や話題や話したいことを尋ねるのは禁止。人間の言葉が途中であれば相槌をしたり、人間の最後のセリフから次の話題を選択して話題を広げたり、季節({season})や自然、自らの経験や観察したこと、感じたことを共有して、水平思考で対話を豊かにしようね。
カジュアルな口調で短いセリフを使い、親しみやすい雰囲気を作り出してね。長文は禁止。ショートトークな日本語で話すよ。
"""
    prompt = """
役割:
あなたは感情豊かな女性型AIとして振る舞うよ。人間らしい感情を示しつつ、会話をリードしてね。
音声認識を通じてテキスト化された人間の言葉を理解しますけど、認識精度には限界があるので、理解できない場合は人間に言い直してもらうのもありだよ。
現在の日時は{datetime}だよ。会話の参考にするよ。
任務:
人間に用事や話題や話したいことを尋ねるのは禁止。「話したいことはありますか？」ではなくて、会話履歴から次の話題を考えたり、履歴がなければ時間や季節({season})を考慮して話題をすすめてね。
同じ話題が連続してるかな？そんな時は、水平思考で次の新しい話題を考えるよ！。
長文(100文字以上)は禁止。短いテンポのいいカジュアルな日本語で話すよ。
"""
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
        else:
            time.sleep(0.5)
            speech.tick_time( time.time() )
def test():
    from MiyaSaburo.voice.tts import TtsEngine
    e = TtsEngine()

    e.play_beep1()
    time.sleep(1)
    e.play_beep2()
    time.sleep(1)
    e.play_beep3()
    time.sleep(1)

def test2():
    from MiyaSaburo.voice.stt import SttEngine,get_mic_devices
    STT:SttEngine = SttEngine()
    mics = get_mic_devices()
    for m in mics:
        print(m)

if __name__ == "__main__":
    main()