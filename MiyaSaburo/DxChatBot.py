
import time
import json
import traceback
import concurrent.futures
import queue
from concurrent.futures import ThreadPoolExecutor, Future
from DxBotUtils import BotCore, BotUtils
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

    @staticmethod
    def list_to_prompt( messages:list ):
        return "\n".join( [m.to_prompt() for m in messages] )

class DxChatBot(BotCore):
    
    def __init__(self, *, executor=None):
        super().__init__()
        self.executor:ThreadPoolExecutor = executor if executor is not None else ThreadPoolExecutor(max_workers=4)
        self.futures:list[Future] = []
        self.mesg_list:list[ChatMessage]=[]
        self.chat_busy:ChatMessage = None
        self.chat_callback = None

    def add_talk(self, message:str ) -> bool:
        with self.lock:
            if self.chat_busy is not None:
                return False
            m:ChatMessage = ChatMessage( ChatMessage.USER, message )
            self.chat_busy = m
            self.futures.append( self.executor.submit( self.do_talk ) )
        if self.chat_callback is not None:
            self.chat_callback(  ChatMessage.USER, message )
        return True

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
            prompt:str = self.create_prompt()
            print(f"[DBG]chat prompt {prompt}")
            ret:str = self.Completion( prompt )
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
            if ret is not None and self.chat_callback is not None:
                self.chat_callback( ChatMessage.ASSISTANT, ret )
        except Exception as ex:
            traceback.print_exc()

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