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

next_prompts = [ 
    '私は今、起動したところです。相手に話しかけてみます。',
    '相手の反応がないけど、話題を続けましょう。',
    '相手の反応がないので、違う話題を話してみましょう。',
    '相手の反応がないので、返事を催促しましょう。'
]

class DxPlanEmoChatBot2(DxEmoChatBot):

    def __init__(self):
        super().__init__()

    def a(self):
        pass
    # override
    def state_event(self, before, count, after ) ->None:
        role:str = ChatMessage.ASSISTANT
        prompt:str = None
        if after == ChatState.InTalkBusy:
            if count==1 and len(self.mesg_list)==0:
                prompt = next_prompts[0]
            else:
                n:int = len(next_prompts) - 1
                idx = (count-1) % n + 1
                prompt = next_prompts[idx]
        elif after == ChatState.ShortBreakBusy:
            prompt = "相手の反応がないので、会話をおわらせましょう。"
        elif after == ChatState.LongBreakBusy:
            prompt = None

        if prompt is not None and role is not None:
            print( f"[DBG] event {after} {count} {prompt}" )
            self.send_message( prompt, role=role, hide=True, keep=False, templeture=0.7, bg=False )
        else:
            print( f"[DBG] event {after} {count} {prompt} skip" )

def test():
    bot: DxPlanEmoChatBot2 = DxPlanEmoChatBot2()
    debug_ui(bot)

if __name__ == "__main__":
    test()