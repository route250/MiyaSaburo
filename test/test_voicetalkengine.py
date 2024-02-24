import sys,os,traceback,time,datetime,json,re,copy
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
from MiyaSaburo.tools import JsonStreamParser, JsonStreamParseError

class PromptFactory:
    W_AI="AI"
    W_USER="User"
    K_FUNCS='functions'
    K_UPDATE_PROF='update_'+W_AI+'_profile'

    def __init__(self, prompt_dict, response_fmt ):
        self.orig_prompt_dict = copy.deepcopy(prompt_dict)
        self.orig_response_fmt = copy.deepcopy(response_fmt)
        self.prompt_dict=copy.deepcopy(prompt_dict)
        self.response_fmt = copy.deepcopy(response_fmt)

    def _LLM(self,request_text:str) ->str:
        openai_llm_model = "gpt-3.5-turbo"
        openai_timeout=5.0
        openai_max_retries=2
        client:OpenAI = OpenAI(timeout=openai_timeout,max_retries=openai_max_retries)
        request_messages = [
            { 'role':'user', 'content': request_text }
        ]
        try:
            response = client.chat.completions.create(
                messages=request_messages,
                model=openai_llm_model, max_tokens=1000, temperature=0.7,
            )
            response_text = response.choices[0].message.content
            return response_text
        except:
            logger.exception('update profile')
        return None

    def update_profile(self, result_dict:str ):
        funcs = result_dict.get( PromptFactory.K_FUNCS)
        profile = funcs.get( PromptFactory.K_UPDATE_PROF,'') if isinstance(funcs,dict) else None
        if profile and profile!="None" and profile!="null" and profile!="未設定":
            key=f'{PromptFactory.W_AI}_profile'
            orig = self.prompt_dict.get(key,"")
            if not profile in orig:
                txt = '下記の既存プロファイルに更新プロファイルをマージして結果のプロファイルだけを出力'
                txt += '\n\n# 既存\n' + orig
                txt += '\n\n# 更新\n' + profile
                txt += "\n\n# 結果\n"
                update = self._LLM(txt)
                if update:
                    self.prompt_dict[key] = update
                    print(f"UpdateProfile\n{orig}\n---\n{update}\n---")

    time_of_day_tbl = [
        # 0時から3時
        '深夜','深夜','深夜','深夜',
        # 4時から6時
        '早朝','早朝','早朝',
        # 7時から9時
        '朝','朝','朝',
        # 10時から11時
        '午前','午前',
        # 12時から13時
        '昼','昼',
        # 14時から16時
        '午後','午後','午後',
        # 17時から18時
        '夕方','夕方',
        # 19時から22時
        '夜','夜','夜','夜',
        # 23時
        '深夜',
    ]

    @staticmethod
    def get_season( dt ):
        # タイムスタンプを datetime オブジェクトに変換
        if isinstance(dt,datetime.datetime):
            dt_object = dt
        elif isinstance(dt,float):
            dt_object = datetime.datetime.fromtimestamp(dt)
        else:
            dt_object = datetime.datetime.fromtimestamp(time.time())
        day = dt_object.month*100+dt_object.day
        if day <=103:
            return '正月'
        if day < 315:
            return '冬'
        if day < 431:
            return '春'
        if day < 531:
            return '初夏'
        if day < 631:
            return '梅雨'
        if day < 931:
            return '夏'
        if day < 1031:
            return '秋'
        if day < 1231:
            return '冬'
        return ''

    @staticmethod
    def strftime( value:float, default="" ):
        if isinstance( value, float ) and value>0.0:
            """unixtimeをフォーマットする"""
            dt=datetime.datetime.fromtimestamp(value)
            season=PromptFactory.get_season(dt)
            tod = PromptFactory.time_of_day_tbl[dt.hour]
            text = dt.strftime('%Y年%m月%d '+season+' '+tod+'%H時%M分')
            # 正規表現で不要な"0"を削除 ただし、"0時"はそのまま残す
            text = re.sub(r'(?<!\d)0', '', text)  # 先頭の0を削除、ただし数字の後ろの0は残す
            return text

        return default

    topics_tbl=[ '猫について語ります', '猫について尋ねます','犬について話します','最近行った場所を話します', '行ってみたい場所を話します', '天気や気候を尋ねます', '季節の食べ物について語ります']

    @staticmethod
    def random_topic():
        return random.choice(PromptFactory.topics_tbl)


    def replace( text, key, value ) ->str:
        return text.replace("{"+key+"}",value).replace("%"+key+"%",value)
    
    def create_total_prompt( self ):
        text = ""
        # 返信フォーマット
        text += "\n"+self.response_fmt.get("prefix","")
        fmt_dict = self.response_fmt.get("format",{})
        text += PromptFactory.create_prompt_fmt2( fmt_dict )
        skl = PromptFactory.convert_to_skelton( fmt_dict )
        text += "\n\n以下のJSONで応答しろ\n"+json.dumps(skl,ensure_ascii=False)
        # プロンプト
        text += "\n\n"
        text += PromptFactory.create_prompt_fmt2( self.prompt_dict )
        #変数置換
        tm:float = time.time()
        text = PromptFactory.replace(text,'datetime', PromptFactory.strftime(tm) )
        text = PromptFactory.replace(text,'season', PromptFactory.get_season(tm) )
        text = PromptFactory.replace(text,'randomtopic', PromptFactory.random_topic() )
        text = PromptFactory.replace(text,'AI', PromptFactory.W_AI )
        text = PromptFactory.replace(text,'USER', PromptFactory.W_USER )

        return text

    def create_prompt_fmt2( fmt:dict, *, indent:str = "\n" ):
        pmt=""
        n=0
        for k,v in fmt.items():
            n+=1
            id = f"{indent}{n}."
            if isinstance(v,dict):
                pmt += f"{id} {k}:"
                pmt += PromptFactory.create_prompt_fmt2( v, indent=id )
            else:
                pmt += f"{id} {k}: {v}"
        return pmt

    def convert_to_skelton( fmt:dict ):
        if isinstance(fmt,dict):
            ret = {}
            for k,v in fmt.items():
                ret[k]=PromptFactory.convert_to_skelton(v)
        elif isinstance(fmt,list):
            ret = []
            for idx,v in enumerate(fmt):
                ret[idx] = PromptFactory.convert_to_skelton(v)
        else:
            ret = "..."
        return ret
    
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
長文(100文字以上)は禁止。短いテンポで話すよ。in casual taok by japanese.
"""

prompt_fmt="""
出力:
以下のJSONで出力すること
{
"topic":"この会話の短い表題",
"summary":"highlighting the main topics and any conclusions reached.",
"keypoint":"A list of key points or important information that we've covered.",
"current state":"current conversational state in short words. 「相互理解」「調整中」「確認中」など",
"thought":"next expected conversational state and events needed to achieve that state transition and your thought.",
"talk":"speech to user"
}
"""
prompt_dict = {
    "role": "%AI%は感情豊で自己主張がある女性型AIとして振る舞うよ。現在の日時(%datetime%)を会話の参考にするよ。",
    PromptFactory.W_AI+"_profile": "名前:未設定\n年齢:未設定\n趣味:未設定",
    "task": "人間らしい感情を示しつつ、積極的に次の話題や主張を考えて、短いテンポで、友達のようなカジュアルな言葉でコミュニケーションしよう。",
    "constraint": "長文(100文字以上)は禁止、短い会話で。%USER%に用事や話題や話したいことを質問は禁止、「話したいことはありますか？」ではなくて、次の話題を始めよう。時間や季節(%season%)を考慮して話題をすすめてね。"
}
response_fmt = {
    "prefix": "以下の項目を応答しろ",
     "format": {
        "topic": "この会話の短い表題",
        "speech": "%AI%の発言",
        "summary": "過去の要約と、それ以降の会話を合わせた要約。",
        "situation": "周囲の状況や場所、時節や会話の場面などの情報",
        "thought": "%AI%の思考内容。%USER%に質問するより、%AI%の主張をするよ。",
        "conversational sate": {
            "current": "現在の会話の状態を示す短い説明",
            "target": "会話をどのような状態に誘導するべきかを示す短い説明"
        },
        PromptFactory.K_FUNCS: {
            PromptFactory.K_UPDATE_PROF: "Optional:%AI%のprofileを修正する場合に既存の内容も含めてすべてを箇条書きで記述。未設定の項目は%AI%が自発的に決定しても良い。",
        }
    }
}


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

    pf:PromptFactory = PromptFactory( prompt_dict, response_fmt )

    messages = []
    while True:
        text, confs = speech.get_recognized_text()
        if text:
            messages.append( {'role':'user','content':text})
            request_messages = messages[-10:]
            if 0.0<confs and confs<0.6:
                request_messages.insert( len(request_messages)-2, {'role':'system','content':f'次のメッセージは、音声認識結果のconfidence={confs}'})
            pr = pf.create_total_prompt()
            request_messages.insert(0, {'role':'system','content':pr})
            openai_timeout=15.0
            openai_max_retries=2
            try:
                client:OpenAI = OpenAI(timeout=openai_timeout,max_retries=openai_max_retries)
                stream = client.chat.completions.create(
                        messages=request_messages,
                        model=openai_llm_model, max_tokens=1000, temperature=0.7,
                        stream=True, response_format={"type":"json_object"}
                )
                talk_buffer = ""
                assistant_content=""
                result_dict=None
                before_talk_text = ""
                parser:JsonStreamParser = JsonStreamParser()
                for part in stream:
                    delta_response = part.choices[0].delta.content or ""
                    assistant_content+=delta_response
                    try:
                        result_dict = parser.put(delta_response)
                    except:
                        logger.error( f'response parse error {assistant_content}')
                    talk_text= result_dict.get("speech") if result_dict is not None else ""
                    talk_text = talk_text if talk_text else ""
                    seg = talk_text[len(before_talk_text):]
                    before_talk_text = talk_text
                    talk_buffer += seg
                    if seg in talk2_split:
                        logger.info( f"{seg} : {talk_buffer}")
                        speech.add_talk(talk_buffer)
                        talk_buffer = ""
                if talk_buffer:
                    speech.add_talk(talk_buffer)
                speech.add_talk(VoiceTalkEngine.EOT)
                print( "chat response" )
                print( assistant_content )
                pf.update_profile( result_dict )
                time.sleep(2.0)
                messages.append( {'role':'assistant','content':assistant_content})
            except openai.APIConnectionError as ex:
                logger.error("Cannot connect to openai: {ex}")
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
def test3():
    pf:PromptFactory = PromptFactory( prompt_dict, response_fmt )
    txt = pf.create_total_prompt()
    print(txt)

    result_dict={
        "functions": {"update_AI_profile": "名前: みきちゃん"}
    }
    pf.update_profile( result_dict )
    txt = pf.create_total_prompt()

    print(txt)

if __name__ == "__main__":
    #test3()
    main()