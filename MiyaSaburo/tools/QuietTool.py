
from typing import Optional
import threading
from langchain.callbacks.manager import AsyncCallbackManagerForToolRun, CallbackManagerForToolRun
from langchain.tools.base import BaseTool

def end_quiet():
    global quiet_timer
    quiet_timer = None
    print("[LLM] quiet cleard")

def start_quiet(query):
    global quiet_timer

    if quiet_timer is not None:
        quiet_timer.cancel()
    
    try:
        sec = int(query)
    except:
        sec = 15
    
    quiet_timer = threading.Timer(sec,end_quiet)
    quiet_timer.start()
    print(f"[LLM] quiet {sec}sec")
    return f"{sec}秒間、静かにしましょう"

class QuietTool(BaseTool):
    name = "QuietTool"
    description = (
        "Used when you want a little silence."
        "The input is the number of seconds you want to be quiet."
    )

    def _run( self, query: str, run_manager: Optional[CallbackManagerForToolRun] = None ) -> str:
        """Use the tool."""
        return start_quiet(query)

    async def _arun(self, query: str, run_manager: Optional[AsyncCallbackManagerForToolRun] = None) -> str:
        """Use the tool asynchronously."""
        raise NotImplementedError("custom_search does not support async")