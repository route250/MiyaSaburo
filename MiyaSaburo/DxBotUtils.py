import sys,os,re,time,json,re
import requests
import traceback
import threading
import datetime
from zoneinfo import ZoneInfo
import openai
import tiktoken
from tiktoken.core import Encoding
from libs.utils import Utils
import logging
from logging.handlers import TimedRotatingFileHandler
import queue
import threading

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

if __name__ == "__main__":
    pre = os.getenv('OPENAI_API_KEY')
    Utils.load_env( ".miyasaburo.conf" )
    after = os.getenv('OPENAI_API_KEY')
    if after is not None and pre != after:
        logger.info("UPDATE OPENAI_API_KEY")
        openai.api_key=after

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

class BotCore:

    def __init__(self):
        self.lock = threading.Lock()
        self.prompt_tokens: int = 0
        self.completion_tokens: int = 0
        self.total_tokens:int  = 0
        self.last_talk_time: float = 0

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

    @staticmethod
    def token_count( input: str ) -> int:
        encoding: Encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")
        tokens = encoding.encode(input)
        count = len(tokens)
        return count

    def Completion(self, prompt, *, max_tokens=None, temperature=0 ) -> str:
        try:
            #print( f"openai.api_key={openai.api_key}")
            #print( f"OPENAI_API_KEY={os.getenv('OPENAI_API_KEY')}")
            if openai.api_key is None:
                openai.api_key=os.getenv('OPENAI_API_KEY')
            in_count = BotCore.token_count( prompt )
            if max_tokens is None:
                max_tokens = 4096
            u = max_tokens - in_count - 50
            for retry in range(2,-1,-1):
                try:
                    response = openai.Completion.create(
                            model="gpt-3.5-turbo-instruct",
                            temperature = temperature, max_tokens=u,
                            prompt=prompt,
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
                except ConnectionRefusedError as ex:
                    if retry>0:
                        print( f"{ex}" )
                        time.sleep(5)
                    else:
                        raise ex

            self.token_usage( response )           
            if response is None or response.choices is None or len(response.choices)==0:
                print( f"Error:invalid response from openai\n{response}")
                return None
            content = response.choices[0].text.strip()
            if length(content)==0:
                print( f"Error:invalid response from openai\n{response}")
                return None
            return content
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

    def ChatCompletion( self, mesg_list, temperature=0 ):
        try:
            api_logger.debug( "request" + "\n" + json.dumps( mesg_list, indent=2, ensure_ascii=False) )

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
                            request_timeout=30
                        )
                    api_logger.debug( "response" + "\n" + json.dumps( response, indent=2, ensure_ascii=False) )
                    break
                except openai.error.Timeout as ex:
                    api_logger.error( f"{ex}" )
                    if retry>0:
                        logger.error( f"ChatCompletion {ex}" )
                        time.sleep(5)
                    else:
                        raise ex
                except openai.error.ServiceUnavailableError as ex:
                    api_logger.error( f"{ex}" )
                    if retry>0:
                        logger.error( f"ChatCompletion {ex}" )
                        time.sleep(5)
                    else:
                        raise ex
                
            if response is None or response.choices is None or len(response.choices)==0:
                logger.error( f"invalid response from openai\n{response}")
                return None

            content = response.choices[0]["message"]["content"].strip()
        except openai.error.AuthenticationError as ex:
            api_logger.error( f"{ex}" )
            logger.error( f"ChatCompletion {ex}" )
            return None
        except openai.error.InvalidRequestError as ex:
            api_logger.error( f"{ex}" )
            logger.error( f"ChatCompletion {ex}" )
            return None
        except openai.error.ServiceUnavailableError as ex:
            api_logger.error( f"{ex}" )
            logger.error( f"ChatCompletion {ex}" )
            return None
        except Exception as ex:
            api_logger.exception( f"%s", ex )
            logger.exception( f"%s", ex )
            return None

        return content

class BotUtils:

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
        text_len=len(text)
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

    def get_location():
        try:
            geo_request_url = 'https://get.geojs.io/v1/ip/geo.json'
            data = requests.get(geo_request_url).json()
            print(data)
            print(data['latitude'])
            print(data['longitude'])
            print(data['country'])
            print(data['region'])
            print(data['city'])
        except Exception as ex:
            pass

def test():
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