import sys,os,re,time,json,re,copy,math
import unicodedata
from pathlib import Path
import traceback
import threading
from threading import Thread, ThreadError
from concurrent.futures import ThreadPoolExecutor, Future
import logging
from logging.handlers import TimedRotatingFileHandler
import queue
import datetime
from zoneinfo import ZoneInfo
import heapq
from collections import Counter
import requests
from requests.adapters import HTTPAdapter
import httpx

import numpy as np
import openai
from openai import OpenAI
from openai.types import Completion, CompletionChoice, CompletionUsage
from openai.types import CreateEmbeddingResponse, Embedding
from openai.types.chat import ChatCompletion, ChatCompletionToolParam, ChatCompletionMessage
from openai.types.chat.chat_completion_message_tool_call import ChatCompletionMessageToolCall, Function
from openai.types.chat.completion_create_params import ResponseFormat
from openai._types import Timeout
import tiktoken
from tiktoken.core import Encoding
try:
    from libs.utils import Utils
except ImportError:
    from MiyaSaburo.libs.utils import Utils

from gtts import gTTS
from io import BytesIO
import pygame

import speech_recognition as sr
import vosk
from vosk import Model, KaldiRecognizer, SpkModel
import sounddevice as sd
import librosa
import pyworld as pw

from sklearn.decomposition import PCA
vosk.SetLogLevel(-1)
Price = {
    "gpt3.5"
}
Price_in: float = 0.0015
Price_out: float = 0.001
DollYen:int = 150
def doll_to_yen( doll:float ) -> int:
    return int( 0.5 + doll * DollYen )

if not os.path.exists("logs"):
    os.makedirs("logs")
