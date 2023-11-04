
import time
import json
import traceback
import concurrent.futures
import queue
from concurrent.futures import ThreadPoolExecutor, Future
from DxBotUtils import BotCore, BotUtils, TalkEngine
from DxBotUI import debug_ui

class ChatMessage:

    ASSISTANT="assistant"
    USER="user"
    SYSTEM="system"
    AI="AI"

    def __init__( self, role:str, message:str, tm:float=None ):
        self.role=role
        self.message=message
        self.tm = tm if tm is not None and tm>0 else time.time()

    def to_prompt(self):
        return f"{self.role}: {self.message}"

    def to_dict(self):
        return ChatMessage.create_dict( self.role, self.message )

    @staticmethod
    def list_to_prompt( messages:list ):
        return "\n".join( [m.to_prompt() for m in messages] )

    @staticmethod
    def create_dict( role:str, message:str ) -> dict:
        return { 'role':role, 'content': message }

class DxChatBot(BotCore):
    
    def __init__(self, *, executor=None):
        super().__init__()
        self.api_mode:bool = False
        self.executor:ThreadPoolExecutor = executor if executor is not None else ThreadPoolExecutor(max_workers=4)
        self.futures:list[Future] = []
        self.mesg_list:list[ChatMessage]=[]
        self.chat_busy:ChatMessage = None
        self.chat_callback = None
        self.api_mode = self.set_api_mode(True)
        self.talk_engine: TalkEngine = TalkEngine( submit_call = self.__submit_call, start_call=self.__start_call )

    def __submit_call(self, func ) -> Future:
        return self.executor.submit( func )

    def __start_call(self, text:str, emotion:int ):
        if self.chat_callback is not None:
            self.chat_callback( ChatMessage.ASSISTANT, text, emotion )

    def set_api_mode( self, mode:bool ) -> bool:
        self.api_mode = mode
        la: str = 'chat' if mode else 'instruct'
        self.update_info( {'api_mode': la } )
        return mode

    def cancel(self) -> None:
        if self.talk_engine is not None:
            self.talk_engine.cancel()

    def add_talk(self, message:str ) -> bool:
        with self.lock:
            if self.chat_busy is not None:
                return False
            m:ChatMessage = ChatMessage( ChatMessage.USER, message )
            self.chat_busy = m
            self.futures.append( self.executor.submit( self.do_talk ) )
        self.cancel()
        if self.chat_callback is not None:
            self.chat_callback(  ChatMessage.USER, message, 0 )
        return True

    def create_promptA(self) -> str:
        return f"# キャラクター設定\n貴方つまり{ChatMessage.ASSISTANT}はアニメーションに登場する生意気で言葉が悪い女性型の会話AIです。\n人間を助けないけれど、お願いされたら手伝ってやります。"

    def create_promptB(self) -> str:
        pass

    def create_promptC(self) -> str:
        pass

    def create_prompt(self,*,prefix=None,postfix=None) -> str:
        prompt_current_time = BotUtils.formatted_current_datetime()
        prompt_history:str = ChatMessage.list_to_prompt( self.mesg_list + [self.chat_busy])

        prompt = ""
        if prefix is not None and len(prefix)>0:
            prompt = prefix + "\n\n"
        prompt += f"Conversation history:\n{prompt_history}\n\n"
        if postfix is not None and len(postfix)>0:
            prompt = prompt + postfix + "\n\n" 
        prompt = prompt + f"current date time: {prompt_current_time}\n\n{ChatMessage.ASSISTANT}:"
        print(f"[DBG]chatprompt\n{prompt}")
        return prompt
    
    def do_talk(self):
        ret: str = None
        try:
            if self.api_mode:
                ret = self.do_chat()
            else:
                ret = self.do_instruct()
            ret = self.message_strip(ret)
            with self.lock:
                self.mesg_list.append( self.chat_busy )
                self.mesg_list.append( ChatMessage( ChatMessage.ASSISTANT, ret ) )
        except Exception as ex:
            traceback.print_exc()
        finally:
            with self.lock:
                self.chat_busy = None
        try:
            emotion:int = 0
            if ret is not None:
                if self.talk_engine is not None:
                    self.talk_engine.add_talk( ret, emotion )
                elif self.chat_callback is not None:
                    self.chat_callback( ChatMessage.ASSISTANT, ret, emotion )
        except Exception as ex:
            traceback.print_exc()

    def do_instruct( self ) -> str:
        prefix = self.create_promptB()
        postfix = self.create_promptC()
        prompt_current_time = BotUtils.formatted_current_datetime()
        prompt_history:str = ChatMessage.list_to_prompt( self.mesg_list + [self.chat_busy])

        prompt = ""
        if prefix is not None and len(prefix)>0:
            prompt = prefix + "\n\n"
        prompt += f"Conversation history:\n{prompt_history}\n\n"
        if postfix is not None and len(postfix)>0:
            prompt = prompt + postfix + "\n\n" 
        prompt = prompt + f"current date time: {prompt_current_time}\n\n{ChatMessage.ASSISTANT}:"
        print(f"[DBG]chat prompt {prompt}")
        ret:str = self.Completion( prompt )
        ret = self.message_strip(ret)
        return ret

    def do_chat(self) -> str:
        profile = self.create_promptA()
        prefix = self.create_promptB()
        postfix = self.create_promptC()
        message_list:list[dict] = []
        if profile is not None:
            message_list.append( ChatMessage.create_dict( ChatMessage.SYSTEM, profile) )
        if prefix is not None:
            message_list.append( ChatMessage.create_dict( ChatMessage.SYSTEM, prefix) )
        for m in self.mesg_list:
            message_list.append( m.to_dict() )
        if self.chat_busy is not None:
            message_list.append( self.chat_busy.to_dict() )
        if postfix is not None:
            message_list.append( ChatMessage.create_dict( ChatMessage.SYSTEM, postfix) )
        prompt_current_time = BotUtils.formatted_current_datetime()
        message_list.append( ChatMessage.create_dict( ChatMessage.SYSTEM, f"current date time: {prompt_current_time}"))

        resss = self.ChatCompletion( message_list )

        return resss

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