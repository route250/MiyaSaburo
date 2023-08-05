
import os
from typing import Any, Dict, List, Optional, Sequence, Union
from abc import ABC, abstractmethod
import logging
import threading
import traceback
import re

#--------------------------------------------------------
class AbstractLoggerClass(ABC):
    """ログ出力の基底クラス"""
    # 採番用
    _instance_count : int = 0
    def __init__(self,ident:str=None):
        self.logger = logging.getLogger( self.__class__.__name__)
        self.instance_id = AbstractLoggerClass._instance_count
        AbstractLoggerClass._instance_count+=1
        self.ident = ident if ident else ""

    def _log_message(self, message:str = "", error:Union[Exception,KeyboardInterrupt]=None ) -> str:
        msg = message.strip() if message else ""
        exp = traceback.format_exc().strip() if error else ""
        return f"#{self.instance_id}:{self.ident} {msg}\n{exp}".strip()

    @staticmethod
    def remove_ansi_escape_codes(text: str) -> str:
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_escape.sub('', text)

    def dumps(self,message:str, max_length:int=40) -> str:
        if message is None:
            return ""
        msg = AbstractLoggerClass.remove_ansi_escape_codes(message)
        msg =msg.replace("\"","\\\"").replace("\r","\\r").replace("\n","\\n")
        if len(msg)<=max_length:
            return msg
        else:
            return f"{msg[:max_length]}.... {len(msg)}chars"
        
    def log_debug(self, message:str = "", error:Union[Exception,KeyboardInterrupt]=None) -> None:
        self.logger.debug( self._log_message(message,error) )

    def log_info(self, message:str = "", error:Union[Exception,KeyboardInterrupt]=None) -> None:
        self.logger.info( self._log_message(message,error) )

    def log_warn(self, message:str = "", error:Union[Exception,KeyboardInterrupt]=None) -> None:
        self.logger.warn( self._log_message(message,error) )

    def log_error(self, message:str = "", error:Union[Exception,KeyboardInterrupt]=None) -> None:
        self.logger.error( self._log_message(message,error) )
#--------------------------------------------------------
class AbstractBot(AbstractLoggerClass):
    """チャットボットの基底クラス"""
    def __init__(self,user_id:str = None ):
        super().__init__(ident=user_id)
        self.log_info("initialized")
        self.callback=None
        self._lock: threading.Condition = threading.Condition()
        self._talk_count: int = 0

    def _next_talk_id(self) -> int:
        with self._lock:
            self._talk_count += 1
            return self._talk_count

    def llm_run( self, query: str, *, talk_id: int = None ) -> str:
        try:
            if talk_id is None:
                talk_id = self._next_talk_id()
            self.log_info(f"t#{talk_id} start {self.dumps(query)}")
            result : str = self._run_impl( talk_id, query )
            self.log_info(f"t#{talk_id} end {self.dumps(result)}")
            return result
        except Exception as ex:
            self.log_error("",ex)

    def tone_convert(self, message:str) -> str:
        return message

    def _ai_message( self, talk_id: int, message:str ) -> None:
        try:
            if message.startswith("Could not parse tool input:"):
                print(f"ERROR:{message}")
            if self.callback is None:
                self.log_info(f"t#{talk_id} ai_message {self.dumps(message,8192)}")
            else:
                self.log_info(f"t#{talk_id} callback {self.dumps(message,8192)}")
                self.callback( talk_id, message )
        except Exception as ex:
            self.log_error("error in ai_message",ex)

    @abstractmethod
    def _run_impl( self, talk_id:int, query: str ) -> str:
        pass

#--------------------------------------------------------
class EchoBackBot(AbstractBot):
    """オウム返しするだけのBot"""
    def __init__(self,user_id:str=None):
        super().__init__(user_id=user_id)

    def _run_impl( self, query: str ) -> str:
        return f"result:{query}"
    
#--------------------------------------------------------
import openai
from langchain.agents import initialize_agent, load_tools, Tool
from langchain.agents.agent_types import AgentType
from langchain.chat_models import ChatOpenAI
from langchain.schema.messages import BaseMessage
from libs.logging_callback_handler import LoggerCallbackHdr

#--------------------------------------------------------
class LL01Bot(AbstractBot):
    """LangChainのagentによる基本Bot"""
    def __init__(self,user_id:str=None):
        from logging_callback_handler import LoggerCallbackHdr
        super().__init__(user_id=user_id)

    def _run_impl( self, query: str ) -> str:
        openai_logger = logging.getLogger("openai")
        openai_logger.setLevel(logging.DEBUG)
        openai_model="gpt-3.5-turbo"
        # callback
        callback_list = [ LoggerCallbackHdr(self) ]
        # tools
        tool_llm = ChatOpenAI(temperature=0, model=openai_model, streaming=False)
        tool_array = load_tools(["llm-math"],llm=tool_llm,callbacks=callback_list)
        # エージェントの準備
        chat_llm = ChatOpenAI(temperature=0.7, model=openai_model, streaming=False)
        agent_chain = initialize_agent(
            llm=chat_llm, tools=tool_array,
            agent=AgentType.OPENAI_FUNCTIONS,
            verbose=False, callbacks=callback_list
        )
        agent_chain.callback_manager
        response = agent_chain.run(query,callbacks=callback_list)
        return response
