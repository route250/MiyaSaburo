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
        '欲求': '貴方のしたい事を一つだけ挙げて下さい。',
        '目標': '欲求を満たすための目標を3項目のリスト形式で',
        '計画': '目標に従って行動計画をリスト形式で',
    }
    def __init__(self):
        super().__init__()
        self.plan_data:dict = {}
        for key in DxPlanEmoChatBot.PLAN_FMT.keys():
            self.plan_data[key] = 'no plan'

    #Override
    def eval_plan(self) -> str:
        prompt:str = ""

        profile = self.create_promptA()
        if BotUtils.length(profile)>0:
            prompt = profile + "\n\n"

        prompt_current_plan = BotUtils.to_prompt( self.plan_data )
        if BotUtils.length(prompt_current_plan)>0:
            prompt += f"Your current plan:\n{prompt_current_plan}\n\n"

        prompt_history:str = ChatMessage.list_to_prompt( self.mesg_list + [self.chat_busy])
        if BotUtils.length(prompt_history)>0:
            prompt += f"Conversation history:\n{prompt_history}\n\n"

        prompt_fmt = BotUtils.to_format( DxPlanEmoChatBot.PLAN_FMT )
        prompt += f"Please update your (i.e. {ChatMessage.ASSISTANT}'s) plan in the following format:\n{prompt_fmt}"

        print( f"[DBG]plan prompt\n{prompt}" )
        self.notify_log(prompt)
        res:str = self.Completion( prompt )
        self.notify_log(res)
        print( f"[DBG]plan response\n{res}")
        new_plan:dict = BotUtils.parse_response( DxPlanEmoChatBot.PLAN_FMT, res )
        if new_plan is not None:
            BotUtils.update_dict( new_plan, self.plan_data )
            self.update_info( {'plan':self.plan_data } )
    #Override
    def create_promptB(self) -> str:
        self.eval_plan()
        plan_text:str = BotUtils.to_prompt(self.plan_data)
        prompt = f"Current plan:\n{plan_text}"
        return prompt
def test():
    bot: DxPlanEmoChatBot = DxPlanEmoChatBot()
    debug_ui(bot)

if __name__ == "__main__":
    test()