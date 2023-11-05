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
        '欲求': 'ただ一つの、貴方のしたい事',
        '目標': '欲求を満たすための目標を3項目のリスト形式で',
        '計画': '目標に従って行動計画をリスト形式で',
    }
    TASK_FMT = {
        'title': 'identify to task',
        'what_to_do': 'What this task does',
        'goal': 'Goals to be achieved, results to be achieved'
    }
    def __init__(self):
        super().__init__()
        self.plan_data:dict = {}
        self._last_plan_time:float = 0
        self._last_plan_hist:int = 0
        self._last_task_time:float = 0
        self._task_feture: Future = None

    #Override
    def eval_plan(self) -> None:

        now_dt = time.time()
        if (now_dt-self._last_plan_time)<300.0 and (len(self.mesg_list)-self._last_plan_hist)<10:
            # ５分以内、または、会話進行が１０未満なら更新しない
            return
        self._last_plan_time = now_dt
        self._last_plan_hist = len(self.mesg_list)

        prompt:str = ""

        profile = self.create_promptA()
        if BotUtils.length(profile)>0:
            prompt = profile + "\n\n"

        prompt_current_plan = BotUtils.to_prompt( self.plan_data ) if len(self.plan_data)>0 else ""
        if BotUtils.length(prompt_current_plan)>0:
            prompt += f"Your current plan:\n{prompt_current_plan}\n\n"

        prompt_history:str = ChatMessage.list_to_prompt( self.mesg_list + [self.chat_busy], assistant='You', user="User")
        if BotUtils.length(prompt_history)>0:
            if prompt_history.find("You:")>0:
                if prompt_history.find("User:")>0:
                    prompt += f"Conversation history:\n{prompt_history}\n\n"
                else:
                    prompt += f"What you said:\n{prompt_history}\n\n"
            else:
                if prompt_history.find("User:")>0:
                    prompt += f"What users said:\n{prompt_history}\n\n"

        prompt_fmt = BotUtils.to_format( DxPlanEmoChatBot.PLAN_FMT )
        if BotUtils.length(prompt_current_plan)>0:
            prompt += f"As a conversational AI, update your own plans according to your profile above.\n{prompt_fmt}"
        else:
            prompt += f"You have just started up as an AI. Please perform the initial settings. Create your action plan based on the profile above.\n{prompt_fmt}"

        print( f"[DBG]plan prompt\n{prompt}" )
        res:str = self.Completion( prompt )
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

    def timer_task(self) -> None:
        now_dt = time.time()
        if self._task_feture is None and (now_dt-self._last_task_time)>180.0:
            self._task_feture = self.submit_task( self._do_task )
            self._last_task_time = now_dt
    
    def _do_task(self) -> None:
        try:
            self.eval_plan()

            prompt = BotUtils.join_str(self.create_prompt0(), self.create_promptA(), sep="\n" )

            prompt = BotUtils.join_str( prompt, self.create_promptB(), sep="\n\n" )

            prompt += f"\n\nBased on the above plan, if you have any tasks to perform, write them in the format below. If not, nothing will be returned.\n"
            prompt += BotUtils.to_format( DxPlanEmoChatBot.TASK_FMT )
            ret:str = self.Completion( prompt )
            print(ret)
        except Exception as ex:
            traceback.print_exc()
        finally:
            self._task_feture = None

def test():
    bot: DxPlanEmoChatBot = DxPlanEmoChatBot()
    debug_ui(bot)

if __name__ == "__main__":
    test()