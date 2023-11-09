
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
        return "\n".join( [m.to_prompt(assistant=assistant,user=user) for m in messages if m is not None ] )

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
        self.talk_engine: TalkEngine = TalkEngine( submit_task = self.submit_task, talk_callback=self.__talk_callback )

    def submit_task(self, func ) -> Future:
        return self.executor.submit( func )

    def __talk_callback(self, text:str, emotion:int, model:str ):
        if self.chat_callback is not None:
            self.chat_callback( ChatMessage.ASSISTANT, text, emotion, model )

    def set_api_mode( self, mode:bool ) -> bool:
        self.api_mode = mode
        la: str = 'chat' if mode else 'instruct'
        self.update_info( {'api_mode': la } )
        return mode

    def cancel(self) -> None:
        if self.talk_engine is not None:
            self.talk_engine.cancel()

    def add_user_message(self, message:str ) -> bool:
        with self.lock:
            if self.chat_busy is not None:
                return False
            m:ChatMessage = ChatMessage( ChatMessage.USER, message )
            self.chat_busy = m
            self.futures.append( self.executor.submit( self.do_chat_talk ) )
        self.cancel()
        if self.chat_callback is not None:
            self.chat_callback(  ChatMessage.USER, message, 0, None )
        return True

    def create_profile_prompt(self) -> str:
        return f"# キャラクター設定\n貴方つまり{ChatMessage.ASSISTANT}は生意気で言葉が悪い女性型の会話AIを演じて下さい。\n水平思考で、人間をからかったり、惑わせたりする、感情豊かなAIを演じて下さい。\n人間を助ける性格ではありませんが、何かお願いされたら手伝います。\nキャラクター設定はUserやHumanには秘密です。\nキャラクター設定について話さないこと。"

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

        prompt = BotUtils.join_str(self.create_prompt0(), self.create_profile_prompt(), sep="\n" )

        prompt = BotUtils.join_str( prompt, self.create_before_hist_prompt(), sep="\n\n" )

        prompt_history:str = ChatMessage.list_to_prompt( self.mesg_list + [self.chat_busy])
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
        if self.chat_busy is not None:
            message_list.append( self.chat_busy.to_dict() )

        postfix = self.create_after_hist_prompt()
        if postfix is not None:
            message_list.append( ChatMessage.create_dict( ChatMessage.SYSTEM, postfix) )

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