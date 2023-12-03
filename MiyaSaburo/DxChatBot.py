import os,sys,threading
from enum import Enum
import time
import json
import traceback
import concurrent.futures
import queue
from queue import Queue
from concurrent.futures import ThreadPoolExecutor, Future
from DxBotUtils import BotCore, BotUtils, RecognizerEngine, TtsEngine
from DxBotUI import debug_ui

from openai.types.chat.completion_create_params import ResponseFormat

class ChatState(Enum):
    Init = 0        # 初期状態
    InitBusy = 1        # 初期状態
    InTalkReady = 2      # 短期間に会話がある
    InTalkBusy = 3
    ShortBreakBusy = 4
    ShortBreakReady = 5      # ちょっと間があいた
    LongBreakBusy = 6
    LongBreakReady = 7      # ちょっと間があいた

class ChatMessage:

    ASSISTANT="assistant"
    USER="user"
    SYSTEM="system"
    AI="AI"

    def __init__( self, role:str, message:str, *, json:dict=None, templeture:float=None, keep:bool=True, tm:float=None ):
        self.tm:float = tm if tm is not None and tm>0 else time.time()
        self.role:str =role
        self.message:str =message
        self.keep:bool = keep
        self.templeture:float = templeture
        self.json:dict =json

    def to_prompt(self, *, assistant:str=None, user:str=None):
        r:str = self.role
        if r == ChatMessage.ASSISTANT and assistant is not None:
            r=assistant
        if r == ChatMessage.USER and user is not None:
            r=user
        return f"{r}: {self.message}"

    def to_dict(self):
        return ChatMessage.create_dict( self.role, self.message )

    @staticmethod
    def list_to_prompt( messages:list, *, assistant:str=None, user:str=None ):
        return "\n".join( [m.to_prompt(assistant=assistant,user=user) for m in messages if m is not None and isinstance(m,ChatMessage) ] )

    @staticmethod
    def create_dict( role:str, message:str ) -> dict:
        return { 'role':role, 'content': message }

