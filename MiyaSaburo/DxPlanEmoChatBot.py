import time
import json
import traceback
import concurrent.futures
import queue
from concurrent.futures import ThreadPoolExecutor, Future
from DxBotUtils import BotCore, BotUtils, ToolBuilder
from DxChatBot import ChatMessage,DxChatBot
from DxEmoChatBot import DxEmoChatBot
from DxBotUI import debug_ui

_id_counter:int = 0
def next_id() -> int:
    global _id_counter
    id:int = _id_counter
    _id_counter += 1
    return id

class PlanBase:
    pass
class PlanDesire(PlanBase):
    pass
class PlanTarget(PlanBase):
    pass
class PlanAction(PlanBase):
    pass
class PlanBase:
    def _append(self,child:PlanBase)->None:
        self.child.append(child)
    def __init__(self,parent:PlanBase,title:str,goal:str=None,isTalk:bool=False):
        self.idx = next_id()
        self.parent: PlanBase = parent
        self.child: PlanBase = []
        if parent is not None:
            parent._append(self)
        self.talk:bool = isTalk
        self.done:bool = False
        self._stat = ""
        self.title = title
        self.goal = goal
    def _done_to_child(self) -> None:
        if self.child is not None:
            for c in self.child:
                c._done_to_child()
    def set_done(self) -> None:
        self._done_to_child()
        self.done = True
        if self.parent is not None:
            self.parent._notify_done()
    def _notify_done(self) -> None:
        if self.child is not None:
            for c in self.child:
                if not c.done:
                    return
        self.done = True
        if self.parent is not None:
            self.parent._notify_done()

    def __str__(self):
        return self.title
    def to_title(self) -> str:
        return f"{self.idx}){self.title}"
    def to_tree(self,*,indent=""):
        text:str = f"{indent}{self.title}) {self._stat}"
        for t in self.child:
            text = BotUtils.join_str( text, t.to_tree(indent=indent+"  "))
        return text
    def get_first_talk(self) -> PlanBase:
        if not self.done:
            if self.child is None or len(self.child)==0:
                if self.talk:
                    return self
            for c in self.child:
                t:PlanBase = c.get_first_talk()
                if t is not None:
                    return t
        return None

class PlanDesire(PlanBase):
    def __init__(self,title):
        super().__init__(None,title)

class PlanTarget(PlanBase):
    def __init__(self,desire:PlanDesire,title:str,goal:str=None):
        super().__init__(desire,title,goal=goal)

class PlanTask(PlanBase):
    def __init__(self,target:PlanBase,title,goal:str=None,isTalk:bool=False):
        super().__init__(target,title,goal=goal,isTalk=isTalk)

