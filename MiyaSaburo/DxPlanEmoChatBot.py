import time
import json
import traceback
import concurrent.futures
import queue
from concurrent.futures import ThreadPoolExecutor, Future
from DxBotUtils import BotCore, BotUtils
from DxChatBot import ChatMessage,DxChatBot
from DxEmoChatBot import DxEmoChatBot
from DxBotUI import debug_ui

class DxPlanEmoChatBot(DxEmoChatBot):
    PLAN_FMT = {
        '目標': '3項目のリスト形式で',
        '計画': '目標を達成するための計画をリスト形式で',
    }
    def __init__(self):
        super().__init__()
        self.plan_data:dict = {}
        for key in DxPlanEmoChatBot.PLAN_FMT.keys():
            self.plan_data[key] = 'no plan'

    #Override
    def create_prompt(self,*,prefix=None,postfix=None) -> str:
        prompt_current_plan = BotUtils.to_prompt( self.plan_data )
        prompt_history:str = ChatMessage.list_to_prompt( self.mesg_list + [self.chat_busy])
        prompt_fmt = BotUtils.to_format( DxPlanEmoChatBot.PLAN_FMT )

        prompt = f"Current plan:\n{prompt_current_plan}\n\nConversation history:\n{prompt_history}\n\n上記を元に下記のフォーマットでプランを作って\n{prompt_fmt}"

        print( f"[DBG]plan prompt\n{prompt}" )
        res:str = self.Completion( prompt )
        print( f"[DBG]plan response\n{res}")
        new_plan:dict = BotUtils.parse_response( DxPlanEmoChatBot.PLAN_FMT, res )
        if new_plan is not None:
            BotUtils.update_dict( new_plan, self.plan_data )
        #---------------------------------
        new_plan_prompt:str = BotUtils.to_prompt(self.plan_data)
        new_plan_prompt = f"Current plan:\n{new_plan_prompt}"
        return super().create_prompt( prefix=new_plan_prompt, postfix=postfix )

def test():
    bot: DxPlanEmoChatBot = DxPlanEmoChatBot()
    debug_ui(bot)

if __name__ == "__main__":
    test()