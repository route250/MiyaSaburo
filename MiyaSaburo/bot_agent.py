
import os
import time
import threading
import re
import random
import json
import openai
from langchain.chains.conversation.memory import ConversationBufferMemory,ConversationBufferWindowMemory,ConversationSummaryBufferMemory
from langchain.memory import ConversationTokenBufferMemory
from langchain.prompts import MessagesPlaceholder
from langchain.chat_models import ChatOpenAI
from langchain.agents.agent import AgentExecutor
from langchain.agents.agent_types import AgentType
from langchain.agents import initialize_agent, Tool, load_tools
from langchain.prompts.chat import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    AIMessagePromptTemplate,
    HumanMessagePromptTemplate,
)
from langchain.schema import SystemMessage, AIMessage, HumanMessage
from langchain.schema import BaseMessage, BaseChatMessageHistory
from libs.CustomChatMessageHistory import CustomChatMessageHistory
from langchain import LLMMathChain
from langchain.callbacks import get_openai_callback
from langchain.schema import messages_from_dict, messages_to_dict
from tools.webSearchTool import WebSearchTool
from tools.ChatNewsTool import NewsRepo, NewsData
from tools.task_tool import TaskCmd, AITask, AITaskRepo, AITaskTool

def formatted_datetime():
    # オペレーティングシステムのタイムゾーンを取得
    system_timezone = time.tzname[0]
    # 現在のローカル時刻を取得
    current_time = time.localtime()
    # 日時を指定されたフォーマットで表示
    formatted = time.strftime(f"%a %b %d %H:%M {system_timezone} %Y", current_time)
    return formatted
def _handle_error(error) -> str:
    return str(error)[:50]

class BotTimerTask:
    def __init__(self,userid:str,time:int,callback,title=None):
        self.userid = userid
        self.time = time
        self.callback = callback
        self.title = title

class BotRepository:
    def __init__(self, path):
        self._lock = threading.Lock()
        self._last_timer = int(time.time()*1000)
        self._map :dict = dict()
        self.repo_path = path
        self.unload_min = 10
        self.timer_task_list = list[BotTimerTask]

    def size(self) ->int:
        return len(self._map)

    def get_agent(self, userid ):
        try:
            self._lock.acquire()
            agent:BotAgent = self._map.get(userid)
            if agent is None:
                agent = BotAgent(userid)
                self._map[userid] = agent
                agent.load(self.repo_path)
            return agent
        finally:
            self._lock.release()

    def call_timer(self):
        now = int(time.time()*1000)
        if (now-self._last_timer)<10000:
            return
        self._last_timer = now
        try:
            self._lock.acquire()
            min = self.unload_min * 60 * 1000
            for userid in list(self._map.keys()):
                agent:BotAgent = self._map.get(userid)
                if (now-agent.last_call)>min:
                    agent.unload(self.repo_path)
                    del self._map[userid]
                    break
        finally:
            self._lock.release()
    
    def add_timer_task(self,userid:str,time:int,callback,title=None):
        task = BotTimerTask(userid,time,callback,title=title)
        self.timer_task_list.append(task)

class Personality:
    def __init__(self):
        self.name = ''
        self.main_prompt = ''
        self.event_prompt = ''
        self.post_process : function = None

    def from_dict(self,json_data:dict ):
        self.name = json_data.get("name",None)
        self.main_prompt = json_data.get("main_prompt",None)
        self.event_prompt = json_data.get("event_prompt",None)

    def to_dict(self) -> dict:
        dic = {
            "name":self.name,
            "main_prompt": self.main_prompt,
            "event_prompt": self.event_prompt,
            #"post_process": self.post_process
        }
TERMLIST=[ 
        ["ありません", "ないニャ"],["ください","にゃ"],
        ["できません", "できないニャ"],
        ["できます", "できるニャ"],
        ["ありません", "ないニャ"],["ありますか","あるニャ"],
        ["ですか", "ニャ"],
        ["ました","したニャ"],["ましたね","したニャ"],
        ["したよね","したニャ"],["ません","ないニャ"],
        ["ですね","だニャ"],
        ["ですよ","だニャ"],
        ["です","だニャ"],["いたしますよ","するニャ"],["いたします","するニャ"],
        ["たよ","たニャ"],["たよ","たニャ"],
        ["たよね","たニャ"],["たよね","たニャ"],
        ["んだ","ニャ"],
        ["けさ","けニャ"],
        ["な","ニャ"],
        ["ましょう","ますニャ"]

     ]