class DxPlanEmoChatBot(DxEmoChatBot):
    PLAN_FMT = {
        '欲求': 'やりたいことのリストを作って、その中から一番優先度が高いものを教えてください。',
        '目標': '欲求を満たすための計画を3つの項目でリスト形式にしてください。各項目の先頭には目標番号をT数字の形式で付けて下さい。)',
        '計画': '目標に基づいた行動計画を、リスト形式で示してください。各項目の先頭には、T数字-P数字の形式で付けて下さい。',
    }
    TASK_FMT = {
        '計画': 'このタスクがどの計画に対応しているか？',
        '作業内容': 'タスクで処理する内容、調べる内容、考える、話す内容など',
        '達成条件': 'タスクの完了を判定する条件など',
        '種別': 'NothingToDo, ResearchTask, ThinkingTask, TalkTaskから選択して下さい。'
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
        self._plan:list[PlanDesire] = []
        self._timer_talk_interval:float = 15.0

    #Override
    def eval_plan(self) -> None:

        now_dt = time.time()
        if (now_dt-self._last_plan_time)<300.0 and (len(self.mesg_list)-self._last_plan_hist)<10:
            # ５分以内、または、会話進行が１０未満なら更新しない
            return
        self._last_plan_time = now_dt
        self._last_plan_hist = len(self.mesg_list)

        prompt:str = ""

        profile = self.create_profile_prompt()
        if BotUtils.length(profile)>0:
            prompt = profile + "\n\n"

        prompt_current_plan = BotUtils.to_prompt( self.plan_data ) if len(self.plan_data)>0 else ""
        if BotUtils.length(prompt_current_plan)<=0:
            self.init_plan()
            return
        
        prompt += f"Your current plan:\n{prompt_current_plan}\n\n"

        prompt_history:str = ChatMessage.list_to_prompt( self.mesg_list + [self.next_message], assistant='You', user="User")
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

    def init_plan(self) -> None:
        """ プランを初期化する
        """
        message_list:list[dict] = []

        profile = BotUtils.join_str(self.create_prompt0(), self.create_profile_prompt(), sep="\n\n" )
        if profile is not None:
            message_list.append( ChatMessage.create_dict( ChatMessage.SYSTEM, profile) )
        message_list.append( ChatMessage.create_dict( ChatMessage.SYSTEM, f"今からプランを設定します。貴方がやりたいことから目標を設定し、目標からタスクを設定し、タスクを実行可能なアクションに分解します。アクションは、ネットを検索する、思考する、人間に問いかけるなどの貴方が実行可能なアクションでないといけません。" ))
        base_num:int = len(message_list)


        # 欲求を決める
        message_list.append( ChatMessage.create_dict( ChatMessage.USER, "貴方が今一番やりたいことはなんですか？簡潔なリスト形式で教えてください。" ))
        #print( f"[DBG]plan prompt\n{prompt2}" )
        res = self.ChatCompletion( message_list, stop=["\n","。"] )
        #print( f"[DBG]plan response\n{res}")
        text:str = BotUtils.strip_messageN( BotUtils.get_first_line(res) )
        print( f"[DBG]plan {text}")
        desire:PlanDesire = PlanDesire(text)

        message_list = message_list[:base_num]
        message_list.append( ChatMessage.create_dict( ChatMessage.SYSTEM, f"貴方が今一番やりたいこと: {desire}" ))

        message_list.append( ChatMessage.create_dict( ChatMessage.USER, "貴方がやりたいことから、３つの目標を設定して、簡潔なリスト形式で教えてください。" ))
        res = self.ChatCompletion( message_list )
        target_list = [ PlanTarget(desire,BotUtils.strip_messageN(l)) for l in res.splitlines()][:3]
        for target in target_list:
            
            message_list = message_list[:base_num]
            message_list.append( ChatMessage.create_dict( ChatMessage.SYSTEM, f"貴方が今一番やりたいこと: {desire}\n目標:{target}" ))
            message_list.append( ChatMessage.create_dict( ChatMessage.USER, "目標を達成するための作業を３つのタスクにして、簡潔なリスト形式で教えてください。" ))
            res = self.ChatCompletion( message_list )
            task_list = [ PlanTask(target,BotUtils.strip_messageN(l)) for l in res.splitlines()]

        self._plan.append(desire)
        print( f"[DBG] init \n{desire.to_tree()}")

    def get_first_talk(self) -> PlanTask:
        if self._plan is not None and len(self._plan)>0:
            return self._plan[0].get_first_talk()
        else:
            return None

    def tree_plan_init(self) -> None:

        if self._plan is not None and len(self._plan)>0:
            return

        print( f"[DBG] planを初期化します")
        desire:PlanDesire = PlanDesire("現在の状況を確認したい")
        target:PlanTarget = PlanTarget( desire, "状況を把握する" )
        task: PlanTask = PlanTask( target, "人間との会話から状況を把握する")
        action1: PlanTask = PlanTask( task, "人間に挨拶する","人間からの挨拶をもらう",isTalk=True)
        action2: PlanTask = PlanTask( task, "ショートトークを通じて状況を把握する","人間のセリフで状況を確認できた",isTalk=True)
        self._plan = [desire]

    def create_before_hist_prompt(self) -> str:

        self.tree_plan_init()
        
        desire:PlanDesire = self._plan[0]

        prompt:str = f"貴方の欲求:{str( desire )}"

        idx:int = 0
        for target in desire.child:
            if not target.done and not target.talk:
                if idx==0:
                    prompt = BotUtils.join_str(prompt,"貴方の目標:")
                prompt = BotUtils.join_str(prompt, f"  {target.to_title()}" )
                idx+=1
        talk:PlanTask = desire.get_first_talk()
        if talk is not None:
            prompt = BotUtils.join_str( prompt, f"会話の目的:{talk.title}")

        return prompt

    @staticmethod
    def replace_label( text:str ) -> str:
        a:str = text.replace("人間","User")
        a:str = a.replace("ユーザ","User")
        return a

    # 会話を評価する
    def _do_eval_talkX(self) -> None:
        xx:bool = False
        try:
            xAI: str = 'AI'
            xUser: str = 'User'
            xPromptKey: str = 'Prompt:'
            prompt0:str = f"貴方は、{xAI}と{xUser}の会話履歴から{xAI}が会話のゴールを満たしているかを判定するGPTです。"
            prompt_history:str = ChatMessage.list_to_prompt( self.mesg_list + [self.next_message], assistant=xAI, user=xUser)
            if len(prompt_history)<=0:
                prompt_history='まだ会話がありません'
            prompt0 = BotUtils.join_str( prompt0, "# 会話履歴", sep="\n\n")
            prompt0 = BotUtils.join_str( prompt0, prompt_history)

            prompt1:str = BotUtils.str_indent(
                f"""
                # {xAI}が会話のゴールを全て完全に満たしているかを以下の手順で回答して下さい。
                1) Thought:
                  1. ...
                  2. ...
                2) Observation:
                  1. ...
                  2. ...
                3) Judge:
                  {xAI}が会話のゴールを全て完全に満たしていたら YesYesYes 満たしてなければ NoNoNoを返して下さい。
                4) Answer:
                  YesYesYes or NoNoNo
                5) AI's next action :
                  AIはこの後の会話をどのように進めるべきでしょうか？
                6) {xPromptKey}
                  next actionの内容から、AIへの指示をAIが理解できるプロンプトにして下さい。
                  例)  ...するように...して下さい。
                """
            )

            #-----------------------------------------------------
            # 実行中会話タスクの終了判定
            #-----------------------------------------------------
            talk:PlanTask = self.get_first_talk()
            NextPrompt:str = None
            while talk is not None and prompt_history is not None and len(prompt_history)>0:
                prompt = prompt0
                prompt = BotUtils.join_str( prompt, f"# Assistantの会話のゴール",sep="\n\n")
                prompt = BotUtils.join_str( prompt, f"  1. {talk.title}")
                if BotUtils.length(talk.goal)>0:
                    prompt = BotUtils.join_str( prompt, f"  2. {talk.goal}")
                prompt = BotUtils.join_str( prompt, prompt1, sep="\n\n")
                print( f"[DBG]plan prompt\n{prompt}" )
                threads = [ { 'role': 'system', 'content': prompt}]
                #res:str = self.Completion( prompt )
                res:str = self.ChatCompletion( threads )
                print( f"[DBG]plan response\n{res}")
                yes:bool = res.find( "YesYesYes" )<0
                no:bool = res.find( "NoNoNo" )<0
                done:bool = not yes and no
                if not done:
                    print( f"[DBG] talk active: {talk.to_title()}")
                    p:int = res.find(xPromptKey)
                    if p>0:
                        x:str = BotUtils.strip_messageN( res[ p+len(xPromptKey):] )
                        if len(x)>0:
                            NextPrompt = x
                    break
                print( f"[DBG] talk done: {talk.to_title()}")
                talk.set_done()
                talk:PlanTask = self.get_first_talk()
            if talk is None:
                return
            print( f"[DBG] talk wait: {talk.to_title()}")

            if NextPrompt is None:
                return
            axx = False
            while not axx:
                if self.send_message( NextPrompt, role=ChatMessage.SYSTEM ):
                    axx = True
                else:
                     time.sleep(1.0)
            if False:
                #-----------------------------------------------------
                # 会話タスク開始のタイミング調整
                #-----------------------------------------------------
                while not xx:
                    with self.lock:
                        now_dt:float = time.time()
                        if (now_dt-self.last_user_message_time)<self._timer_talk_interval:
                            print( f"[DBG] talk wait: {talk.to_title()}")
                            return
                        if self.next_message is None:
                            self.next_message = ""
                            print( f"[NewTalk] Lock")
                            xx = True
                            break
                    print( f"[NewTalk] sleep 1")
                    time.sleep(1.0)
                #-----------------------------------------------------
                # 会話タスクを開始する
                #-----------------------------------------------------
                print( f"[DBG] talk next prompt: {NextPrompt}")
                prompt = BotUtils.join_str(self.create_prompt0(), self.create_profile_prompt(), sep="\n" )
                prompt = BotUtils.join_str( prompt, self.create_before_hist_prompt(), sep="\n\n" )
                if prompt_history is not None and len(prompt_history)>0:
                    prompt += f"Conversation history:\n{prompt_history}\n\n"
                prompt = BotUtils.join_str( prompt, "会話タスクを開始します。")
                prompt = BotUtils.join_str( prompt, "貴方の次のセリフ:", sep="\n\n")
                print( f"-------\n{prompt}\n------")
                ret:str = self.Completion( prompt )
                ret = BotUtils.strip_message(ret)
                ret = BotUtils.split_string(ret)[0]
                print(ret)
                with self.lock:
                    self.mesg_list.append( ChatMessage( ChatMessage.ASSISTANT, ret ) )
                emotion:int = 0
                if self.tts is not None:
                    self.tts.add_talk( ret, emotion )
                elif self._chat_callback is not None:
                    self._chat_callback( ChatMessage.ASSISTANT, ret, emotion )
        except:
            traceback.print_exc()
        finally:
            if xx:
                with self.lock:
                    self.next_message = None
                    print( f"[NewTalk] Unlock")

    def _do_eval_talk(self) -> None:
        try:
            self._do_eval_talkX()
        except:
            traceback.print_exc()
        finally:
            pass

    def _do_task(self) -> None:
        try:
            self.tree_plan_init()
            pass
        except:
            traceback.print_exc()
        finally:
            pass

    #Override
    def create_before_hist_prompt00(self) -> str:
        self.eval_plan()
        plan_text:str = BotUtils.to_prompt(self.plan_data)
        prompt = f"Current plan:\n{plan_text}"
        return prompt

    def timer_task(self) -> None:
        if self._task_feture is None or self._task_feture.done():
            self._task_feture = None
            now_dt = time.time()
            interval:float = (now_dt-self._last_task_time)
            talk:PlanTask = self.get_first_talk()
            if talk is not None:
                if interval > self._timer_talk_interval:
                    self._last_task_time = now_dt
                    self._task_feture = self.submit_task( self._do_eval_talk )
            else:
                if interval>180.0:
                    self._last_task_time = now_dt
                    self._task_feture = self.submit_task( self._do_task )
    
    def _do_taskX(self) -> None:
        try:
            self.eval_plan()
            # 基本とプロファイルをプロンプトに追加
            prompt = BotUtils.join_str(self.create_prompt0(), self.create_profile_prompt(), sep="\n" )
            # 現在のプランを提示
            plan = self.create_before_hist_prompt()
            prompt = BotUtils.join_str( prompt, plan, sep="\n\n" )

            prompt += "\n\n" + BotUtils.str_indent("""
                    1) 貴方が選択できる行動の種別は下記です。
                        NothingToDo: 今は何もしません。
                        ResearchTask: インターネットを使って何かを調べる。
                        ThinkingTask: LLMを使って何かを考える。
                        TalkTask: 人間と何かを話します。
                    """)
            prompt += f"\n\n2) 貴方の行動を選択して、以下のフォーマットで記述して下さい。"
            prompt += "\n" +BotUtils.to_format( DxPlanEmoChatBot.TASK_FMT )
            prompt += f"\n\n貴方の行動:"
            print( f"-------\n{prompt}\n------")
            ret:str = self.Completion( prompt )
            print(ret)
            if ret is None or len(ret.strip())==0:
                return
            task:dict = BotUtils.parse_response( DxPlanEmoChatBot.TASK_FMT, ret, fill=True )
            if task is None:
                print(f"[DBG] task is None" )
                return
            p:str = task.get('計画')
            plan_list: str = self.plan_data.get('計画')
            i:int = plan_list.find(p)
            if i<0:
                print(f"[DBG] task is invalid" )
                return
            self.plan_data['計画'] = plan_list[:i] + "【完了】" + plan_list[i:]

            self._do_start_Task( task )            
            # if ret.find("TalkTask")>=0:
            #     self._do_start_new_talk(ret)
            # else:
            #     self._do_start_new_talk(ret)
        except Exception as ex:
            traceback.print_exc()
        finally:
            self._task_feture = None

    def _do_start_Task(self,ret) -> None:
            # 基本とプロファイルをプロンプトに追加
            prompt = BotUtils.join_str(self.create_prompt0(), self.create_profile_prompt(), sep="\n" )
            # 現在のプランを提示
            prompt = BotUtils.join_str( prompt, self.create_before_hist_prompt(), sep="\n\n" )

    def _do_start_new_talk(self,ret) -> None:
        xx:bool = False
        try:
            while not xx:
                with self.lock:
                    if self.next_message is None:
                        self.next_message = ""
                        xx = True
                        print( f"[NewTalk] Lock")
                        break
                print( f"[NewTalk] sleep 1")
                time.sleep(1.0)

            prompt = BotUtils.join_str(self.create_prompt0(), self.create_profile_prompt(), sep="\n" )
            prompt = BotUtils.join_str( prompt, self.create_before_hist_prompt(), sep="\n\n" )
            prompt_history:str = ChatMessage.list_to_prompt( self.mesg_list )
            prompt += f"Conversation history:\n{prompt_history}\n\n"
            prompt = BotUtils.join_str( prompt, "会話タスクを開始します。")
            prompt = BotUtils.join_str( prompt, ret )
            prompt = BotUtils.join_str( prompt, "貴方の次のセリフ:", sep="\n\n")
            print( f"-------\n{prompt}\n------")
            ret:str = self.Completion( prompt )
            ret = BotUtils.strip_message(ret)
            ret = BotUtils.split_string(ret)[0]
            print(ret)
            with self.lock:
                self.mesg_list.append( ChatMessage( ChatMessage.ASSISTANT, ret ) )
            emotion:int = 0
            if self.tts is not None:
                self.tts.add_talk( ret, emotion )
            elif self._chat_callback is not None:
                self._chat_callback( ChatMessage.ASSISTANT, ret, emotion )
        except Exception as ex:
            traceback.print_exc()
        finally:
            if xx:
                with self.lock:
                    self.next_message = None
                    print( f"[NewTalk] Unlock")
def test():
    bot: DxPlanEmoChatBot = DxPlanEmoChatBot()
    debug_ui(bot)

def test2():
    bot: DxPlanEmoChatBot = DxPlanEmoChatBot()
    tools = [
        ToolBuilder('abcde')
            .param('purposeOfConversation1','会話の目的')
            .param('purposeOfConversation2','言い換えた会話の目的')
            .build()
    ]
    mesg_thread = []
    mesg_thread.append( { 'role': 'user', 'content': BotUtils.str_indent(
                """
                会話の目的:
                  人間と挨拶をする

                会話内容から会話の目的を達成したか判定する疑問文を３項目。客観的な判定基準で簡潔な疑問形にすること。会話の順番で並べて。
                確認項目を達成する為のLLMへの指示
                以下のフォーマットにして下さい
                # 目的
                  ...
                # 確認項目
                  1) ...
                  2) ...
                  3) ...
                # LLMへの指示
                  1) ...
                  2) ...
                  3) ...
                """)})

    ret = bot.ChatCompletion( mesg_thread )
    if ret is None:
        return
    mesg_thread.append( { 'role': 'assistant', 'content': ret })

    if isinstance(ret,list):
        for fn in ret:
            fn_name = fn.name
            fn_args = json.loads( fn.arguments) 
            print( f"function {fn_name}  args={fn_args}")
    else:
        print( f"REt:{ret}")

if __name__ == "__main__":
    test()