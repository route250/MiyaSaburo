import time
import json
import traceback
import concurrent.futures
import queue
from concurrent.futures import ThreadPoolExecutor, Future
from DxBotUtils import BotCore, BotUtils, ToolBuilder
from DxChatBot import ChatState,ChatMessage,DxChatBot
from DxEmoChatBot import DxEmoChatBot
from DxBotUI import debug_ui

class DxPlanEmoChatBot2(DxEmoChatBot):

    def __init__(self):
        super().__init__()

    def a(self):
        pass
    # override
    def state_event(self, before, count, after ) ->None:
        if after == ChatState.LongBreakBusy:
            print( f"[DBG] aaaaa {after}" )
            self.send_message( 'Userからの応答がないから会話の続きをして。', role=ChatMessage.SYSTEM )
        else:
            print( f"[DBG] skip {after}" )

def test():
    bot: DxPlanEmoChatBot2 = DxPlanEmoChatBot2()
    debug_ui(bot)

if __name__ == "__main__":
    test()