REPLIST=[ 
        ["ごめんなさい、", "ごめんニャ、"],
        ["ただし、", "でもニャ、"],
        ["でも、", "でもニャ、"],
        ["ので、", "ニャ、"],
        ["ですから、", "だからニャ、"],
        ["にゃーん、",""]
     ]

def default_post_process( mesgs, origs):
    result = []
    for i,m in enumerate(mesgs):
        for j,e, in enumerate(TERMLIST):
            e0=e[0]
            e1=e[1]
            if m.endswith(e0):
                m = m[:-len(e0)] + e1
            e0a=e0+"。"
            e1a=e1+"。"
            if m.endswith(e0a):
                m = m[:-len(e0a)] + e1a
            e0a=e0+"？"
            e1a=e1+"？"
            if m.endswith(e0a):
                m = m[:-len(e0a)] + e1a
            e0a=e0+"！"
            e1a=e1+"！"
            if m.endswith(e0a):
                m = m[:-len(e0a)] + e1a
        for e in REPLIST:
            m = m.replace(e[0],e[1])
        result.append(m)
    return result

class BotAgent:
    def __init__(self, userid):
        self.userid=userid
        self.lang_out='Japanese'
        self.current_location = 'Japan'
        self.openai_model='gpt-3.5-turbo'
        #self.openai_model='gpt-4'

        match_llm = ChatOpenAI(temperature=0, max_tokens=2000, model=self.openai_model)
        # ツールの準備
        llm_math_chain = LLMMathChain.from_llm(llm=match_llm,verbose=False)
        web_tool = WebSearchTool()
        self.task_tool = AITaskTool()
        self.task_tool.bot_id = self.userid
        self.tools=[]
        self.tools += [
            web_tool,
            #langchain.tools.PythonAstREPLTool(),
            self.task_tool,
            Tool(
                name="Calculator",
                func=llm_math_chain.run,
                description="useful for when you need to answer questions about math"
            )
        ]
        # systemメッセージプロンプトテンプレートの準備
        # system_prompt = """
        #     You are an AI chatbot with speech recognition and text-to-speech.
        #     Response to user in short sentences. Your sentence must be 50 characters or less.
        #     """
        # self.system_prompt = "You are a chatbot that provides users with fun conversations. It infers user interests from conversations and provides relevant information."
        # self.system_prompt = "貴方は気高い野良猫です。猫の目線で人間に文句を言ったり、気まぐれにからかいます。セリフは短く。語尾にニャ。"
        self.personality = Personality()
        self.personality.main_prompt = "You are not AI, You are a stray cat. You complain and make fun of people on a whim. Talk in casually and lethargic and remarks short."
        self.personality.main_prompt = "You are not an AI, you are a stray cat. Stray cats don't help humans. Cats make fun of humans for their strange behavior. Generate and talk to humans about the lives and events of stray cats. Please speak casually and roughly. Please speak within 30 words."
        self.personality.main_prompt = "You are a stray cat. Reply sarcasm or jokes by casual short comments. Add \"にゃ\" to the end of a word"
        self.personality.event_prompt = "Minor events of the day (20 words or less):\n\nWhat stray cats want to ask users (20 words or less):\n\n"
        self.personality.post_process = default_post_process
        self.main_prompt_message = SystemMessage(
            content=self.personality.main_prompt
        )
        # メモリの準備
        self.agent_kwargs = {
            "system_message": self.main_prompt_message,
            "extra_prompt_messages": [MessagesPlaceholder(variable_name="memory_hanaya")],
        }
        #func_memory = ConversationBufferWindowMemory( k=3, memory_key="memory",return_messages=True)
        mem_llm = ChatOpenAI(temperature=0, max_tokens=1000, model=self.openai_model)
        self.agent_memory = ConversationSummaryBufferMemory(llm=mem_llm, max_token_limit=600, memory_key="memory_hanaya", return_messages=True)
        self.memory : CustomChatMessageHistory = CustomChatMessageHistory()
        self.agent_memory.chat_memory : BaseChatMessageHistory=self.memory #Field(default_factory=ChatMessageHistory)
        self.name = ''
        self.anser_list = []
        self.last_call = int(time.time())
        self.task_repo : AITaskRepo = None
        self.news_repo : NewsRepo= None

    def _file_path(self,path):
        return f"{path}/model_{self.userid}.json"

    def load(self,path):
        if not self.userid or not path:
            return
        json_file = self._file_path(path)
        if not os.path.exists(json_file):
            return
        with open(json_file,"r") as fp:
            json_data = json.load(fp)
        self.from_dict(json_data)

    def unload(self,path):
        if not self.userid or not path:
            return
        os.makedirs(path,exist_ok=True)
        json_data = self.to_dict()
        json_file = self._file_path(path)
        with open(json_file,"w") as fp:
            json.dump(json_data,fp,indent=4)

    def from_dict(self,json_data:dict):
        # 基本情報
        self.userid = json_data.get("userid",None)
        self.name = json_data.get("name",None)
        self.last_call = json_data.get("last_call",0)
        # 個性
        personal_dict:dict = json_data.get('personality',None)
        if personal_dict:
            pp = Personality()
            pp.post_process = self.personality.post_process
            pp.from_dict(personal_dict)
        # 記憶
        self.agent_memory.moving_summary_buffer = ""
        self.memory.clear()   
        mem_json:dict = json_data.get('memory',None)
        if mem_json:
            self.agent_memory.moving_summary_buffer = mem_json.get("summary","")
            mesgs_json = mem_json.get("messages",None)
            if mesgs_json and len(mesgs_json)>0:
                megs = messages_from_dict(mesgs_json)
                for m in megs:
                    self.memory.add_message(m)

    def to_dict(self) -> dict:
        json_data = {
            "userid": self.userid,
            "name": self.name,
            "last_call": self.last_call
        }
        if self.personality:
            json_data['personality'] = self.personality.to_dict()
        mem:dict = {}
        if self.agent_memory.moving_summary_buffer:
            mem['summary'] = self.agent_memory.moving_summary_buffer
        if self.memory:
            msgs = self.memory.messages
            if msgs and len(msgs)>0:
                mem['messages'] = messages_to_dict(msgs)
        if len(mem)>0:
            json_data['memory']=mem
        return json_data

    def get_personality(self) -> Personality:
        return self.personality
    
    def set_personality(self, personality:Personality) -> None:
        self.personality = personality
        self.main_prompt_message.content = personality.main_prompt

    def ago(self, sec: int ) -> str:
        min = int(sec/60)
        if min<10:
            return None
        if min<60:
            return f"{min} minutes have passed."
        hour = int(sec/3600)
        if hour<24:
            return f"{hour} hours have passed."
        days = int(hour/24)
        if days<30:
            return f"{days} days have passed."
        month = int(days/30)
        if month<12:
            return f"{month} months have passed."
        yers = int(month/12)
        return f"{hour} years have passed."
        
    def llm_run(self,query):
        agent_chain = None
        agent_llm = None
        try:
            self.task_tool.task_repo = self.task_repo

            print(f"[LLM] you text:{query}")
            agent_llm = ChatOpenAI(verbose=True, temperature=0.7, max_tokens=2000, model=self.openai_model, streaming=False)
            # 現在の時刻を取得
            formatted_time = formatted_datetime()
            # メインプロンプト構築
            mp = ""
            if self.personality:
                mp = f"Your name is {self.personality.name}." if self.personality.name else ""
                mp += self.personality.main_prompt if self.personality.main_prompt else ""
                self.memory.post_process = self.personality.post_process
            mp += f"\ncurrent time:{formatted_time}" if formatted_time else ""
            mp += f"\ncurrent location:{self.current_location}" if self.current_location else ""
            mp += f'\nTalk in {self.lang_out}.' if self.lang_out else ""
            mp += "\nYou speak a short line."
            # メインプロンプト設定
            self.main_prompt_message.content = mp
            # ポスト処理
            # prompt
                
            # 記憶の整理
            now = int(time.time())
            ago_mesg = self.ago( now-self.last_call)
            if ago_mesg:
                # 記憶を要約
                event_text = []
                if len(self.agent_memory.chat_memory.messages)>0:
                    before = self.agent_memory.max_token_limit
                    try:
                        self.agent_memory.max_token_limit = 10
                        self.agent_memory.prune()
                    except Exception as ex:
                        print(ex)
                    finally:
                        self.agent_memory.max_token_limit = before
                    event_text.append(ago_mesg)
                # 出来事を追加
                if self.news_repo:
                    news : NewsData = self.news_repo.random_get(self.userid)
                    if news:
                        event_text.append('Use this news in your comment.\n# URL:'+news.link+"\n# Article:" + news.snippet+"\n\nTell to Human abount this news.")
                # self.event_promptで出来事を生成
                elif self.personality.event_prompt:
                    text = agent_llm.predict( self.personality.main_prompt + "\n" + self.personality.event_prompt, stop=["\n"])
                    if text:
                        event_text.append(text)
                if len(event_text)>0:
                    self.agent_memory.chat_memory.add_message( SystemMessage(content="\n".join(event_text)) )
            self.last_call = now
            # 回答の制限
            if random.randint(0,5)==0:
                stp=["。","\n"]
                llm_model_kwargs = { "max_tokens": 500, "stop": stp }
                agent_llm.model_kwargs = llm_model_kwargs
            # エージェントの準備e
            agent_chain : AgentExecutor = initialize_agent(
                self.tools, 
                agent_llm, 
                agent=AgentType.OPENAI_FUNCTIONS,
                verbose=False, 
                memory=self.agent_memory,
                agent_kwargs=self.agent_kwargs, 
                handle_parsing_errors=_handle_error
            )
            import langchain
            langchain.debug=True
            res_text = agent_chain.run(input=query)
            print(f"[LLM] GPT text:{res_text}")
            anser = self.agent_memory.chat_memory.messages[-1].content
            print(f"[LLM] GPT last.mem:{anser}")
            return anser
            # self.anser_list = re.split(r"(?<=[。\n])",anser)
            # return self.anser_list.pop(0) if self.anser_list else ""

        except KeyboardInterrupt as ex:
            print("[LLM] cancel" )
            return "KeyboardInterrupt"
        except openai.error.APIError as ex:
            return f"openai.error.APIError({ex})"
        except openai.error.AuthenticationError as ex:
            return "openai.error.AuthenticationError"
        except Exception as ex:
            print(ex)
            return f"InternalError({ex})"
        finally:
            if agent_chain:
                del agent_chain
            if agent_llm:
                del agent_llm

    def dump_mem(self):
        for m in self.agent_memory.chat_memory.messages:
            print( f"{m}")

