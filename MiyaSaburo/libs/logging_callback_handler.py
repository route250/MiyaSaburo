
from typing import Any, Dict, List, Optional, Sequence, Union
from uuid import UUID

#from langchain.callbacks import OpenAICallbackHandler,StdOutCallbackHandler, FileCallbackHandler
from langchain.callbacks.base import BaseCallbackHandler
from langchain.schema import AgentAction, AgentFinish, LLMResult
from langchain.schema.document import Document
from langchain.schema.messages import BaseMessage
from langchain.schema.output_parser import OutputParserException
import openai.error
from libs.bot_model import AbstractBot

class LoggerCallbackHdr(BaseCallbackHandler):

    def __init__(self, bot:AbstractBot):
        self._bot = bot
    #------------------------------------------------------------
    # LLMManagerMixin:
    #------------------------------------------------------------
    def on_llm_new_token( self, token: str, *, run_id: UUID, parent_run_id: Optional[UUID] = None, **kwargs: Any, ) -> Any:
        self._bot.log_info(f"on_llm_new_token ")
    def on_llm_end( self, response: LLMResult, *, run_id: UUID, parent_run_id: Optional[UUID] = None, **kwargs: Any, ) -> Any:
        self._bot.log_info(f"on_llm_end")
    def on_llm_error( self, error: Union[Exception, KeyboardInterrupt], *, run_id: UUID, parent_run_id: Optional[UUID] = None, **kwargs: Any, ) -> Any:
        self._bot.log_error(f"on_llm_error",error)
    #------------------------------------------------------------
    # ChainManagerMixin:
    #------------------------------------------------------------
    def on_chain_end(self,outputs: Dict[str, Any],*,run_id: UUID,parent_run_id: Optional[UUID] = None,**kwargs: Any,) -> Any:
        self._bot.log_info(f"on_chain_end ")
    def on_chain_error(self,error: Union[Exception, KeyboardInterrupt],*,run_id: UUID,parent_run_id: Optional[UUID] = None,**kwargs: Any,) -> Any:
        if type(error).__name__ == 'OutputParserException':
            self._bot.log_error(f"on_chain_error {error}")
        elif type(error).__name__ == 'Timeout':
            self._bot.log_error(f"on_chain_error {error}")
        elif type(error).__name__ == 'ValidationError':
            self._bot.log_error(f"on_chain_error {error}")
        else:
            self._bot.log_error(f"on_chain_error",error)
    def on_agent_action(self,action: AgentAction,*,run_id: UUID,parent_run_id: Optional[UUID] = None,**kwargs: Any,) -> Any:
        self._bot.log_info(f"on_agent_action {self._bot.dumps(action.log,max_length=8192)}")
    def on_agent_finish(self,finish: AgentFinish,*,run_id: UUID,parent_run_id: Optional[UUID] = None,**kwargs: Any,) -> Any:
        self._bot.log_info(f"on_agent_finish {self._bot.dumps(finish.log,max_length=8192)}")
    #------------------------------------------------------------
    # ToolManagerMixin:
    #------------------------------------------------------------
    def on_tool_end(self,output: str,*,run_id: UUID,parent_run_id: Optional[UUID] = None,**kwargs: Any,) -> Any:
        self._bot.log_info(f"on_tool_end ")
    def on_tool_error(self,error: Union[Exception, KeyboardInterrupt],*,run_id: UUID,parent_run_id: Optional[UUID] = None,**kwargs: Any,) -> Any:
        self._bot.log_error(f"on_tool_error",error)
    #------------------------------------------------------------
    # RetrieverManagerMixin:
    #------------------------------------------------------------
    def on_retriever_error(self,error: Union[Exception, KeyboardInterrupt],*,run_id: UUID,parent_run_id: Optional[UUID] = None,**kwargs: Any,) -> Any:
        self._bot.log_error(f"on_retriever_error",error)
    def on_retriever_end(self,documents: Sequence[Document],*,run_id: UUID,parent_run_id: Optional[UUID] = None,**kwargs: Any,) -> Any:
        self._bot.log_info(f"on_retriever_end ")
    #------------------------------------------------------------
    #CallbackManagerMixin,
    #------------------------------------------------------------
    def on_llm_start(self,serialized: Dict[str, Any],prompts: List[str],*,run_id: UUID,parent_run_id: Optional[UUID] = None,tags: Optional[List[str]] = None,metadata: Optional[Dict[str, Any]] = None,**kwargs: Any,) -> Any:
        class_name = serialized.get("name", serialized.get("id", ["<unknown>"])[-1])
        self._bot.log_info(f"on_llm_start {class_name}")
    def on_chat_model_start(self,serialized: Dict[str, Any],messages: List[List[BaseMessage]],*,run_id: UUID,parent_run_id: Optional[UUID] = None,tags: Optional[List[str]] = None,metadata: Optional[Dict[str, Any]] = None,**kwargs: Any,) -> Any:
        class_name = serialized.get("name", serialized.get("id", ["<unknown>"])[-1])
        self._bot.log_info(f"on_chat_model_start {class_name}")
    def on_retriever_start(self,serialized: Dict[str, Any],query: str,*,run_id: UUID,parent_run_id: Optional[UUID] = None,tags: Optional[List[str]] = None,metadata: Optional[Dict[str, Any]] = None,**kwargs: Any,) -> Any:
        class_name = serialized.get("name", serialized.get("id", ["<unknown>"])[-1])
        self._bot.log_info(f"on_retriever_start {class_name}")
    def on_chain_start(self,serialized: Dict[str, Any],inputs: Dict[str, Any],*,run_id: UUID,parent_run_id: Optional[UUID] = None,tags: Optional[List[str]] = None,metadata: Optional[Dict[str, Any]] = None,**kwargs: Any,) -> Any:
        class_name = serialized.get("name", serialized.get("id", ["<unknown>"])[-1])
        self._bot.log_info(f"on_chain_start {class_name}")
    def on_tool_start(self,serialized: Dict[str, Any],input_str: str,*,run_id: UUID,parent_run_id: Optional[UUID] = None,tags: Optional[List[str]] = None,metadata: Optional[Dict[str, Any]] = None,**kwargs: Any,) -> Any:
        class_name = serialized.get("name", serialized.get("id", ["<unknown>"])[-1])
        self._bot.log_info(f"on_tool_start {class_name}")
    #------------------------------------------------------------
    # RunManagerMixin:
    #------------------------------------------------------------
    def on_text(self,text: str,*,run_id: UUID,parent_run_id: Optional[UUID] = None,**kwargs: Any,) -> Any:
        self._bot.log_info(f"on_text {self._bot.dumps(text)}")
