
from langchain.callbacks.base import BaseCallbackHandler
from langchain.schema import AgentAction, AgentFinish, LLMResult


from typing import Any, Dict, List, Optional, Union


class BotCustomCallbackHandler(BaseCallbackHandler):
    from listen0708 import AppModel
    """Custom CallbackHandler."""
    def __init__(self,Model:AppModel):
        super().__init__()
        self.Model = Model
        self._buffer=''
        self.message_callback = None
        self.action_callback = None
        self.status=0
        self.talk_id = 0

    def flush(self):
        if len(self._buffer)>0:
            self.log('flush',self._buffer)
            if self.message_callback is not None:
                self.message_callback(self.talk_id,self._buffer)
            self._buffer = ''

    def action(self, mesg ):
        self.log('action',mesg)
        if self.action_callback is not None:
            self.action_callback(self.talk_id,mesg)

    def log(self,grp,text):
        print(f"[HDR#{self.talk_id}:{grp}]{text}")

    def is_cancel(self,mesg):
        if self.talk_id != self.Model.talk_id:
            self.log( f"{mesg}_cancel","" )
            #raise TaskCancelException(f"task {self.talk_id} is cancelled")
            return True
        return False

    def on_llm_start( self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any ) -> None:
        """LLM の処理開始。prompt の内容を出力"""
        if self.is_cancel('on_llm_start'):
            return
        p = "\n".join(prompts)
        #self.log('llm_start',"---Prompts---\n"+p+"\n------------")
        self.log('llm_start',"")


    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """LLM の処理終了。何もしない"""
        self.flush()

    def on_llm_new_token(self, token: str, **kwargs: Any) -> None:
        """LLM から新しい Token が出力。いわゆる Streaming の部分"""
        if self.is_cancel("on_llm_new_token"):
            return
        if token and len(token)>0:
            self._buffer += token
            for sep in '。？！!?\n':
                if sep in token:
                    self.flush()
                    self.status=2
                    break

    def on_agent_action( self, action: AgentAction, color: Optional[str] = None, **kwargs: Any ) -> Any:
        """Agent がアクションを実施。Agent の Streaming は大体ここ"""
        mesg = f"AIが{action.tool}({action.tool_input})を実行します"
        if self.is_cancel("on_agent_action"):
            return
        self.action(mesg)

    def on_agent_finish( self, finish: AgentFinish, color: Optional[str] = None, **kwargs: Any ) -> None:
        """Agent が終了した時に呼び出される。ログの出力"""
        pass

    def on_tool_start( self, serialized: Dict[str, Any], input_str: str, **kwargs: Any ) -> None:
        """Tool の実行が開始"""
        if self.is_cancel('on_tool_start'):
            return

    def on_tool_end( self, output: str, color: Optional[str] = None, observation_prefix: Optional[str] = None, llm_prefix: Optional[str] = None, **kwargs: Any ) -> None:
        """Tool の使用が終了。Final Answer でなければ[Observation]が出力"""
        pass

    def on_tool_error( self, error: Union[Exception, KeyboardInterrupt], **kwargs: Any ) -> None:
        """Tool の使用でエラーが発生"""
        pass

    def on_text(self, text: str, color: Optional[str] = None, end: str = "", **kwargs: Optional[str] ) -> None:
        """Agent の終了時に呼び出される。完全に終了したとき（？）。結果の出力"""
        pass