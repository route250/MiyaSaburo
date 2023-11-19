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

next_prompts = [ '相手の反応がありませんが、違う言葉で話題を続けましょう。', '相手の反応がありません。違う言葉で話題を少し変えてみましょう。', '相手の反応がありません。寝ましょう。']
class DxPlanEmoChatBot2(DxEmoChatBot):

    def __init__(self):
        super().__init__()

    def a(self):
        pass
    # override
    def state_event(self, before, count, after ) ->None:
        if after == ChatState.InTalkBusy:
            p:str = None
            if count==1 and len(self.mesg_list)==0:
                p = 'まだ会話がありません。あなたから話しかけて下さい。'
            else:
                p = next_prompts[count%len(next_prompts)]
            if p is not None:
                print( f"[DBG] aaaaa {after} {p}" )
                self.send_message( p, role=ChatMessage.SYSTEM, bg=False )
            else:
                print( f"[DBG] aaaaa {after} {p} skip" )

        elif after == ChatState.LongBreakBusy:
            print( f"[DBG] aaaaa {after}" )
            self.send_message( 'Userからの応答がないから、あなたの最後の会話の続きを生成して。', role=ChatMessage.SYSTEM, bg=False )
        else:
            print( f"[DBG] skip {after}" )

def test():
    bot: DxPlanEmoChatBot2 = DxPlanEmoChatBot2()
    debug_ui(bot)

if __name__ == "__main__":
    test()