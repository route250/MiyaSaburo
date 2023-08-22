import typing
from typing import (
    Any,
    AsyncIterator,
    Dict,
    Iterator,
    List,
    Optional,
    Sequence,
    cast,
)
import json
from json import JSONDecodeError
from langchain.chat_models import ChatOpenAI
from langchain.schema import ( AIMessage, BaseChatMessageHistory, BaseMessage, HumanMessage, SystemMessage, FunctionMessage, messages_from_dict, messages_to_dict)

class ExChatOpenAI(ChatOpenAI):
    def predict_messages( self, messages: List[BaseMessage], *, stop: Optional[Sequence[str]] = None, **kwargs: Any, ) -> BaseMessage:
        tmp_messages = messages
        for t in range(0,2):
            message: BaseMessage = super().predict_messages(tmp_messages,stop=stop,**kwargs)
            if isinstance(message, AIMessage):
                function_call = message.additional_kwargs.get("function_call", {})
                if function_call:
                    function_name = function_call.get("name","")
                    function_args = function_call.get("arguments","")
                    try:
                        json.loads(function_args)
                        break
                    except JSONDecodeError:
                        print( f"ERROR: function {function_name}  {function_args} ")
                        tmp_messages = messages + [ message, FunctionMessage( name=function_name, content=f"Could not parse JSON: {function_args}") ]
            else:
                break
        return message