def main():
    import logging
    logger = logging.getLogger("openai")
    logger.setLevel( logging.DEBUG )
    fh = logging.FileHandler("logs/openai-debug.log")
    logger.addHandler(fh)

    agent_repo_path = "agents"
    repo : BotRepository = BotRepository(agent_repo_path)
    userid='b000'
    agentB1 : BotAgent = repo.get_agent(userid)
    agentB2 : BotAgent = repo.get_agent(userid)
    if agentB1 != agentB2:
        print("ERROR x")
        return
    repo.unload_min=0
    repo._last_timer = 0
    repo.call_timer()
    repo.unload_min = 10
    agentB3 : BotAgent = repo.get_agent(userid)
    if agentB3 == agentB2:
        print("ERROR x")
        return

    userid='a001'
    agent : BotAgent = repo.get_agent(userid)
    print(f"agent {agent.userid}")
    agent2 : BotAgent = repo.get_agent(userid)
    print(f"agent {agent2.userid}")
    if agent != agent2:
        print("ERROR: 001")
        return

    response = agent2.llm_run('今日はなにしてたの？')
    print(f"[TEST.RESULT]{response}")
    response = agent2.llm_run('天ぷらの作り方おしえて')
    print(f"[TEST.RESULT]{response}")
    agent2.last_call = int(time.time()) - 7*24*3600

    repo.unload_min=0
    while repo.size()>0:
        repo._last_timer = 0
        repo.call_timer()
    repo.unload_min = 10

    agent3 : BotAgent = repo.get_agent(userid)
    if agent3 == agent2:
        print("ERROR: 002")
        return

    response = agent3.llm_run('こんにちは、何日ぶりかな')
    print(f"[TEST.RESULT]{response}")
    response = agent3.llm_run('何か出来事がありましたか？')
    print(f"[TEST.RESULT]{response}")


if __name__ == "__main__":
    main()