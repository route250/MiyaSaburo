from typing import Any, Dict, List, Optional, Sequence, Union
from uuid import UUID
import traceback

class AAA:
    def on_llm_error( self, message="", exception: Union[Exception, KeyboardInterrupt]=None ):
        if message is None:
            message = ""
        if exception is not None:
            trace = traceback.format_exc()
            message = message + "\n" + trace
        print( f"{message.strip()}" )

aaa = AAA()

try:
    raise Exception("えらーですが")
except Exception as ex:
    aaa.on_llm_error(None,ex)