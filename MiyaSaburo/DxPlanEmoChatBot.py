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
        'タイトル': '実行するタスクのタイトル',
        '作業内容': 'タスクで処理する内容、調べる内容、考える内容など',
        '達成条件': 'タスクの完了を判定する条件など'
    }
    TALK_FMT = {
        'タイトル': '会話のタイトル',
        'トピック': '何について会話するか？',
        '達成条件': '会話の目的、完了を判定する条件など'
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
            prompt += f"You have just started up as an AI. Please perform the initial settings. Conversational AI creates an executable action plan based on the profile above.\n{prompt_fmt}"

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

            prompt += f"\n\n1) 貴方の行動を、NothingToDo, StartNewTask, StartNewTalk から選択して下さい。\n貴方の行動:"

            prompt += f"\n\n2) NothinToDoを選択した場合は、ここで終了です。"
            prompt += f"\n\n3) StartNewTaskを選択した場合は、以下のフォーマットで内容を記述して下さい。"
            prompt += "\n" +BotUtils.to_format( DxPlanEmoChatBot.TASK_FMT )
            prompt += f"\n\n4) StartNewTalkを選択した場合は、以下のフォーマットで内容を記述して下さい。"
            prompt += "\n" +BotUtils.to_format( DxPlanEmoChatBot.TALK_FMT )
            prompt += f"\n\n貴方の行動:"
            print( f"-------\n{prompt}\n------")
            ret:str = self.Completion( prompt )
            print(ret)
            if ret is None or len(ret.strip())==0:
                return
            if ret.find("StartNewTalk")>=0:
                self._do_start_new_talk(ret)

        except Exception as ex:
            traceback.print_exc()
        finally:
            self._task_feture = None

    def _do_start_new_talk(self,ret) -> None:
        xx:bool = False
        try:
            while not xx:
                with self.lock:
                    if self.chat_busy is None:
                        self.chat_busy = ""
                        xx = True
                        break
                print( f"[NewTalk] sleep 1")
                time.sleep(1.0)

            prompt = BotUtils.join_str(self.create_prompt0(), self.create_promptA(), sep="\n" )
            prompt = BotUtils.join_str( prompt, self.create_promptB(), sep="\n\n" )
            prompt_history:str = ChatMessage.list_to_prompt( self.mesg_list )
            prompt += f"Conversation history:\n{prompt_history}\n\n"
            prompt = BotUtils.join_str( prompt, "会話タスクを開始します。")
            prompt = BotUtils.join_str( prompt, ret )
            prompt = BotUtils.join_str( prompt, "貴方の次のセリフ:", sep="\n\n")
            print( f"-------\n{prompt}\n------")
            ret:str = self.Completion( prompt )
            print(ret)
            with self.lock:
                self.mesg_list.append( ChatMessage( ChatMessage.ASSISTANT, ret ) )
            emotion:int = 0
            if self.talk_engine is not None:
                self.talk_engine.add_talk( ret, emotion )
            elif self.chat_callback is not None:
                self.chat_callback( ChatMessage.ASSISTANT, ret, emotion )
        except Exception as ex:
            traceback.print_exc()
        finally:
            if xx:
                with self.lock:
                    self.chat_busy = None
def test():
    bot: DxPlanEmoChatBot = DxPlanEmoChatBot()
    debug_ui(bot)

if __name__ == "__main__":
    test()