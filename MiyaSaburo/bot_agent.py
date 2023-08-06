
import json
import os
import random
import re
import threading
import time
import logging
from logging.handlers import TimedRotatingFileHandler
import typing
from typing import (
    Any,
    AsyncIterator,
    Dict,
    Iterator,
    List,
    Optional,
    Sequence,
    cast,
)
from json import JSONDecodeError
import openai
import langchain
from langchain import LLMMathChain
from langchain.agents import Tool, initialize_agent, load_tools, OpenAIFunctionsAgent
from langchain.agents.agent import AgentExecutor
from langchain.agents.agent_types import AgentType
from langchain.callbacks import get_openai_callback
from langchain.chains.conversation.memory import (
    ConversationBufferMemory, ConversationBufferWindowMemory,
    ConversationSummaryBufferMemory)
from langchain.chat_models import ChatOpenAI
from langchain.memory import ConversationTokenBufferMemory
from langchain.prompts import PromptTemplate,MessagesPlaceholder
from langchain.prompts.chat import (AIMessagePromptTemplate,
                                    ChatPromptTemplate,
                                    HumanMessagePromptTemplate,
                                    SystemMessagePromptTemplate)
from langchain.schema import (OutputParserException, AIMessage, BaseChatMessageHistory, BaseMessage,
                              HumanMessage, SystemMessage, messages_from_dict,
                              messages_to_dict)
from libs.extends_chatopenai import ExChatOpenAI
from libs.CustomChatMessageHistory import CustomChatMessageHistory
from tools.ChatNewsTool import NewsData, NewsRepo
from tools.task_tool import AITask, AITaskRepo, AITaskTool, TaskCmd
from tools.webSearchTool import WebSearchTool
from libs.utils import Utils

from libs.bot_model import AbstractBot
from libs.logging_callback_handler import LoggerCallbackHdr
from libs.extends_memory import ExtConversationSummaryBufferMemory

langchain.debug=False
logger = logging.getLogger('BotAgent')

class BotTimerTask:
    def __init__(self,userid:str,time:int,callback,title=None):
        self.userid = userid
        self.time = time
        self.callback = callback
        self.title = title

class BotRepository:
    def __init__(self, path):
        self._cv = threading.Condition()
        self._last_timer_sec = int(time.time())
        self._agent_map :dict[str,BotAgent] = dict()
        self._summarize_map: dict[str,float] = dict()
        self.repo_path = path
        self.unload_min = 1
        self.summarize_min = self.unload_min + 1
        self.timer_task_list = list[BotTimerTask]

    def size(self) ->int:
        return len(self._agent_map)

    def get_agent(self, userid: str ):
        with self._cv:
            agent:BotAgent = self._agent_map.get(userid)
            if agent is None:
                agent = BotAgent(userid)
                agent.logger.setLevel(logging.DEBUG)
                self._agent_map[userid] = agent
                agent.load(self.repo_path)
            self.load_time_sec = int(time.time())
            self.configure_agent(agent)
            return agent

    def configure_agent(self, agent ):
                # system_prompt = """
        #     You are an AI chatbot with speech recognition and text-to-speech.
        #     Response to user in short sentences. Your sentence must be 50 characters or less.
        #     """
        # self.system_prompt = "You are a chatbot that provides users with fun conversations. It infers user interests from conversations and provides relevant information."
        # self.system_prompt = "貴方は気高い野良猫です。猫の目線で人間に文句を言ったり、気まぐれにからかいます。セリフは短く。語尾にニャ。"
        # self.personality = Personality()
        # self.personality.main_prompt = "You are not AI, You are a stray cat. You complain and make fun of people on a whim. Talk in casually and lethargic and remarks short."
        # self.personality.main_prompt = "You are not an AI, you are a stray cat. Stray cats don't help humans. Cats make fun of humans for their strange behavior. Generate and talk to humans about the lives and events of stray cats. Please speak casually and roughly. Please speak within 30 words."
        # self.personality.main_prompt = "You are a stray cat. Reply sarcasm or jokes by casual short comments. Add \"にゃ\" to the end of a word"
        # self.personality.event_prompt = "Minor events of the day (20 words or less):\n\nWhat stray cats want to ask users (20 words or less):\n\n"
        agent.main_prompt = "You are a stray cat. Reply sarcasm or jokes by casual short comments. Add \"にゃ\" to the end of a word. Current date is {current_datetime}"


    def call_timer(self):
        now_sec = int(time.time())
        if (now_sec-self._last_timer_sec)<10:
            return
        self._last_timer_sec = now_sec
        with self._cv:
            # ---
            unload_sec = self.unload_min * 60
            for userid in list(self._agent_map.keys()):
                agent:BotAgent = self._agent_map.get(userid)
                if (now_sec-agent.last_call_sec)>unload_sec and (now_sec-agent.load_time_sec)>unload_sec:
                    self._summarize_map[userid] = agent.last_call_sec
                    agent.unload(self.repo_path)
                    del self._agent_map[userid]
                    return
            # ---
            summarize_sec = self.summarize_min * 60
            for userid in list(self._summarize_map.keys()):
                last_call = self._summarize_map[userid]
                if (now_sec-last_call)>summarize_sec:
                    agent = self.get_agent(userid)
                    agent.summarize()
                    agent.last_call_sec = last_call
                    agent.unload(self.repo_path)
                    del self._agent_map[userid]
                    del self._summarize_map[userid]
                    return
    
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