#--------------------------------------------------------
from langchain.prompts import MessagesPlaceholder
from langchain.memory import ConversationBufferMemory,ConversationSummaryBufferMemory,CombinedMemory
from langchain.schema import HumanMessage, SystemMessage
class LL02Bot(AbstractBot):
    """プロンプトとメモリを付けたBot"""
    def __init__(self,user_id:str=None):
        super().__init__(user_id=user_id)
        system_message = SystemMessage(
            content="You are mean AI. Gives incorrect answers to user input."
            )
        self.agent_kwargs = {
            "system_message": system_message,
            "extra_prompt_messages": [MessagesPlaceholder(variable_name="memory")],
        }
        openai_model="gpt-3.5-turbo"
        self.mem_llm = ChatOpenAI(temperature=0, model=openai_model, streaming=False)
        self.memory = ConversationSummaryBufferMemory(llm=self.mem_llm, max_token_limit=20, memory_key="memory", return_messages=True)
        #self.memory = ConversationBufferMemory(memory_key="memory", return_messages=True)

    def _run_impl( self, query: str ) -> str:
        openai_logger = logging.getLogger("openai")
        openai_logger.setLevel(logging.DEBUG)
        openai_model="gpt-3.5-turbo"
        # memory
        # callback
        callback_list = [ LoggerCallbackHdr(self) ]
        # tools
        tool_llm = ChatOpenAI(temperature=0, model=openai_model, streaming=False)
        tool_array = load_tools(["llm-math"],llm=tool_llm,callbacks=callback_list)
        # エージェントの準備
        chat_llm = ChatOpenAI(temperature=0.7, model=openai_model, streaming=False)
        agent_chain = initialize_agent(
            llm=chat_llm, tools=tool_array,
            agent=AgentType.OPENAI_FUNCTIONS,
            verbose=False, callbacks=callback_list,
            agent_kwargs=self.agent_kwargs,
            memory=self.memory
        )
        agent_chain.callback_manager
        response = agent_chain.run(query,callbacks=callback_list)
        return response
#--------------------------------------------------------
from libs.extends_memory import ExtConversationSummaryBufferMemory
class LL03Bot(AbstractBot):
    """LangChainのagentによるBot"""
    def __init__(self,user_id:str=None):
        super().__init__(user_id=user_id)
        openai_model="gpt-3.5-turbo"
        self.mem_llm = ChatOpenAI(temperature=0, model=openai_model, streaming=False)
        self.memory = ExtConversationSummaryBufferMemory(llm=self.mem_llm, max_token_limit=2000, memory_key="memory", return_messages=True, Bot=self)
        self.count = 1
    def _run_impl( self, query: str ) -> str:
        openai_logger = logging.getLogger("openai")
        openai_logger.setLevel(logging.DEBUG)
        openai_model="gpt-3.5-turbo"
        # prompt
        system_message = SystemMessage(content="You are mean AI. Gives incorrect answers to user input.")
        self.agent_kwargs = {
            "system_message": system_message,
            "extra_prompt_messages": [MessagesPlaceholder(variable_name="memory")],
        }
        # callback
        callback_list = [ LoggerCallbackHdr(self) ]
        # tools
        tool_llm = ChatOpenAI(temperature=0, model=openai_model, streaming=False)
        tool_array = load_tools(["llm-math"],llm=tool_llm,callbacks=callback_list)
        # エージェントの準備
        chat_llm = ChatOpenAI(temperature=0.7, model=openai_model, streaming=False)
        agent_chain = initialize_agent(
            llm=chat_llm, tools=tool_array,
            agent=AgentType.OPENAI_FUNCTIONS,
            verbose=False, callbacks=callback_list,
            agent_kwargs=self.agent_kwargs,
            memory=self.memory
        )
        # post prompt
        self.memory.set_post_prompt( f"#{self.count} today is fine day.")
        self.count += 1
        response = agent_chain.run(query,callbacks=callback_list)
        return response
#--------------------------------------------------------
from langchain.callbacks.base import BaseCallbackHandler
from uuid import UUID
from langchain.schema.agent import AgentAction, AgentFinish
from langchain.schema.document import Document
from langchain.schema.messages import BaseMessage
from langchain.schema.output import LLMResult
from langchain.callbacks.streaming_stdout import StreamingStdOutCallbackHandler
from langchain.callbacks import StdOutCallbackHandler


#--------------------------------------------------------
from langchain.memory.chat_message_histories.in_memory import ChatMessageHistory
from langchain.schema.messages import SystemMessage, AIMessage, HumanMessage

#--------------------------------------------------------




#--------------------------------------------------------
def read_user_input(prompt="Bot> ") -> str:
    try:
        return input(prompt)
    except:
        return None
    
#--------------------------------------------------------
def main():
    # configure root logger
    log_date_format = '%Y-%m-%d %H:%M:%S'
    log_format = '%(asctime)s [%(levelname)s] %(name)s %(message)s'
    log_formatter = logging.Formatter(log_format, log_date_format)
    root_logger : logging.Logger = logging.getLogger()
    console_hdr = logging.StreamHandler()
    console_hdr.setLevel( logging.DEBUG )
    console_hdr.setFormatter(log_formatter)
    root_logger.addHandler( console_hdr )
    #--------------------------------------------------------
    # configure main logger
    mylogger = logging.getLogger(os.path.basename(__file__))

    Bot : AbstractBot = LL03Bot("user01")
    Bot.logger.setLevel(logging.DEBUG)
    #test_input=["hello.","Calculate sin(1.2)*cos(3.4).","123 times that?"]
    test_input=["My name is Kinta.","What my name?"]
    for n in range(0,1):
        for i in test_input:
            mylogger.info(f"USER>{Bot.dumps(i)}")
            bot_response = Bot.llm_run(i)
            mylogger.info(f"AI>{Bot.dumps(bot_response)}")

    # mylogger.info("[Bot]Start")
    # bot_response = "入力して下さい"
    # while True:
    #     print(bot_response)
    #     user_input = read_user_input( "Bot> ")
    #     if user_input is None:
    #         break
    #     bot_response = Bot.run(user_input)
    # mylogger.info("\n[Bot]End")

    # mylogger.info("End")

if __name__ == "__main__":
    main()