import sys,os,re,time,json,re,copy
import numpy as np
import requests
from requests.adapters import HTTPAdapter
import traceback
import threading
from concurrent.futures import ThreadPoolExecutor, Future
import datetime
from zoneinfo import ZoneInfo
import httpx
import openai
from openai import OpenAI
from openai.types import Completion, CompletionChoice, CompletionUsage
from openai.types import CreateEmbeddingResponse, Embedding
import tiktoken
from tiktoken.core import Encoding
from libs.utils import Utils
import logging
from logging.handlers import TimedRotatingFileHandler
import queue
import threading

from gtts import gTTS
from io import BytesIO
import pygame

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
loghdr.setFormatter( logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
loghdr.setLevel(logging.DEBUG)
conhdr = logging.StreamHandler()
conhdr.setFormatter( logging.Formatter("%(asctime)s %(message)s"))
conhdr.setLevel(logging.INFO)
logger.addHandler(loghdr)
logger.addHandler(conhdr)
api_logger = logging.getLogger("api")
api_logger.setLevel(logging.DEBUG)
loghdr = TimedRotatingFileHandler('logs/api.log', when='midnight', backupCount=7)
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

    def update_info( self, data:dict ) -> None:
        BotUtils.update_dict( data, self.info_data )
        if not self.info_data == self._before_info_data:
            self._before_info_data = copy.deepcopy( self.info_data )
            if self.info_callback is not None:
                self.info_callback( self.info_data )

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


    def ChatCompletion( self, mesg_list:list[dict], temperature=0, stop=["\n", "。", "？", "！"] ):
        content = None
        try:
            api_logger.debug( "request" + "\n" + json.dumps( mesg_list, indent=2, ensure_ascii=False) )
            self.notify_log( mesg_list )

            client:OpenAI = get_client()
            for retry in range(2,-1,-1):
                try:
                    response = client.chat.completions.create(
                            model="gpt-3.5-turbo",
                            temperature = temperature,
                            messages=mesg_list,
                        )
#                            request_timeout=(self.connect_timeout,self.read_timeout)
                    api_logger.debug( "response" + "\n" + response.model_dump_json(indent=2) )
                    break
                except (openai.APITimeoutError,openai.RateLimitError,openai.InternalServerError,openai.APIConnectionError,ConnectionRefusedError) as ex:
                    api_logger.error( f"{ex}" )
                    if retry>0:
                        logger.error( f"ChatCompletion {ex}" )
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
                content = response.choices[0].message.content.strip()

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
        return content

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

class TalkEngine:
    VoiceList = [
        ( "gTTS[ja_JP]", -1, 'ja_JP' ),
        ( "gTTS[en_US]", -1, 'en_US' ),
        ( "gTTS[en_GB]", -1, 'en_GB' ),
        ( "gTTS[fr_FR]", -1, 'fr_FR' ),
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
        ( "OpenAI:alloy[ja_JP]", 1001, 'ja_JP' ),
        ( "OpenAI:echo[ja_JP]", 1002, 'ja_JP' ),
        ( "OpenAI:fable[ja_JP]", 1003, 'ja_JP' ),
        ( "OpenAI:onyx[ja_JP]", 1004, 'ja_JP' ),
        ( "OpenAI:nova[ja_JP]", 1005, 'ja_JP' ),
        ( "OpenAI:shimmer[ja_JP]", 1006, 'ja_JP' ),
    ]

    @staticmethod
    def id_to_name( idx:int ) -> str:
        return next((voice for voice in TalkEngine.VoiceList if voice[1] == idx), "???")

    def __init__(self, *, submit_task = None, talk_callback = None ):
        self.lock: threading.Lock = threading.Lock()
        self._running_future:Future = None
        self._running_future2:Future = None
        self._talk_id: int = 0
        self.wave_queue:queue.Queue = queue.Queue()
        self.play_queue:queue.Queue = queue.Queue()
        self.speaker = 1005 #3
        self.submit_call = submit_task
        self.start_call = talk_callback
        self.pygame_init:bool = False
        self._disable_voicevox: float = 0.0
        self._disable_gtts: float = 0.0

    def cancel(self):
        self._talk_id += 1

    def add_talk(self, full_text:str, emotion:int = 0 ) -> None:
        talk_id:int = self._talk_id
        for text in TalkEngine.split_string(full_text):
            self.wave_queue.put( (talk_id, text, emotion ) )
        with self.lock:
            if self._running_future is None:
                self._running_future = self.submit_call(self.run_text_to_audio)
    
    def run_text_to_audio(self)->None:
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
                    audio_bytes, model = self._text_to_audio( text, emotion )
                    self._add_audio( talk_id,text,emotion,audio_bytes,model )
            except Exception as ex:
                traceback.print_exc()

    def _add_audio( self, talk_id:int, text:str, emotion:int, audio_bytes: bytes, model:str=None ) -> None:
        self.play_queue.put( (talk_id,text,emotion,audio_bytes,model) )
        with self.lock:
            if self._running_future2 is None:
                self._running_future2 = self.submit_call(self.run_talk)

    def _text_to_audio_by_voicevox(self, text: str, emotion:int = 0, lang='ja') -> bytes:
        if self._disable_voicevox>0 and (time.time()-self._disable_voicevox)<180.0:
            return None,None
        try:
            self._disable_voicevox = 0
            sv_host: str = os.getenv('VOICEVOX_HOST','127.0.0.1')
            sv_port: str = os.getenv('VOICEVOX_PORT','50021')
            timeout = (5.0,180.0)
            params = {'text': text, 'speaker': self.speaker, 'timeout': timeout }
            s = requests.Session()
            s.mount(f'http://{sv_host}:{sv_port}/audio_query', HTTPAdapter(max_retries=1))
            res1 : requests.Response = requests.post( f'http://{sv_host}:{sv_port}/audio_query', params=params)

            params = {'speaker': self.speaker, 'timeout': timeout }
            headers = {'content-type': 'application/json'}
            res = requests.post(
                f'http://{sv_host}:{sv_port}/synthesis',
                data=res1.content,
                params=params,
                headers=headers
            )
            model:str = TalkEngine.id_to_name(self.speaker)
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

    def _text_to_audio_by_gtts(self, text: str, emotion:int = 0, lang='ja') -> bytes:
        if self._disable_gtts>0 and (time.time()-self._disable_gtts)<180.0:
            return None,None
        try:
            self._disable_gtts = 0
            tts = gTTS(text=text, lang=lang,lang_check=False )
            with BytesIO() as buffer:
                tts.write_to_fp(buffer)
                wave:bytes = buffer.getvalue()
                del tts
                return wave,f"gTTS[{lang}]"
        except requests.exceptions.ConnectTimeout as ex:
            print( f"[gTTS] timeout")
        except Exception as ex:
            print( f"[gTTS] {ex}")
            traceback.print_exc()
        self._disable_gtts = time.time()
        return None,None

    def _text_to_audio_by_openai(self, text: str, emotion:int = 0, lang='ja') -> bytes:
        if self._disable_gtts>0 and (time.time()-self._disable_gtts)<180.0:
            return None,None
        try:
            self._disable_gtts = 0
            client:OpenAI = get_client()
            response:openai._base_client.HttpxBinaryResponseContent = client.audio.speech.create(
                model="tts-1",
                voice="alloy",
                response_format="mp3",
                input=text
            )
            return response.content,"OpenAI"
        except requests.exceptions.ConnectTimeout as ex:
            print( f"[gTTS] timeout")
        except Exception as ex:
            print( f"[gTTS] {ex}")
            traceback.print_exc()
        self._disable_gtts = time.time()
        return None,None

    def _text_to_audio( self, text: str, emotion:int = 0, lang='ja' ) -> bytes:
        wave: bytes = None
        model:str = None
        if self.speaker>=1000:
            wave, model = self._text_to_audio_by_openai( text, emotion, lang=lang )
        elif self.speaker>=0 and lang=='ja':
            wave, model = self._text_to_audio_by_voicevox( text, emotion, lang=lang )
        if wave is None:
            wave, model = self._text_to_audio_by_gtts( text, emotion, lang=lang )
        return wave,model
        
    def run_talk(self)->None:
        start:bool = False
        while True:
            talk_id:int = -1
            text:str = None
            emotion: int = 0
            audio:bytes = None
            model:str = None
            with self.lock:
                try:
                    talk_id, text, emotion, audio, model = self.play_queue.get_nowait()
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
                        pygame.mixer.music.play(1)
                    if self.start_call is not None:
                        self.start_call( text, emotion, model )
                    if audio is not None:
                        while pygame.mixer.music.get_busy():
                            if talk_id != self._talk_id:
                                pygame.mixer.music.stop()
                                break
                            time.sleep(0.2)
                    
            except Exception as ex:
                traceback.print_exc()

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

if __name__ == "__main__":
    test()