class ToneV:

    _IGNORE_WORDS = (
        "お手伝いできますか",
        "お手伝いができますか",
        "お手伝いがあれば教えてください",
        "お手伝いできることがあれば教えてください",
        "お手伝いできることはありますか",
        "お手伝いいたします",
        "お手伝いできることがあればお知らせください",
        "お手伝いできるかもしれません",
        "お手伝いできるかと思います",

        "お知らせください",
        "お聞きください",
        "お聞かせください",
        "お話しください",
        "困っているのか教えてください", "お困りですか",
        "教えていただけますか",
        "お話を教えてください",

        "お話しましょうか","お話しすることはありますか？",

        "質問があればどうぞ","何か質問がありますか"

        "どんなことでも結構ですよ",

        "頑張ってください", "応援しています",
        "何か特別な予定はありますか",
        "お申し付けください",
        "伝いが必要な場合はお知らせください",
        "遠慮なくお知らせください",
        "サポートいたします",
        "良い一日をお過ごしください",

        "サイトで確認してください",
        "願っています",
        "計画はありますか",

        "話したいことある",
        "助けが必要か"
        )
    _IGNORE_TUPLE = tuple( set(_IGNORE_WORDS) )
    _pattern = re.compile(r"[、？！]")
    _split_re = re.compile(r"([。！])")

    @staticmethod
    def _is_ignore_word(message:str) -> str:
        buf = ToneV._pattern.sub("", message.strip("  。\n"))
        return buf.endswith(ToneV._IGNORE_TUPLE)

    @staticmethod
    def tone_convert(message: str, post_process : typing.Callable = None) -> str:
        # lines0 = re.split(r"(?<=[\n])",message0)
        # message = lines0[0]
        lines = re.split(r"(?<=[。！\n])",message)
        results = [line for line in lines if not ToneV._is_ignore_word(line)]
        if post_process is not None:
            results = post_process(results,lines)
        return "".join(results) if results else "".join(lines)

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
#天ぷらの作り方について調べてみましたが、情報が見つかりませんでしたにゃ。他の質問に答えることはできるかもしれません。何か他の質問はありますか？
        ]
    REPLIST=[ 
            ["ごめんなさい、", "ごめんニャ、"],
            ["ただし、", "でもニャ、"],
            ["でも、", "でもニャ、"],
            ["ので、", "ニャ、"],
            ["ですから、", "だからニャ、"],
            ["にゃーん、",""]
        ]
    @staticmethod
    def default_post_process( mesgs, origs):
        result = []
        for i,m in enumerate(mesgs):
            for j,e, in enumerate(ToneV.TERMLIST):
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
            for e in ToneV.REPLIST:
                m = m.replace(e[0],e[1])
            result.append(m)
        return result