logger = logging.getLogger("AIbot")
logger.setLevel(logging.DEBUG)
loghdr = TimedRotatingFileHandler('logs/bot.log', when='midnight', backupCount=7)
loghdr.encoding = 'utf8'
loghdr.setFormatter( logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
loghdr.setLevel(logging.DEBUG)
conhdr = logging.StreamHandler()
conhdr.setFormatter( logging.Formatter("%(asctime)s %(message)s"))
conhdr.setLevel(logging.INFO)
logger.addHandler(loghdr)
logger.addHandler(conhdr)
api_logger = logging.getLogger("api")
api_logger.setLevel(logging.DEBUG)
loghdr = TimedRotatingFileHandler('logs/api.log', encoding='utf8', when='midnight', backupCount=7)
loghdr.setFormatter( logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
api_logger.addHandler(loghdr)

z_next_id: int = 10000

def next_id():
    global z_next_id
    id = z_next_id
    z_next_id += 1
    return id

def length( value ):
    if value is None:
        return 0
    else:
        return len(value)

_openai_client: OpenAI = None
def get_client():
    global _openai_client
    if _openai_client is None:
        if openai.api_key is None:
            openai.api_key=os.getenv('OPENAI_API_KEY')
            if openai.api_key is None:
                BotUtils.load_api_keys()
                openai.api_key=os.getenv('OPENAI_API_KEY')
        _openai_client = OpenAI( timeout=httpx.Timeout(180.0, connect=5.0), max_retries=0 )
    return _openai_client

class ToolBuilder:
    def __init__(self, name, description=None ):
        self.name = name
        self.description = description
        self.properties = {}
        self.required = []
    def param( self, name, description=None, enum:list[str] = None, type="string"):
        prop:dict = { 'type': type }
        if description is not None:
            prop['description'] = description
        if isinstance(enum,list) and len(enum)>0 and isinstance(enum[0],str):
            prop['enum'] = enum
        self.properties[name] = prop
        self.required.append(name)
        return self
    def build(self) -> ChatCompletionToolParam:
        return ChatCompletionToolParam({
            "type": "function",
            "function": {
                "name": self.name,
                "parameters": {
                    "type": "object",
                    "properties": self.properties,
                    "required": self.required
                }
            }
        })

    @staticmethod
    def decode( f:ChatCompletionMessageToolCall ) ->ChatCompletionMessageToolCall:
        f.function.arguments = BotUtils.decode_utf8( f.function.arguments )
        f.function.name = BotUtils.decode_utf8(f.function.name)
        return f

    @staticmethod
    def decode_tool_calls( orig_message ):
        message = json.loads(orig_message.json())
        print( f"[JSON]{message}")
        tool_calls = message.get("tool_calls",[])
        for call in tool_calls:
            funcs = call.get("function",{})
            args = funcs.get("arguments")
            if args:
                funcs["arguments"]=json.dumps(json.loads(args),ensure_ascii=False)
        return message

class BotCore:

    def __init__(self):
        self.lock = threading.Lock()
        self.prompt_tokens: int = 0
        self.completion_tokens: int = 0
        self.total_tokens:int  = 0
        self.last_talk_time: float = 0
        self.info_callback = None
        self.info_data:dict = {}
        self._before_info_data = None
        self.connect_timeout:float = 10.0
        self.read_timeout:float = 60.0
        self._load_api_key: bool = False
        self.log_callback = None
        #
        self._location:str = None
        self._update_location:float = 0

    def notify_log(self, message:str ):
        try:
            if self.log_callback is not None:
                self.log_callback(message)
        except:
            traceback.print_exc()

    def set_chat_callback( self, chat_callback=None ) ->None:
        pass

    def update_info( self, data:dict ) -> None:
        BotUtils.update_dict( data, self.info_data )
        if not self.info_data == self._before_info_data:
            self._before_info_data = copy.deepcopy( self.info_data )
            if self.info_callback is not None:
                self.info_callback( self.info_data )
    
    def setTTS(self, speaker_id=None ):
        pass

    def set_recg_callback( self, recg_callback=None, plot_callback=None ) ->None:
        pass

    def set_recg_autosend( self, sw=False ) ->None:
        pass

    def token_usage( self, response ):
        with self.lock:
            global prompt_tokens, completion_tokens, total_tokens
            try:
                model = response.model
                price_in:float = 0.0015
                price_out:float = 0.002
                if model == "gpt4":
                    price_in = 0.01
                    price_out = 0.01
                usage = response.usage
                p = usage.prompt_tokens
                c = usage.completion_tokens
                t = usage.total_tokens
                self.prompt_tokens += p
                self.completion_tokens += c
                self.total_tokens += t
                self.in_doll = int((self.prompt_tokens+999)/1000) * price_in
                self.out_doll = int((self.completion_tokens+999)/1000) * price_out
                self.total_doll = self.in_doll + self.out_doll
                y = doll_to_yen( self.total_doll )
                print( f"total:{t}/{self.total_tokens} {y}(Yen) ${self.total_doll:.4f} prompt:{p}/{self.prompt_tokens} ${self.in_doll:.4f} completion:{c}/{self.completion_tokens} ${self.out_doll:.4f} ")
                return True
            except Exception as ex:
                return False

    def print_tokens(self):
        with self.lock:
            y = self.total_doll * 150
            print( f"[COST] total {y:.1f}円 ${self.total_doll:.4f}({self.total_tokens})  in ${self.in_doll:.4f}({self.prompt_tokens})  out  ${self.out_doll:.4f}({self.completion_tokens})")

    def Completion(self, prompt, *, max_tokens=None, temperature=0 ) -> str:
        content:str = None
        try:
            self.notify_log(prompt)
            in_count = BotUtils.token_count( prompt )
            if max_tokens is None:
                max_tokens = 4096
            u = max_tokens - in_count - 50
            client:OpenAI = get_client()
            for retry in range(2,-1,-1):
                try:
                    response: Completion = client.completions.create(
                            model="gpt-3.5-turbo-instruct",
                            temperature = temperature, max_tokens=u,
                            prompt=prompt
                            )
                    break
                except (openai.APITimeoutError,openai.RateLimitError,openai.InternalServerError,openai.APIConnectionError,ConnectionRefusedError) as ex:
                    if retry>0:
                        print( f"{ex}" )
                        time.sleep(5)
                    else:
                        raise ex
                except openai.AuthenticationError as ex:
                    if not self._load_api_key:
                        self._load_api_key=True
                        BotUtils.load_api_keys()
                    else:
                        raise ex

            self.token_usage( response )           
            if response is None or response.choices is None or len(response.choices)==0:
                print( f"Error:invalid response from openai\n{response}")
                return None
            content = response.choices[0].text.strip()
            if content is None:
                print( f"Error:invalid response from openai\n{response}")
                return None
            return content
        except openai.AuthenticationError as ex:
            api_logger.error( f"{ex}" )
            logger.error( f"ChatCompletion {ex}" )
        except (openai.APITimeoutError,openai.RateLimitError,openai.InternalServerError,openai.APIConnectionError,ConnectionRefusedError) as ex:
            api_logger.error( f"{ex}" )
            logger.error( f"ChatCompletion {ex}" )
        except Exception as ex:
            traceback.print_exc()
            return None
        finally:
            self.notify_log(content)

    def ChatCompletion( self, mesg_list:list[dict], temperature:float=0, stop=None, *, max_retries=2, read_timeout=60, json_fmt:dict=None ):
        """ChatCompletionを実行する

        Args:
            mesg_list (list[dict]): 会話履歴
            temperature (float, optional): 生成精度. Defaults to 0.
            stop (_type_, optional): 停止文字. Defaults to None.
            max_retries (int, optional): リトライ回数. Defaults to 2.
            read_timeout (int, optional): 通信タイムアウト. Defaults to 60.
            json_fmt (dict, optional): 返信フォーマット指定. Defaults to None.

        Returns:
            str: 生成された文章
        """
        ret,tool_calls = self.ChatCompletion3(mesg_list,temperature,stop,max_retries=max_retries, read_timeout=read_timeout, json_fmt=json_fmt )
        return ret

    def ChatCompletion2( self, mesg_list:list[dict], temperature:float=0, stop=None, *, tools=None, tool_choice=None, max_retries=2, read_timeout=60, json_fmt:dict=None ):
        # toolが無い場合
        if tools is None:
            return self.ChatCompletion3(mesg_list,temperature,stop,max_retries=max_retries, read_timeout=read_timeout, json_fmt=json_fmt )

        # toolがある場合、無いツールを指定してきたりするのでチェックしてリトライする
        try_count = 0
        while True:
            res,tool_calls = self.ChatCompletion3(mesg_list,temperature,stop,tools=tools,tool_choice=tool_choice, max_retries=max_retries, read_timeout=read_timeout, json_fmt=json_fmt )
            # toolが無い場合
            if try_count>=2 or not isinstance(tool_calls,list):
                return res,tool_calls
            # toolがある場合
            # 呼び出したfunction名のリスト
            func_names = [ t.get('function',{}).get('name',None) for t in tools]
            # 戻り値のfunctionから、func_namesに含まれるものだけ
            new_calls = [ call for call in tool_calls if call.get("function",{}).get('name','xxxxxxxx') in func_names]
            if len(new_calls)>0:
                return res,new_calls[:1]
            invalid_names = [ call.get("function",{}).get('name',None) for call in tool_calls if call.get("function",{}).get('name','xxxxxxxx') not in func_names]
            print( f"[ERROR] tool_calls invalid func name {invalid_names} ")
            try_count += 1

    def ChatCompletion3( self, mesg_list:list[dict], temperature:float=0, stop=None, *, tools=None, tool_choice=None, max_retries=2, read_timeout=60, json_fmt:dict=None ):
        content = None
        tool_calls = None
        try:
            mesg_list2:list[dict] = mesg_list
            kwargs = {}
            if tools:
                kwargs['tools'] = tools
            if tool_choice:
                kwargs['tool_choice'] = tool_choice
            if isinstance(json_fmt,dict):
                kwargs['response_format'] = ResponseFormat( type='json_object' )
                json_prompt:str = f"JSON format\n {json.dumps(json_fmt,ensure_ascii=False)}"
                mesg_list2.append( { 'role': 'system', 'content': json_prompt })
            api_logger.debug( "request" + "\n" + json.dumps( mesg_list2, indent=2, ensure_ascii=False) )
            self.notify_log( mesg_list2 )

            client:OpenAI = get_client()
            client = client.with_options( timeout=Timeout( 60, connect=5.0, write=5.0, read=read_timeout), max_retries=0 )
            for retry in range(max_retries,-1,-1):
                try:
                    response = client.chat.completions.create(
                            model="gpt-3.5-turbo-1106",
                            temperature = temperature,
                            messages=mesg_list2,
                            **kwargs
                        )
#                   request_timeout=(self.connect_timeout,self.read_timeout)
                    api_logger.debug( "response" + "\n" + response.model_dump_json(indent=2) )
                    break
                except (openai.APITimeoutError,openai.RateLimitError,openai.APIConnectionError,ConnectionRefusedError) as ex:
                    api_logger.error( f"{ex}" )
                    if retry>0:
                        logger.error( f"ChatCompletion {ex}" )
                        time.sleep(5)
                    else:
                        raise ex
                except (openai.InternalServerError) as ex:
                    api_logger.error( f"{type(ex)}" )
                    if retry>0:
                        logger.error( f"ChatCompletion {type(ex)}" )
                        time.sleep(5)
                    else:
                        raise ex
                except openai.AuthenticationError as ex:
                    if not self._load_api_key:
                        self._load_api_key=True
                        BotUtils.load_api_keys()
                    else:
                        raise ex

            self.token_usage( response )
            if response is None or response.choices is None or len(response.choices)==0:
                logger.error( f"invalid response from openai\n{response}")
            else:
                msg = response.choices[0].message
                if msg.tool_calls is not None:
                    content = msg.content
                    decorded = json.loads(msg.json())
                    print( f"[JSON]{decorded}")
                    tool_calls = decorded.get("tool_calls")
                else:
                    content = msg.content.strip() if msg.content is not None else ""

        except openai.BadRequestError as ex:
            try:
                data = json.loads(ex.response.text)
                mesg = data['error']['message']
                api_logger.error( f"BadRequestError {mesg}" )
                logger.error( f"ChatCompletion BadRequestError {mesg}" )
            except:
                api_logger.error( f"{ex}" )
                logger.error( f"ChatCompletion {ex}" )

        except openai.AuthenticationError as ex:
            api_logger.error( f"{ex}" )
            logger.error( f"ChatCompletion {ex}" )
        except (openai.APITimeoutError,openai.RateLimitError,openai.InternalServerError,openai.APIConnectionError,ConnectionRefusedError) as ex:
            api_logger.error( f"{ex}" )
            logger.error( f"ChatCompletion {ex}" )
        except Exception as ex:
            api_logger.exception( f"%s", ex )
            logger.exception( f"%s", ex )

        self.notify_log(content)
        return (content, tool_calls)

    def timer_task(self) -> None:
        pass

    def get_location(self) -> str:
        try:
            now_dt:float = time.time()
            if self._location is None or (now_dt-self._update_location)>300.0:
                data:dict = BotUtils.get_location()
                if data is not None:
                    location = BotUtils.join_str( data.get('city'), BotUtils.join_str( data.get('region'), data.get('country'), sep=" "), sep=" ")
                    if not BotUtils.is_empty(location):
                        self._location = location
        except:
            pass
        return self._location

class TtsEngine:
    VoiceList = [
        ( "VOICEVOX:四国めたん [あまあま]", 0, 'ja_JP' ),
        ( "VOICEVOX:四国めたん [ノーマル]", 2, 'ja_JP' ),
        ( "VOICEVOX:四国めたん [セクシー]", 4, 'ja_JP' ),
        ( "VOICEVOX:四国めたん [ツンツン]", 6, 'ja_JP' ),
        ( "VOICEVOX:ずんだもん [あまあま]", 1, 'ja_JP' ),
        ( "VOICEVOX:ずんだもん [ノーマル]", 3, 'ja_JP' ),
        ( "VOICEVOX:ずんだもん [セクシー]", 5, 'ja_JP' ),
        ( "VOICEVOX:ずんだもん [ツンツン]", 7, 'ja_JP' ),
        ( "VOICEVOX:春日部つむぎ [ノーマル]",8, 'ja_JP' ),
        ( "VOICEVOX:波音リツ [ノーマル]", 9, 'ja_JP' ),
        ( "VOICEVOX:雨晴はう [ノーマル]", 10, 'ja_JP' ),
        ( "VOICEVOX:玄野武宏 [ノーマル]", 11, 'ja_JP' ),
        ( "VOICEVOX:白上虎太郎 [ふつう]", 11, 'ja_JP' ),
        ( "VOICEVOX:白上虎太郎 [わーい]", 32, 'ja_JP' ),
        ( "VOICEVOX:白上虎太郎 [びくびく]", 33, 'ja_JP' ),
        ( "VOICEVOX:白上虎太郎 [おこ]", 34, 'ja_JP' ),
        ( "VOICEVOX:白上虎太郎 [びえーん]", 36, 'ja_JP' ),
        ( "VOICEVOX:もち子(cv 明日葉よもぎ)[ノーマル]", 20, 'ja_JP' ),
        ( "OpenAI:alloy", 1001, 'ja_JP' ),
        ( "OpenAI:echo", 1002, 'ja_JP' ),
        ( "OpenAI:fable", 1003, 'ja_JP' ),
        ( "OpenAI:onyx", 1004, 'ja_JP' ), # 男性っぽい
        ( "OpenAI:nova", 1005, 'ja_JP' ), # 女性っぽい
        ( "OpenAI:shimmer", 1006, 'ja_JP' ), # 女性ぽい
        ( "gTTS:[ja_JP]", 2000, 'ja_JP' ),
        ( "gTTS:[en_US]", 2001, 'en_US' ),
        ( "gTTS:[en_GB]", 2002, 'en_GB' ),
        ( "gTTS:[fr_FR]", 2003, 'fr_FR' ),
    ]

    @staticmethod
    def id_to_model( idx:int ) -> str:
        return next((voice for voice in TtsEngine.VoiceList if voice[1] == idx), None )

    @staticmethod
    def id_to_name( idx:int ) -> str:
        voice = TtsEngine.id_to_model( idx )
        name = voice[0]
        return name if name else '???'

    @staticmethod
    def id_to_lang( idx:int ) -> str:
        voice = TtsEngine.id_to_model( idx )
        lang = voice[2]
        return lang if lang else 'ja_JP'

    def __init__(self, *, speaker=-1, submit_task = None, talk_callback = None ):
        # 並列処理用
        self.lock: threading.Lock = threading.Lock()
        self._running_future:Future = None
        self._running_future2:Future = None
        self.wave_queue:queue.Queue = queue.Queue()
        self.play_queue:queue.Queue = queue.Queue()
        # 発声中のセリフのID
        self._talk_id: int = 0
        # 音声エンジン選択
        self.speaker = speaker
        # コールバック
        self.submit_call = submit_task # スレッドプールへの投入
        self.start_call = talk_callback # 発声開始と完了を通知する
        # pygame初期化済みフラグ
        self.pygame_init:bool = False
        # 音声エンジン無効時間
        self._disable_gtts: float = 0.0
        self._disable_openai: float = 0.0
        self._disable_voicevox: float = 0.0
        # VOICEVOXサーバURL
        self._voicevox_url = None
        self._voicevox_port = os.getenv('VOICEVOX_PORT','50021')
        self._voicevox_list = list(set([os.getenv('VOICEVOX_HOST','127.0.0.1'),'127.0.0.1','192.168.0.104','chickennanban.ddns.net']))

    def cancel(self):
        self._talk_id += 1

    def _get_voicevox_url( self ) ->str:
        if self._voicevox_url is None:
            self._voicevox_url = BotUtils.find_first_responsive_host(self._voicevox_list,self._voicevox_port)
        return self._voicevox_url

    @staticmethod
    def remove_code_blocksRE(markdown_text):
        # 正規表現を使用してコードブロックを検出し、それらを改行に置き換えます
        # ```（コードブロックの開始と終了）に囲まれた部分を検出します
        # 正規表現のパターンは、```で始まり、任意の文字（改行を含む）にマッチし、最後に```で終わるものです
        # re.DOTALLは、`.`が改行にもマッチするようにするフラグです
        pattern = r'```.*?```'
        return re.sub(pattern, '\n', markdown_text, flags=re.DOTALL)

    @staticmethod
    def split_talk_text( text):
        sz = len(text)
        st = 0
        lines = []
        while st<sz:
            block_start = text.find("```",st)
            newline_pos = text.find('\n',st)
            if block_start>=0 and ( newline_pos<0 or block_start<newline_pos ):
                if st<block_start:
                    lines.append( text[st:block_start] )
                block_end = text.find( "```", block_start+3)
                if (block_start+3)<block_end:
                    block_end += 3
                else:
                    block_end = sz
                lines.append( text[block_start:block_end])
                st = block_end
            else:
                if newline_pos<0:
                    newline_pos = sz
                if st<newline_pos:
                    lines.append( text[st:newline_pos] )
                st = newline_pos+1
        return lines

    def add_talk(self, full_text:str, emotion:int = 0 ) -> None:
        talk_id:int = self._talk_id
        for text in TtsEngine.split_talk_text(full_text):
            self.wave_queue.put( (talk_id, text, emotion ) )
        with self.lock:
            if self._running_future is None:
                self._running_future = self.submit_call(self.run_text_to_audio)
    
    def run_text_to_audio(self)->None:
        """ボイススレッド
        テキストキューからテキストを取得して音声に変換して発声キューへ送る
        """
        while True:
            talk_id:int = -1
            text:str = None
            emotion:int = -1
            with self.lock:
                try:
                    talk_id, text, emotion = self.wave_queue.get_nowait()
                except Exception as ex:
                    if not isinstance( ex, queue.Empty ):
                        traceback.print_exc()
                    talk_id=-1
                    text = None
                if text is None:
                    self._running_future = None
                    return
            try:
                if talk_id == self._talk_id:
                    # textから音声へ
                    audio_bytes, tts_model = self._text_to_audio( text, emotion )
                    self._add_audio( talk_id,text,emotion,audio_bytes,tts_model )
            except Exception as ex:
                traceback.print_exc()

    def _add_audio( self, talk_id:int, text:str, emotion:int, audio_bytes: bytes, tts_model:str=None ) -> None:
        self.play_queue.put( (talk_id,text,emotion,audio_bytes,tts_model) )
        with self.lock:
            if self._running_future2 is None:
                self._running_future2 = self.submit_call(self.run_talk)

    @staticmethod
    def __penpenpen( text, default=" " ) ->str:
        if text is None or text.startswith("```"):
            return default # VOICEVOX,OpenAI,gTTSで、エラーにならない無音文字列
        else:
            return text
        
    def _text_to_audio_by_voicevox(self, text: str, emotion:int = 0, lang='ja') -> bytes:
        if self._disable_voicevox>0 and (time.time()-self._disable_voicevox)<180.0:
            return None,None
        sv_url: str = self._get_voicevox_url()
        if sv_url is None:
            self._disable_voicevox = time.time()
            return None,None
        try:
            self._disable_voicevox = 0
            timeout = (5.0,180.0)
            params = {'text': TtsEngine.__penpenpen(text, ' '), 'speaker': self.speaker, 'timeout': timeout }
            s:requests.Session = requests.Session()
            s.mount(f'{sv_url}/audio_query', HTTPAdapter(max_retries=1))
            res1 : requests.Response = requests.post( f'{sv_url}/audio_query', params=params)

            params = {'speaker': self.speaker, 'timeout': timeout }
            headers = {'content-type': 'application/json'}
            res = requests.post(
                f'{sv_url}/synthesis',
                data=res1.content,
                params=params,
                headers=headers
            )
            model:str = TtsEngine.id_to_name(self.speaker)
            # wave形式 デフォルトは24kHz
            return res.content, model
        except requests.exceptions.ConnectTimeout as ex:
            print( f"[VOICEVOX] {type(ex)} {ex}")
        except requests.exceptions.ConnectionError as ex:
            print( f"[VOICEVOX] {type(ex)} {ex}")
        except Exception as ex:
            print( f"[VOICEVOX] {type(ex)} {ex}")
            traceback.print_exc()
        self._disable_voicevox = time.time()
        return None,None

    def _text_to_audio_by_gtts(self, text: str, emotion:int = 0) -> bytes:
        if self._disable_gtts>0 and (time.time()-self._disable_gtts)<180.0:
            return None,None
        voice = TtsEngine.id_to_model( self.speaker )
        lang = voice[2] if voice else 'ja_JP'
        lang = lang[:2]
        try:
            self._disable_gtts = 0
            tts = gTTS(text=TtsEngine.__penpenpen(text,'!!'), lang=lang,lang_check=False )
            # gTTSはmp3で返ってくる
            with BytesIO() as buffer:
                tts.write_to_fp(buffer)
                wave:bytes = buffer.getvalue()
                del tts
                return wave,f"gTTS[{lang}]"
        except AssertionError as ex:
            if "No text to send" in str(ex):
                return None,f"gTTS[{lang}]"
            print( f"[gTTS] {ex}")
            traceback.print_exc()
        except requests.exceptions.ConnectTimeout as ex:
            print( f"[gTTS] timeout")
        except Exception as ex:
            print( f"[gTTS] {ex}")
            traceback.print_exc()
        self._disable_gtts = time.time()
        return None,None

    def _text_to_audio_by_openai(self, text: str, emotion:int = 0) -> bytes:
        if self._disable_openai>0 and (time.time()-self._disable_openai)<180.0:
            return None,None
        try:
            vc:str = "alloy"
            if self.speaker==1001:
                vc = "alloy"
            elif self.speaker==1002:
                vc = "echo"
            elif self.speaker==1003:
                vc = "fable"
            elif self.speaker==1004:
                vc = "onyx"
            elif self.speaker==1005:
                vc = "nova"
            elif self.speaker==1006:
                vc = "shimmer"
            self._disable_openai = 0
            client:OpenAI = get_client()
            response:openai._base_client.HttpxBinaryResponseContent = client.audio.speech.create(
                model="tts-1",
                voice=vc,
                response_format="mp3",
                input=TtsEngine.__penpenpen(text,' ')
            )
            # openaiはmp3で返ってくる
            return response.content,f"OpenAI:{vc}"
        except requests.exceptions.ConnectTimeout as ex:
            print( f"[gTTS] timeout")
        except Exception as ex:
            print( f"[gTTS] {ex}")
            traceback.print_exc()
        self._disable_openai = time.time()
        return None,None

    def _text_to_audio( self, text: str, emotion:int = 0 ) -> bytes:
        wave: bytes = None
        model:str = None
        if 0<=self.speaker and self.speaker<1000:
            wave, model = self._text_to_audio_by_voicevox( text, emotion )
        if 1000<=self.speaker and self.speaker<2000:
            wave, model = self._text_to_audio_by_openai( text, emotion )
        if wave is None:
            wave, model = self._text_to_audio_by_gtts( text, emotion )
        return wave,model
        
    def run_talk(self)->None:
        start:bool = False
        while True:
            talk_id:int = -1
            text:str = None
            emotion: int = 0
            audio:bytes = None
            tts_model:str = None
            with self.lock:
                try:
                    talk_id, text, emotion, audio, tts_model = self.play_queue.get_nowait()
                except Exception as ex:
                    if not isinstance( ex, queue.Empty ):
                        traceback.print_exc()
                    talk_id=-1
                    text = None
                    audio = None
                if text is None:
                    self._running_future2 = None
                    return
            try:
                if talk_id == self._talk_id:
                    if audio is not None:
                        if not self.pygame_init:
                            pygame.mixer.pre_init(16000,-16,1,10240)
                            pygame.mixer.quit()
                            pygame.mixer.init()
                            self.pygame_init = True
                        mp3_buffer = BytesIO(audio)
                        pygame.mixer.music.load(mp3_buffer)
                        pygame.mixer.music.play(1,0.0) # 再生回数１回、フェードイン時間ゼロ
                    if self.start_call is not None:
                        self.start_call( text, emotion, tts_model )
                    if audio is not None:
                        while pygame.mixer.music.get_busy():
                            if talk_id != self._talk_id:
                                pygame.mixer.music.stop()
                                break
                            time.sleep(0.2)
                    if self.start_call is not None:
                        self.start_call( None, emotion, tts_model )
                    time.sleep(0.5)
                    
            except Exception as ex:
                traceback.print_exc()



class VoiceSeg:

    def __init__(self):
        self.f0_cut =0.3
        self.f0_mid = 0.8
        self._buf_sz = 100
        self._buf_count=0
        self._buf_list = [None] * (self._buf_sz+1)
        self._before_level = 0
        self._before_rec:bool = False
        self._pre_length=2
        self._post_length = 3
        self._post_count = 0
        self._buf_count_low = 3
    
    def reset(self):
        self._buf_count = 0

    # F0をカウントして有声無声判定
    # https://blog.shinonome.io/voice-recog-random/
    # https://qiita.com/zukky_rikugame/items/dea51c60bfb984d39029
    def _f0_ratio( self, wave_float64, sr ) ->float:
        _f0, t = pw.dio(wave_float64, sr, frame_period=1) 
        f0 = pw.stonemask(wave_float64, _f0, t, sr)
        f0_vuv = f0[f0 > 0] # 有声・無声フラグ
        vuv_ratio = len(f0_vuv)/len(f0) # 有声部分の割合
        return vuv_ratio

    def _calc_mfcc(self, wave_float2, frame_rate ):
        mfcc_list = librosa.feature.mfcc(  y=wave_float2, sr=frame_rate, n_mfcc=20, n_fft=512 )
        mfcc_13 = mfcc_list[ 1:14, : ]
        # mfcc = np.average(mfcc_13,axis=1)
        # mfcc = np.mean(mfcc_13,axis=1)
        mfcc = np.max(mfcc_13,axis=1)
        return mfcc

    def _trim(self):
        if self._buf_count > self._pre_length:
            diff = self._buf_count - self._pre_length
            for idx in range(0,self._pre_length):
                self._buf_list[idx] = self._buf_list[idx+diff]
            self._buf_count = self._pre_length


    def put(self, wave:np.ndarray, frame_rate:int, xflg:bool = False ):
        sec:float = (float(len(wave))/float(frame_rate))
        wave_int16:np.ndarray = wave.astype(np.int16)
        wave_float64:np.ndarray = wave.astype(np.float64)
        wave_float64 = wave_float64 / 32767.0
        f0_ratio = self._f0_ratio( wave_float64, frame_rate )
        f0_level = 2 if f0_ratio>self.f0_mid else 1 if f0_ratio>self.f0_cut else 0
        flush:bool = False
        rec:bool = self._before_rec

        empty=False
        if rec:
            if f0_level == 0:
                self._post_count += 1
                if self._post_count >= self._post_length:
                    if self._buf_count > ( self._pre_length + self._buf_count_low + self._post_length ):
                        flush = True
                    else:
                        self._trim()
                    rec = False
            else:
                self._post_count = 0
        else:
            if f0_level>=2:
                rec = True
                self._post_count = 0
            else:
                if self._buf_count>=self._pre_length:
                    if xflg:
                        f0_level = -1
                        flush = True
                        empty = True
                    else:
                        self._trim()

        if flush or self._buf_count>=self._buf_sz:
            if empty:
                print(f"[frame] F0 ratio:{f0_ratio:6.3f} {self._before_level} to {f0_level} rec:{rec} EMPTY!")
            elif self._before_level != f0_level or self._before_rec != rec:
                print(f"[frame] F0 ratio:{f0_ratio:6.3f} {self._before_level} to {f0_level} rec:{rec} FLUSH!")
        # else:
        #     if self._before_level != f0_level or self._before_rec != rec:
        #         print(f"[frame] F0 ratio:{f0_ratio:6.3f} {self._before_level} to {f0_level} rec:{rec}")

        self._buf_list[self._buf_count] = wave_int16
        self._buf_count += 1
        self._before_level = f0_level
        self._before_rec = rec

        if flush or self._buf_count>=self._buf_sz:
            # 有声から無声に変化した、もしくは、バッファがいっぱいなら
            concat_int16 = np.concatenate(self._buf_list[:self._buf_count])
            self._buf_count = 0
            self._post_count = 0
            # mfcc計算
            wave_float = concat_int16.astype(np.float64)
            wave_float2 = wave_float / 32767.0
            mfcc = self._calc_mfcc( wave_float2, frame_rate )
            # byteデータへ変換
            #byte_data = concat_int16.astype(np.int16).tobytes()
            # 次のキューへ
            return f0_level, concat_int16, mfcc
        else:
            return f0_level, None, None
        
    def put2(self, wave:np.ndarray, frame_rate:int, xflg:bool = False ):
        sec:float = (float(len(wave))/float(frame_rate))
        wave_int16:np.ndarray = wave.astype(np.int16)
        wave_float64:np.ndarray = wave.astype(np.float64)
        wave_float64 = wave_float64 / 32767.0
        f0_ratio = self._f0_ratio( wave_float64, frame_rate )
        f0_level = 2 if f0_ratio>self.f0_mid else 1 if f0_ratio>self.f0_cut else 0
        flush:bool = False
        rec:bool = self._before_rec
        if xflg:
            rec = True
        if rec:
            if self._before_level==0 and f0_level==0:
                flush = True
                rec = False
        else:
            if f0_level>=2:
                rec = True
            else:
                if self._buf_count>1:
                    for idx in range(1,self._buf_count):
                        self._buf_list[idx-1] = self._buf_list[idx]
                    self._buf_count -= 1

        if self._before_level != f0_level or self._before_rec != rec:
            print(f"[frame] F0 ratio:{f0_ratio:6.3f} {self._before_level} to {f0_level} rec:{rec}")

        self._buf_list[self._buf_count] = wave_int16
        self._buf_count += 1
        self._before_level = f0_level
        self._before_rec = rec

        if flush or self._buf_count>=self._buf_sz:
            # 有声から無声に変化した、もしくは、バッファがいっぱいなら
            concat_int16 = np.concatenate(self._buf_list[:self._buf_count])
            self._buf_count = 0
            # mfcc計算
            wave_float = concat_int16.astype(np.float64)
            wave_float2 = wave_float / 32767.0
            mfcc = self._calc_mfcc( wave_float2, frame_rate )
            # byteデータへ変換
            #byte_data = concat_int16.astype(np.int16).tobytes()
            # 次のキューへ
            return f0_level, concat_int16, mfcc
        else:
            return f0_level, None, None
        
    def put1(self, wave:np.ndarray, frame_rate:int, xflg:bool = False ):
        wave_int16:np.ndarray = wave.astype(np.int16)
        wave_float64:np.ndarray = wave.astype(np.float64)
        wave_float64 = wave_float64 / 32767.0
        f0_ratio = self._f0_ratio( wave_float64, frame_rate )
        f0_level = 2 if f0_ratio>self.f0_mid else 1 if f0_ratio>self.f0_cut else 0
        if self._before_level != f0_level:
            print(f"[frame] F0 ratio:{f0_ratio:6.3f} {self._before_level} to {f0_level}")
        
        self._buf_list[self._buf_count] = wave_int16
        self._buf_count += 1
        flush:bool = self._buf_count >= self._buf_sz
        if self._before_level >= 2:
            if f0_level >= 2:
                pass
            elif f0_level == 1:
                flush = True
            else:
                flush = True
        elif self._before_level == 1:
            if f0_level >= 2:
                pass
            elif f0_level == 1:
                pass
            else:
                flush = True
        else:
            if f0_level >= 2:
                pass
            else:
                self._buf_list[0] = wave_int16
                self._buf_count = 1
        self._before_level = f0_level
        if flush:
            # 有声から無声に変化した、もしくは、バッファがいっぱいなら
            concat_int16 = np.concatenate(self._buf_list[:self._buf_count])
            self._buf_count = 0
            # mfcc計算
            wave_float = concat_int16.astype(np.float64)
            wave_float2 = wave_float / 32767.0
            mfcc = self._calc_mfcc( wave_float2, frame_rate )
            # byteデータへ変換
            #byte_data = concat_int16.astype(np.int16).tobytes()
            # 次のキューへ
            return f0_level, concat_int16, mfcc
        else:
            return f0_level, None, None

class VectList:
    def __init__(self,num=10):
        self._list:np.ndarray = np.empty((0,0))
        self._maxlength = num
        self._last_idx = -1
        # 平均と標準偏差
        self._mean:np.ndarray = None
        self._std:np.ndarray = None
        self._center:np.ndarray = None
    # 追加する
    def put( self, vector:np.ndarray ):
        if vector is not None:
            if len(self._list)>self._maxlength:
                # 上限を超えたので上書き
                self._last_idx = (self._last_idx+1) % self._maxlength
                self._list[self._last_idx] = vector
            elif len(self._list) >0:
                # 上限以下なので追加
                self._last_idx = len( self._list )
                self._list = np.concatenate( (self._list,vector.reshape((1,-1))), axis=0 )
            else:
                # 初期化
                self._last_idx = 0
                self._list = vector.reshape(1,-1)
            self._mean = None
            self._std = None
            self._center = None
    # 個数
    def length(self):
        return len(self._list)
    def __len__(self):
        return len(self._list)
    
    # 平均と標準偏差を求める
    def _calc(self):
        if len(self._list) == 0:
            return
        if len(self._list) == 1:
            self._center = self._list[0]
            self._radius = 0
            return
        # 平均
        mean = np.mean(self._list, axis=0)
        # 標準偏差
        std = np.std(self._list, axis=0)

        # 各ベクトルが3シグマ以内にあるかどうかをベクトル全体として評価
        std3 = 3 * std
        filtered = np.array([v for v in self._list if np.linalg.norm(v - mean) < np.linalg.norm(std3)])

        # filteredの平均を中心として計算
        center = np.mean(filtered, axis=0)

        # 中心からの距離（半径）のリスト
        delta_list = filtered - center
        radius_list = np.linalg.norm(delta_list, axis=1)

        # 最大半径の計算
        max_radius = np.max(radius_list)

        self._mean = mean
        self._std = std
        self._center = center
        self._radius = max_radius

    def mean(self)->np.ndarray:
        if( self._mean is None ):
            self._calc()
        return self._mean

    def std(self)->np.ndarray:
        if( self._std is None ):
            self._calc()
        return self._std
    
    def center(self) ->np.ndarray:
        if( self._center is None):
            self._calc()
        return self._center

    def is_match( self, vect:np.ndarray ) ->bool:
        center = self.center()
        if center is None or self._radius is None:
            return False
        r = np.linalg.norm( vect - center )
        return r < self._radius

    def min_dist( self, vector ):
        return min( np.linalg.norm( vector- a) for a in self._list) if self._list else sys.float_info.max
    def max( self, vector ):
        return max(BotUtils.cosine_dist( vector, a) for a in self._list) if self._list else 0

SPK_DIM=128
SPK_LEN=5
SPK_NOIZE=0
SPK_USER_OR_NOIZE=1
SPK_USER=2
SPK_USER_OR_AI=3
SPK_AI=4
SPK_NN=15
COLORMAP1=[ '#888888', '#008888', '#ff8888', '#ff88ff', '#8888ff']
COLORMAP2=[ '#000000', '#00ffff', '#ff0000', '#ff00ff', '#0000ff']
class RecognizerEngine:
    def __init__(self):
        self.lang='ja_JP'
        self._callback = None
        self._running=False
        self.device=None
        self.device_info=None
        self.sample_rate=44100
        self.sample_width=2
        self.sample_dtype='int16'
        self.block_size = int(self.sample_rate*0.2)
        self.model=None
        self._wave_queue = queue.Queue()
        self._ats_queue = queue.Queue()
        self._pca_queue = queue.Queue()
        self._in_speek = None
        # Spk分類用
        self._spk_veclist = [ VectList(SPK_NN) for _ in range(SPK_LEN)]
        self._spklen = [ 0 for _ in range(5)]
        self._pca = PCA(n_components=2)
        # mfcc用
        self._mfcc_sz = 100
        self._mfcc_list = [None]*self._mfcc_sz
        self._mfcc_count = 0

    def set_lang(self, lang:str='ja_JP' ):
        self.lang=lang

    def set_mic_device(self,device):
        self.device = device

    def set_vosk_model(self,m):
        self.model = m

    def set_speek(self, text:str=None):
        self._in_speek=text

    def list_devices():
        print(sd.query_devices())

    def start(self):
        try:
            vosk.SetLogLevel(-1)
            self._running = True
            self._pca_thread = Thread( target=self._fn_pca, daemon=True )
            self.att_thread = Thread( target=self._fn_recognize, daemon=True )
            self.vosk_thread = Thread( target=self._fn_vosk, daemon=True )
            self._pca_thread.start()
            self.att_thread.start()
            self.vosk_thread.start()
        except:
            traceback.print_exc()
            self._running = False

    def stop(self):
        self._running=False
        try:
            if self._pca_thread:
                self._pca_thread.join(1.0)
        except:
            traceback.print_exc()
        try:
            if self.vosk_thread:
                self.vosk_thread.join(1.0)
        except:
            traceback.print_exc()
        try:
            if self.att_thread:
                self.att_thread.join(1.0)
        except:
            traceback.print_exc()

    def _fn_callback(self,data):
        if self._callback is not None:
            self._callback(data)
        else:
            print(f"[REG] {data}")

    def _add_spkvect( self, grp, spkvect:np.ndarray ) ->None:
        if spkvect is not None and len(spkvect)==SPK_DIM:
            self._spk_veclist[grp].put( spkvect )
        else:
            print(f"[ERROR] raw_spkvect None or invalid dim")

    def _spk_veclen( self, grp ) ->int:
        return len(self._spk_veclist[grp])

    def _len_spkvect( self, grp ) ->int:
        return self._spklen[grp]

    def _spk_ismatch( self, grp, spkvect:np.ndarray, default:bool=None ) ->bool:
        vect_list:VectList = self._spk_veclist[grp]
        if vect_list is None or len(vect_list)<3:
            return default
        else:
            return vect_list.is_match(spkvect)

    def _spk_update(self, temp_vector:np.ndarray=None) ->None:
        #分類用にベクトルを結合する
        allvec = np.concatenate( [ v._list for v in self._spk_veclist if len(v)>0], axis=0 )
        #分類用にベクトルを結合する
        all_colors = []
        for grp, vect in enumerate(self._spk_veclist):
            if vect:
                color = COLORMAP1[grp]
                all_colors += [color] * (len(vect)-1)
                all_colors.append( COLORMAP2[grp] )
        if temp_vector is not None:
            if len(temp_vector)==128:
                allvec = np.concatenate( [allvec, temp_vector.reshape(1,-1)], axis=1 )
                all_colors.append( '#ffff00' )
            else:
                print(f"[ERROR] raw_spkvect len:{len(temp_vector)}")
        if len(allvec)>2:
            self._pca_queue.put( (allvec, all_colors) )

    def _fn_pca(self):
        try:
            # 処理ループ
            while self._running:
                try:
                    all_vectors:np.ndarray
                    all_vectors, all_colors = self._pca_queue.get(timeout=1.0)
                    if self._pca_queue.qsize()>0:
                        continue
                except:
                    continue
                try:
                    # ベクトルを２次元に投影する
                    print(f"[PCA] start")
                    st = time.time()
                    all_2d = self._pca.fit_transform(all_vectors)
                    for grp in range(5):
                        self._spklen[grp] = len( self._spk_veclist[grp] )
                    ed = time.time()
                    print(f"[PCA] end len:{len(all_vectors)} time:{ed-st}(sec)")
                    self._fn_callback( { 'spk2d':all_2d, 'colors':all_colors } )
                except:
                    traceback.print_exc()
        except:
            pass

    # googleで音声認識
    def _fn_recognize(self):
        try:
            # google recognizerの設定
            self.recognizer = sr.Recognizer()
            NN=100
            partial_text:str = None
            spkvect: np.ndarray = None
            in_speek:str = None
            while self._running:
                segment,partial_text,spkvect, in_speek = self._ats_queue.get()
                if partial_text is None:
                    break
                if partial_text == 'ん':
                    continue
                if segment is None:
                    data = { 'actin': 'partial', 'content': partial_text }
                    self._fn_callback(data)
                    continue
                #------------------------------
                if spkvect is not None:
                    if len(spkvect)!=128:
                        print(f"[ERROR] raw_spkvect len:{len(spkvect)}")

                    if in_speek:
                        if not self._spk_ismatch( SPK_USER, spkvect, False ):
                            self._add_spkvect( SPK_AI, spkvect )
                            if self._spk_veclen( SPK_AI )<10:
                                data = { 'actin': 'partial', 'content': '' }
                                self._fn_callback(data)
                                print( f"[RECG] PreCancel AI<10 in speek {partial_text}")
                                continue
                            if self._spk_ismatch( SPK_AI, False ):
                                data = { 'actin': 'partial', 'content': '' }
                                self._fn_callback(data)
                                print( f"[RECG] PreCancel AI in speek {partial_text}")
                                continue
                        print( f"[RECG] PreCancel Interrupt in speek {partial_text}")
                    else:
                        if self._spk_ismatch( SPK_NOIZE, spkvect ):
                            if not self._spk_ismatch( SPK_USER, spkvect ):
                                data = { 'actin': 'partial', 'content': '' }
                                self._fn_callback(data)
                                print( f"[RECG] PreCandel Noize {partial_text}")
                                continue

                    # xgrp = self._spk_prediction( spkvect )
                    # if xgrp == SPK_AI:
                    #     # AIのほうが近いので、AIとみなす
                    #     data = { 'actin': 'partial', 'content': '' }
                    #     self._fn_callback(data)
                    #     print( f"[RECG] AI cancel {partial_text}")
                    #     continue

                    #------------------------------
                    #if in_speek:
                        #if ai_vects.length()>=3 and user_vects.length()>=3:
                            # AI発話中でデータが揃っている
                            # ai = ai_vects.min_dist( spkvect )
                            # us = user_vects.min_dist( spkvect )
                            # if ai<us:
                            #     # AIのほうが近いので、AIとみなす
                            #     data = { 'actin': 'partial', 'content': '' }
                            #     self._fn_callback(data)
                            #     print( f"[RECG] AI cancel {partial_text}")
                            #     continue
                            # if noize_vects.length()>=3:
                            #     nz = noize_vects.min_dist( spkvect )
                            #     if nz<us:
                            #         # ノイズのほうが近いので、AIとみなす
                            #         data = { 'actin': 'partial', 'content': '' }
                            #         self._fn_callback(data)
                            #         print( f"[RECG] Noize cancel {partial_text}")
                            #         continue
                    #else:
                        # if noize_vects.length()>=3 and user_vects.length()>=3:
                        #     us = user_vects.min_dist( spkvect )
                        #     nz = noize_vects.min_dist( spkvect )
                        #     if nz<us:
                        #         # ノイズのほうが近いので、AIとみなす
                        #         data = { 'actin': 'partial', 'content': '' }
                        #         self._fn_callback(data)
                        #         print( f"[RECG] Noize cancel {partial_text}")
                        #         continue

                #------------------------------
                confidence = 0.0
                actual_result = None
                final_text = None
                try:
                    buf = bytearray()
                    for s in segment:
                        buf += bytearray(s)
                    # rate 44100 width 2 ja_JP
                    # buffer <bytearray, len() = 882000> type(buffer) <class 'bytearray'> WIDTH 2 RATE 44100
                    audio_data = sr.AudioData( buf, int(self.sample_rate*0.8), self.sample_width)
                    lang = self.lang if self.lang else 'ja_JP'
                    for retry in range(1,0,-1):
                        actual_result = self.recognizer.recognize_google(audio_data, language=lang, with_confidence=False, show_all=True )
                        if retry>0 and isinstance(actual_result,list) and len(actual_result)==0:
                            print(f"[RECG] empty result retry {retry}")
                            time.sleep(1.0)
                            continue
                        break
                    if isinstance(actual_result,list) and len(actual_result)==0:
                        print(f"[RECG] empty result {partial_text}")
                        self._fn_callback( { 'action':'abort','content':''} )
                        if len(partial_text)<5:
                            self._add_spkvect( SPK_NOIZE, spkvect )
                            self._spk_update()
                        continue
                    elif isinstance(actual_result, dict) and len(actual_result.get("alternative", []))>0:
                        if "confidence" in actual_result["alternative"]:
                            # return alternative with highest confidence score
                            best_hypothesis = max(actual_result["alternative"], key=lambda alternative: alternative["confidence"])
                        else:
                            # when there is no confidence available, we arbitrarily choose the first hypothesis.
                            best_hypothesis = actual_result["alternative"][0]
                        if "transcript" in best_hypothesis:
                            # https://cloud.google.com/speech-to-text/docs/basics#confidence-values
                            # "Your code should not require the confidence field as it is not guaranteed to be accurate, or even set, in any of the results."
                            confidence = best_hypothesis.get("confidence", 0.5)
                            final_text = best_hypothesis["transcript"]
                            final_len = len(final_text)
                            if final_len<3 or confidence < 0.6:
                                # ほぼノイズでしょう
                                print( f"[RECG] noize {final_text} {confidence}")
                                self._add_spkvect( SPK_NOIZE, spkvect )
                                self._spk_update()
                                continue
                            elif not in_speek:
                                # AIは発声してない
                                if final_len<5:
                                    print( f"[RECG] USER/NOIZE {final_text} {confidence}")
                                    self._add_spkvect( SPK_USER_OR_NOIZE, spkvect )
                                else:
                                    print( f"[RECG] USER {final_text} {confidence}")
                                    self._add_spkvect( SPK_USER, spkvect )
                                self._spk_update()
                            else:
                                # AIは発声中
                                #-------------------------------
                                # 短かったらノイズでしょ
                                if final_len<5:
                                    print( f"[RECG] AI short {final_text}")
                                    self._fn_callback( { 'action':'abort','content':''} )
                                    self._add_spkvect( SPK_USER_OR_NOIZE, spkvect )
                                    self._spk_update()
                                    continue
                                #------------------------------
                                # AIが発声している内容とどれくらい近いか？
                                ai_ngram:Ngram = Ngram(in_speek)
                                recg_ngram:Ngram = Ngram(final_text)
                                sim: float = ai_ngram.similarity(recg_ngram)
                                if sim>0.9:
                                    # AIと判定した
                                    data = { 'actin': 'partial', 'content': '' }
                                    self._fn_callback(data)
                                    print( f"[RECG] AI Ngram {sim} {partial_text}")
                                    self._add_spkvect( SPK_AI, spkvect )
                                    self._spk_update()
                                    continue
                                #------------------------------
                                # AIの発話中でAIのベクトルが貯まるまでは識別しない
                                ai_count = self._len_spkvect(SPK_AI)
                                if ai_count<=3:
                                    print( f"[RECG] AI skip {ai_count}  sim:{sim} text:{final_text} in_speek:{in_speek}")
                                    self._fn_callback( { 'action':'abort','content':''} )
                                    self._add_spkvect( SPK_USER_OR_AI, spkvect )
                                    self._spk_update()
                                    continue
                                #------------------------------
                                # ここまできたら、AI発声中に人間がしゃべったんじゃないか？と判定
                                print( f"[RECG] AI/USER {final_text} {confidence}")
                    else:
                        print(f"[RECG] error response {actual_result}")
                        self._fn_callback( {'action':'error','error': 'invalid response'})

                except sr.exceptions.RequestError as ex:
                    print(f"[RECG] error response {ex}")
                    self._fn_callback( {'action':'error','error': f'{ex}'})
                except Exception as ex:
                    traceback.print_exc()
                    self._fn_callback( {'action':'error','error': f'{ex}'})

                if final_text is not None:
                    self._fn_callback( { 'action':'final','content':final_text} )
                elif partial_text is not None:
                    self._fn_callback( { 'action':'abort','content':final_text} )
        except:
            traceback.print_exc()
        self._running = False
        print(f"[RECG] stop")

    def _fn_wave_callback(self, indata, frames:int, time, status:sd.CallbackFlags):
        """This is called (from a separate thread) for each audio block."""
        try:
            sz:int = self._wave_queue.qsize()
            if status:
                print(status, file=sys.stderr)
            if self._q_full:
                if self._wave_queue.qsize()==0:
                    self._q_full=False
                    self._fn_callback( {'action':'restart'})
            elif self._wave_queue.qsize()<self._q_limit:
                self._wave_queue.put( (bytes(indata), self._in_speek) )
            else:
                self._fn_callback( {'action':'pause'})
                self._q_full=True
        except:
            pass

    def _fn_vosk(self):
        try:
            noize_strs: list[str] = [ 'ん', 'えーっと', 'えっと', 'えっと ん' ]
            #------------------------------------------------------------
            # voskを初期化する
            #------------------------------------------------------------
            self.device_info = sd.query_devices(self.device, "input")
            if self.device_info is None:
                return
            if self.device is None:
                self.device = self.device_info['index']
            default_rate = int(self.device_info["default_samplerate"])
            for r in [ 16000, 24000, default_rate ]:
                try:
                    sd.check_input_settings( device=self.device, samplerate=r)
                    self.sample_rate = r
                    break
                except:
                    pass
            self.sample_width = 2
            self.dtype = 'int16'
            self.block_size = int(self.sample_rate * 0.1) # sample_rateが１秒のブロック数に相当するので 0.2秒のブロックサイズにする

            self._q_limit = 5 * 10
            self._q_full = False

            # voskの設定
            vosk.SetLogLevel(-1)
            if self.model is None:
                self.model = RecognizerEngine.get_vosk_model(lang="ja")
            else:
                self.model = Model(lang=self.model)
            self.vosk: KaldiRecognizer = KaldiRecognizer(self.model, self.sample_rate)
            spkmodel_path = RecognizerEngine.get_vosk_spk_model(self.model)
            if spkmodel_path is not None:
                self.vosk.SetSpkModel( spkmodel_path )
            #
            Splitter:VoiceSeg = VoiceSeg()
            #------------------------------------------------------------
            # 検出ループ
            #------------------------------------------------------------
            with sd.RawInputStream(samplerate=self.sample_rate, blocksize = self.block_size, device=self.device, dtype=self.dtype, channels=1, callback=self._fn_wave_callback):
                framebuf = []
                before_notify=""
                before_in_speek=None
                in_speek:str = None
                partial_count:int = 0
                noize_count:int = 0
                vflg:bool=False
                # 処理ループ
                while self._running:
                    # get from queue
                    try:
                        frame_seg_bytes, frame_in_speek = self._wave_queue.get(timeout=1.0)
                    except:
                        continue
                    frame_seg_int16 = np.frombuffer( frame_seg_bytes, dtype=np.int16)
                    f0_lv, wave_int16, mfcc = Splitter.put( frame_seg_int16, self.sample_rate, vflg )
                    if wave_int16 is None:
                        continue
                    frame = wave_int16.tobytes()
                    # バッファに蓄積
                    framebuf.append(frame)
                    # AIが発声した内容を記録
                    if frame_in_speek:
                        if in_speek is None:
                            in_speek = frame_in_speek
                            before_in_speek = frame_in_speek
                        elif before_in_speek != frame_in_speek and not in_speek.endswith(frame_in_speek):
                            in_speek += frame_in_speek
                    else:
                        before_in_speek = ""
                    #
                    # MFCC
                    self._mfcc_list[self._mfcc_count] = mfcc
                    self._mfcc_count = (self._mfcc_count+1) % self._mfcc_sz
                    #
                    send=None
                    send_text=None
                    spkvect=None
                    if self.vosk.AcceptWaveform(frame) or f0_lv<0:
                        res_text:str = self.vosk.Result()
                        res_obj = json.loads( res_text )
                        rawtxt:str = BotUtils.NoneToDefault(res_obj.get('text'))
                        rawlen:int = len(rawtxt)
                        nz:bool = rawtxt in noize_strs
                        txt:str = rawtxt
                        tmp_spkvect = res_obj.get('spk')
                        if rawlen <= 1 or nz:
                            noize_count += 1
                            if noize_count<2:
                                print( f"[VOSK] Noize count:{noize_count} {rawtxt}")
                            else:
                                print( f"[VOSK] Noize count:{noize_count} {rawtxt} RESET!!")
                                noize_count = 0
                                self.vosk.Reset()
                            if before_notify:
                                self._ats_queue.put( (None,'',None,None) )
                            txt = ''
                            framebuf.clear()
                        else:
                            send = framebuf
                            framebuf=[]
                            send_text = in_speek
                            spkvect = tmp_spkvect
                            if spkvect is not None:
                                print( f"[VOSK] final   {txt} // {send_text}")
                                npvect = np.array(spkvect)
                                self._ats_queue.put( (send,txt,npvect, send_text) )
                            else:
                                print( f"[VOSK] json {res_text}")
                                print( f"[VOSK] no spkvect {txt} // {send_text}")
                                if before_notify:
                                    self._ats_queue.put( (None,'',None,None) )
                        vflg = False 
                        before_notify = ""
                        in_speek = None
                        before_in_speek = None
                        partial_count = 0
                    else:
                        partial_count += 1
                        res_obj = json.loads( self.vosk.PartialResult() )
                        txt:str = BotUtils.NoneToDefault(res_obj.get('partial'))
                        if len(txt)>0:
                            vflg=True
                        if txt != before_notify:
                            print( f"[VOSK] partial {txt} // {in_speek}")
                            before_notify = txt
                            self._ats_queue.put( (None,txt,None,None) )

                self._ats_queue.put( (None,None,None,None) )

        except Exception as e:
            traceback.print_exc()
        self._running=False
        self._ats_queue.put( (None,None,None,None) )

    @staticmethod
    def get_vosk_model( lang:str='ja' ) ->Model:
        for directory in vosk.MODEL_DIRS:
            if directory is None or not Path(directory).exists():
                continue
            model_file_list = os.listdir(directory)
            model_file = [model for model in model_file_list if re.match(rf"vosk-model-{lang}", model)]
            if model_file != []:
                return Model(str(Path(directory, model_file[0])))
        for directory in vosk.MODEL_DIRS:
            if directory is None or not Path(directory).exists():
                continue
            model_file_list = os.listdir(directory)
            model_file = [model for model in model_file_list if re.match(rf"vosk-model-small-{lang}", model)]
            if model_file != []:
                return Model(str(Path(directory, model_file[0])))
        m:Model = Model(lang=lang)
        return m

    @staticmethod
    def get_vosk_spk_model(m:Model=None):
        for directory in vosk.MODEL_DIRS:
            if directory is None or not Path(directory).exists():
                continue
            model_file_list = os.listdir(directory)
            model_file = [model for model in model_file_list if re.match(r"vosk-model-spk-", model)]
            if model_file != []:
                return SpkModel(str(Path(directory, model_file[0])))
            
        p:str = m.get_model_path('vosk-model-spk-0.4',None) if m is not None else None
        if p is not None:
            return SpkModel( p )
        return None
    
    # https://qiita.com/adumaru0828/items/a95de3a0fbfe54f51953

class BotUtils:

    @staticmethod
    def load_api_keys():
        pre = os.getenv('OPENAI_API_KEY')
        Utils.load_env( ".miyasaburo.conf" )
        after = os.getenv('OPENAI_API_KEY')
        if after is not None and pre != after:
            logger.info("UPDATE OPENAI_API_KEY")
            openai.api_key=after

    @staticmethod
    def formatted_current_datetime():
        # オペレーティングシステムのタイムゾーンを取得
        system_timezone = time.tzname[0]
        # 現在のローカル時刻を取得
        current_time = time.localtime()
        # 日時を指定されたフォーマットで表示
        formatted = time.strftime(f"%a %b %d %H:%M {system_timezone} %Y", current_time)
        return formatted

    @staticmethod
    def parse_response( inp:dict, text:str, start:int=0, end:int=-1, fill:bool=False ):
        # 位置調整
        if text is None:
            return None
        text_len=BotUtils.length(text)
        if end<0 or text_len<end:
            end=text_len
        # keyの位置を検索
        index_list = [(BotUtils.find_key(key, text, start, end), key) for key in inp.keys()]
        # 見つかった位置だけにする
        index_list = [(i, k) for i,k in index_list if i>=0]
        index_len:int = len(index_list)
        # チェック
        if index_len==0 or ( fill and index_len<len(inp) ):
            return None
        # リストをインデックスでソートする
        index_list.sort(key=lambda x: x[0])
        index_list.append((end,""))
        # 分割
        out:dict = {}
        for i in range(0,index_len):
            key:str = index_list[i][1]
            st:int = index_list[i][0] + len(key)
            ed:int = index_list[i+1][0]
            while st<ed and BotUtils.is_sep(text[st]):
                st+=1
            while st<ed and BotUtils.is_sep(text[ed-1]):
                ed-=1
            val = inp[key]
            if isinstance(val,dict):
                val = BotUtils.parse_response( val, text, st, ed, fill=fill)
                if val is not None:
                    out[key] = val
                elif fill:
                    return None
            else:
                out[key] = text[st:ed]
        return out

    @staticmethod
    def update_dict( inp:dict, out:dict ):
        if inp is None:
            return
        if out is None:
            return inp
        for key in inp.keys():
            inp_val = inp[key]
            if isinstance(inp_val,dict):
                out_val = out.get(key)
                if out_val is None or not isinstance(out_val,dict):
                    out[key]=inp_val
                else:
                    BotUtils.update_dict(inp_val,out_val)
            else:
                out[key]=inp_val

    @staticmethod
    def length( value ) -> int:
        if hasattr(value,'__len__'):
            return len(value)
        return -1

    @staticmethod
    def eq( valueA, valueB ) -> bool:
        if type(valueA) != type(valueB):
            return False
        l = BotUtils.length(valueA)
        if l != BotUtils.length(valueB):
            return False
        if isinstance(valueA,dict):
            for key in valueA.keys():
                if key not in valueB:
                    return False
                if not BotUtils.eq( valueA[key], valueB[key] ):
                    return False
        elif isinstance(valueA,list):
            for idx in range(0,l):
                if not BotUtils.eq( valueA[idx], valueB[idx] ):
                    return False
        else:
            if valueA != valueB:
                return False
        return True

    @staticmethod
    def find_key( key:str, text:str, st:int=0, ed:int=None ):
        if ed is None:
            ed=len(key)
        while st<ed:
            idx:int=text.find(key,st)
            if idx<st:
                return -1
            if st==idx or BotUtils.is_sep(text[idx-1]):
                j=idx+len(key)
                if ed<j:
                    return -1
                if j==ed or BotUtils.is_sep(text[j]):
                    return idx
            st+=1
        return -1

    @staticmethod
    def is_sep( cc:str ):
        return cc and " \r\n#.-:".find(cc)>=0
    @staticmethod
    def is_spc( cc:str ):
        return cc and " \r\n".find(cc)>=0
    
    @staticmethod
    def to_format( fmt:dict, *, indent="", mark="#" ) -> str:
        tst:str=""
        for key in fmt.keys():
            if len(tst)>0:
                tst = tst +"\n"
            tst = tst + indent + mark + " " + key + "\n"
            val = fmt[key]
            if isinstance(val,dict):
                val = BotUtils.to_prompt( val, indent=indent+"  ", mark=mark+"#" )
            elif isinstance(val,str) and len(val.strip())>0:
                val = "{" + val + "}"
            else:
                val = "..."
            tst = tst + indent + "    " + val
        return tst

    @staticmethod
    def to_prompt( fmt:dict, *, indent="", mark="#" ) -> str:
        tst:str=""
        for key in fmt.keys():
            if len(tst)>0:
                tst = tst +"\n"
            tst = tst + indent + mark + " " + key + "\n"
            val = fmt[key]
            if isinstance(val,dict):
                val = BotUtils.to_prompt( val, indent=indent+"  ", mark=mark+"#" )
            tst = tst + indent + "    " + val
        return tst

    @staticmethod
    def get_location() -> dict:
        try:
            geo_request_url = 'https://get.geojs.io/v1/ip/geo.json'
            data = requests.get(geo_request_url).json()
            # {'organization': 'AS17511 OPTAGE Inc.', 'organization_name': 'OPTAGE Inc.', 'area_code': '0', 'ip': '121.86.210.40', 'country_code': 'JP', 'country_code3': 'JPN', 'continent_code': 'AS', 'asn': 17511, 'region': 'Ōsaka', 'city': 'Otemae', 'longitude': '135.5236', 'accuracy': 10, 'latitude': '34.6837', 'timezone': 'Asia/Tokyo', 'country': 'Japan'}
            # print(data['latitude']) # 34.6837
            # print(data['longitude']) # 135.5236
            # print(data['country']) # Japan
            # print(data['region']) # Osaka
            # print(data['city'])   # Otemae
            # print(data['ip'])     # 121.86.210.40
            return data
        except Exception as ex:
            pass
        return None

    @staticmethod
    def token_count( input: str ) -> int:
        encoding: Encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")
        tokens = encoding.encode(input)
        count = len(tokens)
        return count

    @staticmethod
    def to_embedding( input ):
        client:OpenAI = get_client()
        res:CreateEmbeddingResponse = client.embeddings.create(input=input, model="text-embedding-ada-002")
        return [data.embedding for data in res.data ]

    @staticmethod
    def cosine_similarity(a, b):
        return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

    @staticmethod
    def cosine_dist(x, y) ->float:
        if x is None or y is None:
            return 0.0
        nx = np.array(x)
        ny = np.array(y)
        return 1 - np.dot(nx, ny) / np.linalg.norm(nx) / np.linalg.norm(ny)


    @staticmethod
    def get_queue( queue:queue.Queue ):
        try:
            return queue.get_nowait()
        except:
            pass
        return None

    @staticmethod
    def to_str( obj ) -> str:
        if isinstance(obj,list):
            return "\n".join( [BotUtils.to_str(s) for s in obj] )
        if isinstance(obj,dict):
            return json.dumps( obj, ensure_ascii=False, indent=4 )
        return str(obj)

    @staticmethod
    def join_str( a:str=None, b:str=None, *,sep:str="\n") -> str:
        ret:str = ""
        if BotUtils.is_empty(a):
            if BotUtils.is_empty(b):
                return ""
            else:
                return str(b)
        else:
            if BotUtils.is_empty(b):
                return str(a)
            else:
                return str(a) + str(sep) + str(b)

    @staticmethod
    def str_strip( value:str ) -> str:
        if value is None:
            return None
        else:
            return str(value).strip()

    @staticmethod
    def str_strip_or_default( value:str, default:str=None ) -> str:
        if value is None:
            return default
        value = str(value).strip()
        if len(value)==0:
            return default
        return value

    @staticmethod
    def is_empty( value ) -> bool:
        return value is None or len(str(value).strip())<=0

    @staticmethod
    def strip_message( mesg:str ) -> str:
        while True:
            if mesg is None or len(mesg)==0:
                return ""
            mesg = mesg.strip()
            cc = mesg[0]
            if cc == "「" or cc == "(" or cc=="{" or cc=="[":
                mesg = mesg[1:]
                continue
            cc = mesg[-1]
            if cc == "「" or cc == "(" or cc=="{" or cc=="[":
                mesg = mesg[:-2]
                continue
            return mesg
    @staticmethod
    def strip_messageN( mesg:str ) -> str:
        while True:
            if mesg is None or len(mesg)==0:
                return ""
            mesg = mesg.strip()
            cc = mesg[0]
            if "0"<=cc and cc<="9" or cc=="." or cc=="-":
                mesg = mesg[1:]
                continue
            if cc == "「" or cc == "(" or cc=="{" or cc=="[":
                mesg = mesg[1:]
                continue
            cc = mesg[-1]
            if cc == "「" or cc == "(" or cc=="{" or cc=="[":
                mesg = mesg[:-2]
                continue
            return mesg
    @staticmethod
    def get_first_line( text:str ) -> str:
        if text is None or len(text)==0:
            return ""
        idx:str = text.find("\n")
        if idx<0:
            return text
        else:
            return text[:idx]

    @staticmethod
    def split_string(text:str) -> list[str]:
        # 文字列を改行で分割
        lines = text.split("\n")
        # 句読点で分割するための正規表現パターン
        pattern = r"(?<=[。．！？])"
        # 分割結果を格納するリスト
        result = []
        # 各行を句読点で分割し、結果をリストに追加
        for line in lines:
            sentences = re.split(pattern, line)
            result.extend(sentences)
        # 空の要素を削除して結果を返す
        return list(filter(None, result))

    # 文字列の左側の空白を数える
    @staticmethod
    def count_left_space( value:str ) -> int:
        if value is None:
            return 0
        n:int = 0
        for cc in value:
            if cc==" ":
                n+=1
            else:
                break
        return n

    # 複数行文字列のインデント
    @staticmethod
    def str_indent( value:str ) -> str:
        if( value is None ):
            return []
        lines:list[str] = value.split('\n')
        while len(lines)>0:
            if lines[0].strip() == "":
                lines.pop(0)
            else:
                break
        while len(lines)>0:
            if lines[-1].strip() == "":
                lines.pop()
            else:
                break
        left_spc:int = 99999
        for l in lines:
            n:int = BotUtils.count_left_space(l)
            if n<left_spc:
                left_spc=n
        return "\n".join( [ l[left_spc:] for l in lines] )

    @staticmethod
    def int_or_str(text):
        """Helper function for argument parsing."""
        try:
            return int(text)
        except ValueError:
            return text

    @staticmethod
    def NoneToDefault( value, *,default="" ) ->str:
        if value is not None:
            svalue = str(value)
            if len(svalue)>0:
                return svalue
        return default

    @staticmethod
    def decode_utf8( text:str ) ->str:
        try:
            # 文字列をバイト列に変換
            byte_data = bytes(text, 'latin1')
            # UTF-8でデコード
            return byte_data.decode('utf-8')
        except:
            return text

    @staticmethod
    def find_first_responsive_host(hostname_list:list[str], port:int=None, timeout:float=1.0) ->str:
        uniq:set = set()
        for sv in hostname_list:
            url = f"{sv}"
            if not url.startswith("http://") and not url.startswith("https://"):
                url = "http://"+url
            if port is not None:
                url += f":{port}"
            if url not in uniq:
                uniq.add(url)
                try:
                    response = requests.get(url, timeout=timeout)
                    if response.status_code == 200 or response.status_code == 404:
                        return url
                except (requests.ConnectionError, requests.Timeout):
                    continue

        return None

class Ngram:
    def __init__( self, text:str, N:int=2 ):
        self._text = text
        strip_text = Ngram._ngrams_preprocess_txt(text)
        N_gram_vec={}
        for i in range(len(strip_text)-N+1):
            t = strip_text[i:i+N]
            if t in N_gram_vec.keys():
                N_gram_vec[t]+=1
            else:
                N_gram_vec[t]=1
        self._vect = N_gram_vec

    def similarity( self, ngram2:'Ngram' ) ->float:
        return Ngram.cosine_similarity( self, ngram2 )

    @staticmethod
    def _ngrams_preprocess_txt( text:str ):
        # 句読点の除去
        text = re.sub(r'[、。？?！! 　]', '', text)
        # 英数字を半角に変換
        text = unicodedata.normalize("NFKC", text)
        return text

    @staticmethod
    def cosine_similarity( ngram1:'Ngram', ngram2:'Ngram' ) ->float:
        vec1:dict = ngram1._vect
        vec2:dict = ngram2._vect
        # ベクトル間のコサイン類似度を計算
        intersection = set(vec1.keys()) & set(vec2.keys())
        numerator = sum([vec1[x] * vec2[x] for x in intersection])

        norm1 = math.sqrt( sum([vec1[x]**2 for x in vec1.keys()]) )
        norm2 = math.sqrt( sum([vec2[x]**2 for x in vec2.keys()]) )
        denominator = norm1 * norm2

        if not denominator:
            return 0.0
        else:
            return float(numerator) / denominator

def test():
    a = BotUtils.to_embedding( 'aaaa' )
    BotUtils.eq(
         { 'a': '1', 'b': '2'},
         { 'a': '1', 'b': '2'}
    )
    BotUtils.get_location()
    text:str = """
    aa:
      bb
    III:
      JJJ: jjjj
      KKK: kkkk
    #cc
     dd
    ee"""
    fmt:dict = {
        "aa": "",
        "cc": "",
        "ee": "",
        "III": {
            "JJJ": "",
            "KKK": "",
        }
    }
    out:dict = BotUtils.parse_response(fmt,text)
    print(out)

    bot:BotCore = BotCore()

    res = bot.Completion( "元気？")
    print( res )

def test2():
    txt_list = [ "ああああ", "あああ\nいいいい", "ああああ\n```こーど\nブロック```\nだよん"]
    for txt in txt_list:
        lines = TtsEngine.split_talk_text( txt )
        print( lines )

if __name__ == "__main__":
    test2()