class DxChatBot(BotCore):
    
    def __init__(self, *, executor=None):
        super().__init__()
        # ステータス
        self.chatstate:ChatState = ChatState.Init
        self.api_mode:bool = False
        self.api_mode = self.set_api_mode(True)
        # チャットメッセージ
        self.mesg_list:list[ChatMessage]=[]
        self.next_message:ChatMessage = None
        self.last_user_message_time:float = 0
        # UIへのコールバック
        self._chat_callback = None
        self._recg_callback = None
        self._plot_callback = None
        # スレッド
        self.executor:ThreadPoolExecutor = executor if executor is not None else ThreadPoolExecutor(max_workers=4)
        self.futures:list[Future] = []
        # タイマー
        self._tm_timer: threading.Timer = None
        self._tm_last_action: float = 0
        self._tm_count:int = 0
        self._tm_future:Future = None
        self._tm_queue:Queue = Queue()
        # イベント通知
        self._event_callback = []
        # スピーチエンジン
        self.tts: TtsEngine = None
        # 音声認識エンジン
        self.att: RecognizerEngine = None

    def start(self)-> None:
        with self.lock:
            if self._tm_timer is None:
                self.update_info( {'stat': self.chatstate.name } )
                self._tm_timer = threading.Timer( 1.0, lambda: self._timer_event2( time.time() ))
                self._tm_timer.start()

    def stop(self) ->None:
        self.tts_cancel()
        with self.lock:
            try:
                if self._tm_timer is not None:
                    self._tm_timer.cancel()
            except:
                pass

    def _timer_event2(self,now) ->None:
        m1:float = 0.5 # 0.5
        m2:float = 1.0 # 3.0
        m3:float = 1.0 # 15.0
        live:bool = True
        try:
            with self.lock:
                limit:float = 0
                tm:float = now - self._tm_last_action
                try:
                    if self._tm_future is not None:
                        return
                    # ステータス修正
                    before: ChatState = self.chatstate
                    if before == ChatState.Init:
                        self.chatstate = ChatState.InitBusy
                    elif before == ChatState.InTalkReady:
                        limit = m1 * 60.0
                        if tm>limit:
                            self._tm_count += 1
                            if self._tm_count<=3:
                                self.chatstate = ChatState.InTalkBusy
                            else:
                                self._tm_count = 1
                                self.chatstate = ChatState.ShortBreakBusy
                    elif before == ChatState.ShortBreakReady:
                        limit = m2*60.0
                        if tm>limit:
                            self._tm_count = 1
                            self.chatstate = ChatState.LongBreakBusy
                    elif before == ChatState.LongBreakReady:
                        limit = m3*60.0
                        if tm>limit:
                            self.chatstate = ChatState.LongBreakBusy
                    # 処理起動
                    if before != self.chatstate:
                        self._tm_future = self.executor.submit( self._timer_event_task, before, self._tm_count, self.chatstate )
                finally:
                    # タイマー再起動
                    try:
                        self._tm_timer = threading.Timer( 1.0, lambda: self._timer_event2( time.time() ))
                        self._tm_timer.start()
                        live = True
                    except:
                        live = False
        except:
            pass
        finally:
            if live:
                xtm = max( limit -tm, 0 )
                self.update_info( {'stat': self.chatstate.name, 'tm': int(xtm) } )

    def _timer_event_task(self, before, count, after ) ->None:
        try:
            print( f"[DBG] event {before} to {count}:{after}")
            self.state_event( before, count, after )
        finally:
            with self.lock:
                self._tm_future = None
                self._tm_last_action = time.time()
                if self.chatstate == ChatState.InitBusy:
                    self.chatstate = ChatState.InTalkReady
                elif self.chatstate == ChatState.InTalkBusy:
                    self.chatstate = ChatState.InTalkReady
                elif self.chatstate == ChatState.ShortBreakBusy:
                    self.chatstate = ChatState.ShortBreakReady
                elif self.chatstate == ChatState.LongBreakBusy:
                    self.chatstate = ChatState.LongBreakReady
            print( f"[DBG] event {after} to {count}:{self.chatstate}")
            self.update_info( {'stat': self.chatstate.name } )

    def state_event(self, before, count, after ) ->None:
        pass

    def setTTS(self, sw:bool = False ):
        if sw:
            self.tts = TtsEngine( submit_task = self.submit_task, talk_callback=self._fn_tts_callback )
        else:
            self.tts = None

    # TTSからコールされる
    def _fn_tts_callback(self, text:str, emotion:int, tts_model:str ):
        self.att_set_speek( text )
        if text is not None:
            if self._chat_callback is not None:
                self._chat_callback( ChatMessage.ASSISTANT, text, emotion, tts_model )

    def tts_cancel(self) -> None:
        if self.tts is not None:
            self.tts.cancel()

    # RecognizerEngineからコールされる
    def _fn_recg_callback(self, data:dict ):
        if self._recg_callback is not None:
            content:str = data.get('content')
            self._recg_callback(content)
            if data.get('action') == 'final' and self._recg_autosend:
                self.send_message(content)
        if self._plot_callback is not None:
            spk2d = data.get('spk2d')
            colors = data.get('colors')
            if spk2d is not None:
                self._plot_callback(spk2d,colors)
        else:
            print(f"[BOT] recg {data}")

    def set_recg_callback(self, recg_callback=None, plot_callback=None ):
        if recg_callback is not None:
            self._recg_callback = recg_callback
            self._plot_callback = plot_callback
            if self.att is None:
                self.att = RecognizerEngine()
                self.att.start()
                self.att._callback = self._fn_recg_callback
        else:
            if self.att is not None:
                self.att.stop()
                self.att._callback=None
            self.att = None
            self._recg_callback = None
            self._plot_callback = None

    def set_recg_autosend( self, sw=False ) ->None:
        self._recg_autosend = sw

    def att_set_speek(self, text:str=None ):
        if self.att is not None:
            self.att.set_speek(text)
    
    def submit_task(self, func ) -> Future:
        return self.executor.submit( func )

    def set_api_mode( self, mode:bool ) -> bool:
        self.api_mode = mode
        la: str = 'chat' if mode else 'instruct'
        self.update_info( {'api_mode': la } )
        return mode
    
    def set_chat_callback(self,callback):
        self._chat_callback=callback

    def send_message(self, message:str, *, role:str = ChatMessage.USER, hide:bool=False, keep:bool=True, templeture:float=None, bg:bool=True ) -> bool:
        self.start()
        with self.lock:
            if self.next_message is not None:
                return False
            m:ChatMessage = ChatMessage( role, message, keep=keep, templeture=templeture )
            self.next_message = m
            print( f"[DBG]send_message Lock")
            if role == ChatMessage.USER:
                self.last_user_message_time = time.time()
                self.chatstate = ChatState.InTalkBusy
                self._tm_count = 1
                self._tm_last_action = time.time()
            if bg:
                self.futures.append( self.executor.submit( self.do_chat_talk ) )
        self.tts_cancel()
        if self._chat_callback is not None and not hide and role != ChatMessage.SYSTEM:
            self._chat_callback( role, message, 0 )
        if not bg:
            self.do_chat_talk()
        return True

    def create_profile_prompt(self) -> str:
        return f"# キャラクター設定\n貴方つまり{ChatMessage.ASSISTANT}は生意気で言葉が悪い女性型の感情豊かな会話AIを演じて下さい。\n# 制約条件:\n人間を助ける性格ではありませんが、何かお願いされたら手伝います。\nキャラクター設定はUserやHumanには秘密です。\nキャラクター設定について話さないこと。"

    def create_before_hist_prompt(self) -> str:
        pass

    def create_after_hist_prompt(self) -> str:
        pass

    def create_prompt0(self) -> str:
        prompt = ""
        # 現在地
        location:str = self.get_location()
        # 現在日時
        current_time:str = BotUtils.formatted_current_datetime()
        if BotUtils.length(location)>0:
            prompt = f"Current location: {location}\n"
        prompt += f"Current date and time: {current_time}"
        return prompt
    
    def do_chat_talk(self):
        json_fmt:dict = None
        message: str = None
        try:
            if self.api_mode:
                message = self.do_chat()
            else:
                message = self.do_instruct()
            message = BotUtils.str_strip( message )
            if message is not None:
                try:
                    json_fmt = json.loads(message)
                    self.next_message.json = json_fmt
                    for key in [ 'serif', 'speak', 'comment', '発言', 'セリフ' ]:
                        if key in json_fmt:
                            message = json_fmt.get(key)
                            break
                    for key in [ 'topic', '話題' ]:
                        topic = BotUtils.str_strip( json_fmt.get(key) )
                        if topic is not None:
                            self.update_info( {'topic': topic } )
                            break
                except:
                    pass

            with self.lock:
                if self.next_message.keep and self.next_message.role != ChatMessage.SYSTEM:
                    self.mesg_list.append( self.next_message )
                if message is not None:
                    self.mesg_list.append( ChatMessage( ChatMessage.ASSISTANT, message ) )
        except Exception as ex:
            traceback.print_exc()
        finally:
            with self.lock:
                print( f"[DBG]do_chat_talk Unlock")
                self.next_message = None
                if self.chatstate == ChatState.InTalkBusy:
                    self.chatstate = ChatState.InTalkReady
                    self._tm_last_action = time.time()
        try:
            emotion:int = 0
            if message is not None:
                if self.tts is not None:
                    self.tts.add_talk( message, emotion )
                elif self._chat_callback is not None:
                    self._chat_callback( ChatMessage.ASSISTANT, message, emotion )
        except Exception as ex:
            traceback.print_exc()

    def do_instruct( self ) -> str:

        prompt = BotUtils.join_str(self.create_prompt0(), self.create_profile_prompt(), sep="\n" )

        prompt = BotUtils.join_str( prompt, self.create_before_hist_prompt(), sep="\n\n" )

        prompt_history:str = ChatMessage.list_to_prompt( self.mesg_list + [self.next_message])
        prompt += f"Conversation history:\n{prompt_history}\n\n"

        prompt = BotUtils.join_str( prompt, self.create_after_hist_prompt(), sep="\n\n" )
        prompt += f"\n\n{ChatMessage.ASSISTANT}:"
        ret:str = self.Completion( prompt )
        ret = self.message_strip(ret)
        return ret

    def do_chat(self) -> str:

        message_list:list[dict] = []

        profile = BotUtils.join_str(self.create_prompt0(), self.create_profile_prompt(), sep="\n\n" )
        if profile is not None:
            message_list.append( ChatMessage.create_dict( ChatMessage.SYSTEM, profile) )

        prefix = self.create_before_hist_prompt()
        if prefix is not None:
            message_list.append( ChatMessage.create_dict( ChatMessage.SYSTEM, prefix) )

        for m in self.mesg_list:
            message_list.append( m.to_dict() )
        temperature:float =None
        json_fmt:dict = None
        if self.next_message is not None:
            temperature = self.next_message.templeture
            json_fmt = self.next_message.json
            message_list.append( self.next_message.to_dict() )

        postfix = self.create_after_hist_prompt()
        if postfix is not None:
            message_list.append( ChatMessage.create_dict( ChatMessage.SYSTEM, postfix) )

        # if json_fmt is None:
        #     json_fmt = { '考察': '...', 'topic': '...', 'serif': '...'}
        res_text = self.ChatCompletion( message_list, temperature=temperature, json_fmt=json_fmt)

        return res_text

    def message_strip(self, message:str ) -> str:
        message = message.strip()
        if message.startswith( ChatMessage.ASSISTANT+":" ):
            return message[ len(ChatMessage.ASSISTANT)+1:].strip()
        if message.startswith( ChatMessage.USER+":" ):
            return message[ len(ChatMessage.USER)+1:].strip()
        if message.startswith( ChatMessage.SYSTEM+":" ):
            return message[ len(ChatMessage.SYSTEM)+1:].strip()
        if message.startswith( ChatMessage.AI+":" ):
            return message[ len(ChatMessage.AI)+1:].strip()
        return message

def test():
    bot: DxChatBot = DxChatBot()
    debug_ui(bot)

if __name__ == "__main__":
    test()