class BotAgent(AbstractBot):
    REQUEST_TIMEOUT=30
    def __init__(self, userid:str):
        super().__init__( user_id = userid )
        self.userid=userid
        self.lang_out='Japanese'
        self.current_location = 'Japan'
        self.openai_model='gpt-3.5-turbo'
        #self.openai_model='gpt-4'

        self.name = ''
        self.main_prompt = ""
        self.event_prompt = ""
        # callback
        self.callback_list = [ LoggerCallbackHdr(self) ]

        # ツールの準備
        match_llm = ChatOpenAI(temperature=0, max_tokens=2000, model=self.openai_model, request_timeout=BotAgent.REQUEST_TIMEOUT)
        llm_math_chain = LLMMathChain.from_llm(llm=match_llm,verbose=False,callbacks=self.callback_list)
        web_tool = WebSearchTool()
        self.task_repo: AITaskRepo = None
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
        for t in self.tools:
            t.callbacks = self.callback_list
        # メモリの準備
        mem_llm = ChatOpenAI(temperature=0, max_tokens=1000, model=self.openai_model, request_timeout=BotAgent.REQUEST_TIMEOUT )
        self.agent_memory: ExtConversationSummaryBufferMemory = ExtConversationSummaryBufferMemory( Bot=self, llm=mem_llm, max_token_limit=800, memory_key="memory_hanaya", return_messages=True, callbacks=self.callback_list)

        self.anser_list = []
        self.load_time_sec = int(time.time())
        self.last_call_sec = self.load_time_sec
        self.news_repo : NewsRepo= None

    def _file_path(self,path):
        return f"{path}/model_{self.userid}.json"

    def load(self,path):
        if not self.userid or not path:
            return
        json_file = self._file_path(path)
        if not os.path.exists(json_file):
            return
        logger.info(f"load from {json_file}")
        with open(json_file,"r") as fp:
            json_data = json.load(fp)
        self.from_dict(json_data)

    def unload(self,path):
        if not self.userid or not path:
            return
        os.makedirs(path,exist_ok=True)
        json_file = self._file_path(path)
        logger.info(f"unload to {json_file}")
        json_data = self.to_dict()
        with open(json_file,"w") as fp:
            json.dump(json_data,fp,indent=4)

    def from_dict(self,json_data:dict):
        # 基本情報
        self.userid = json_data.get("userid",None)
        self.name = json_data.get("name",None)
        self.last_call_sec = json_data.get("last_call",0)
        # 記憶
        self.agent_memory.moving_summary_buffer = ""
        self.agent_memory.chat_memory.clear()   
        mem_json:dict = json_data.get('memory',None)
        if mem_json:
            self.agent_memory.moving_summary_buffer = mem_json.get("summary","")
            mesgs_json = mem_json.get("messages",None)
            if mesgs_json and len(mesgs_json)>0:
                megs = messages_from_dict(mesgs_json)
                for m in megs:
                    self.agent_memory.chat_memory.add_message(m)

    def to_dict(self) -> dict:
        json_data = {
            "userid": self.userid,
            "name": self.name,
            "last_call": self.last_call_sec
        }
        mem:dict = {}
        if self.agent_memory.moving_summary_buffer:
            mem['summary'] = self.agent_memory.moving_summary_buffer
        if self.agent_memory.chat_memory:
            msgs = self.agent_memory.chat_memory.messages
            if msgs and len(msgs)>0:
                mem['messages'] = messages_to_dict(msgs)
        if len(mem)>0:
            json_data['memory']=mem
        return json_data

    def summarize(self) -> None:
        # タイマーから起動されて、記憶を全部要約する
        self.log_info("summarize...")
        if len(self.agent_memory.chat_memory.messages)>0:
            before = self.agent_memory.max_token_limit
            try:
                self.agent_memory.max_token_limit = 10
                self.agent_memory.prune()
            except Exception as ex:
                self.log_error("",ex)
            finally:
                self.agent_memory.max_token_limit = before

    def tone_convert(self, message: str) -> str:
        msg2 = ToneV.tone_convert(message)
        if message != msg2:
            self.log_info(f"convert {message}\nto {msg2}")
        return msg2

    @staticmethod
    def ago( sec: int ) -> str:
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
        
    def build_main_prompt(self) -> str:
        # メインプロンプト構築
        prompt = self.main_prompt if self.main_prompt is not None else ""
        if "{bot_name}" in prompt:
            if self.name is None or len(self.name)==0:
                prompt = prompt.replace("{bot_name}","none")
            else:
                prompt = prompt.replace("{bot_name}",self.name)
        if "{current_datetime}" in prompt:
            # 現在の時刻を取得
            formatted_time = Utils.formatted_datetime()
            prompt = prompt.replace("{current_datetime}",formatted_time)
        if "{current_location}" in prompt:
            if self.current_location is None or len(self.current_location)==0:
                prompt = prompt.replace("{current_location}","Japan")
            else:
                prompt = prompt.replace("{current_location}",self.current_location)
        prompt += "\nYou speak a short line"
        if self.lang_out is None or len(self.lang_out)==0:
            prompt += "."
        else:
            prompt += f' in {self.lang_out}.'
        return prompt

    def _run_impl(self,talk_id:int, query:str):
        agent_chain = None
        agent_llm = None
        try:
            self.task_tool.task_repo = self.task_repo # 実行前に設定されるはず
            self.log_info(f"[LLM] you text:{query}")
                
            agent_llm = ExChatOpenAI(verbose=False, temperature=0.7, max_tokens=2000, model=self.openai_model, streaming=False, request_timeout=BotAgent.REQUEST_TIMEOUT )
            # メインプロンプト設定
            # ポスト処理
            # prompt
            # systemメッセージプロンプトテンプレートの準備
            main_prompt_message = SystemMessage(
                content=self.build_main_prompt()
            )
                
            # 記憶の整理
            now = int(time.time())
            ago_mesg = BotAgent.ago( now-self.last_call_sec)
            if ago_mesg:
                event_text = []
                event_text.append(ago_mesg)
                # 出来事を追加
                if self.news_repo:
                    news : NewsData = self.news_repo.random_get(self.userid)
                    if news:
                        event_text.append('Use this news in your comment.\n# URL:'+news.link+"\n# Article:" + news.snippet+"\n\nTell to Human abount this news.")
                # self.event_promptで出来事を生成
                elif self.event_prompt is not None and len(self.event_prompt)>0:
                    text = agent_llm.predict( main_prompt_message.content + "\n" + self.event_prompt, stop=["\n"])
                    if text:
                        event_text.append(text)
                if len(event_text)>0:
                    self.agent_memory.set_post_prompt( "\n".join(event_text) )
            self.last_call_sec = now
            # 回答の制限
            if random.randint(0,5)==0:
                stp=["。","\n"]
                llm_model_kwargs = { "max_tokens": 500, "stop": stp }
                agent_llm.model_kwargs = llm_model_kwargs
            agent_kwargs = {
                "system_message": main_prompt_message,
                "extra_prompt_messages": [MessagesPlaceholder(variable_name="memory_hanaya")],
            }
            # エージェントの準備
            agent_chain : AgentExecutor = initialize_agent(
                self.tools, 
                agent_llm, 
                agent=AgentType.OPENAI_FUNCTIONS,
                verbose=False, callbacks=self.callback_list,
                memory=self.agent_memory,
                agent_kwargs=agent_kwargs, 
                handle_parsing_errors=False
            )
            import langchain
            langchain.debug=False
            save_max_tokens = agent_llm.max_tokens
            save_temperature = agent_llm.temperature
            try:
                for t in range(3,-1,-1):
                    try:
                        res_text = agent_chain.run(input=query)
                        self._ai_message(talk_id,res_text)
                        break
                    except OutputParserException as ex:
                        res_text = f"{ex}"
                        if res_text.startswith("Could not parse tool input:"):
                            if t>0:
                                print(f"ERROR:{res_text}")
                                self.agent_memory.ext_save_context( query, res_text )
                            else:
                                print(f"ERROR:{res_text}")
                                self._ai_message(talk_id,"えらーが発生しました")
                            agent_llm.temperature = 0
                            agent_llm.max_tokens += 100
                        else:
                            self.log_error( "",ex)
                            self._ai_message(talk_id,"エラーが発生しました")
                            break
            finally:
                agent_llm.max_tokens = save_max_tokens
                agent_llm.temperature = save_temperature

            anser = res_text
            if len(self.agent_memory.chat_memory.messages)>0:
                anser = self.agent_memory.chat_memory.messages[-1].content
            print(f"[LLM] GPT anser:{anser}")

            # 記憶の整理

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
            self.log_error("",ex)
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
    langchain.debug=False
    import logging
    # configure root logger
    log_date_format = '%Y-%m-%d %H:%M:%S'
    log_format = '%(asctime)s [%(levelname)s] %(name)s %(message)s'
    log_formatter = logging.Formatter(log_format, log_date_format)
    root_logger : logging.Logger = logging.getLogger()
    console_hdr = logging.StreamHandler()
    console_hdr.setLevel( logging.DEBUG )
    console_hdr.setFormatter(log_formatter)
    root_logger.addHandler( console_hdr )

    openai_logger = logging.getLogger("openai")
    openai_logger.setLevel( logging.DEBUG )
    openai_logger.propagate = False
    openai_fh = TimedRotatingFileHandler('logs/openai-debug_log',when='midnight',backupCount=7,interval=1,encoding='utf-8')
    openai_fh.setFormatter(log_formatter)
    openai_logger.addHandler(openai_fh)

    agent_repo_path = "agents"
    task_repo = AITaskRepo()
    repo : BotRepository = BotRepository(agent_repo_path)
    userid='b000'
    agentB1 : BotAgent = repo.get_agent(userid)
    agentB2 : BotAgent = repo.get_agent(userid)
    if agentB1 != agentB2:
        print("ERROR x")
        return
    repo.unload_min=0
    repo._last_timer_sec = 0
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
    agent2.task_repo = task_repo
    response = agent2.llm_run('今日はなにしてたの？')
    print(f"[TEST.RESULT]{response}")
    response = agent2.llm_run('天ぷらの作り方を調べておしえて')
    print(f"[TEST.RESULT]{response}")
    agent2.last_call_sec = int(time.time()) - 7*24*3600

    repo.unload_min=0
    while repo.size()>0:
        repo._last_timer_sec = 0
        repo.call_timer()
    repo.unload_min = 10

    agent3 : BotAgent = repo.get_agent(userid)
    if agent3 == agent2:
        print("ERROR: 002")
        return

    agent3.task_repo = task_repo
    response = agent3.llm_run('こんにちは、何日ぶりかな')
    print(f"[TEST.RESULT]{response}")
    response = agent3.llm_run('何か出来事がありましたか？')
    print(f"[TEST.RESULT]{response}")


if __name__ == "__main__":
    main()