
import os
import time

import openai
from langchain.chains.conversation.memory import ConversationBufferMemory,ConversationBufferWindowMemory,ConversationSummaryBufferMemory
from langchain.memory import ConversationTokenBufferMemory
from langchain.prompts import MessagesPlaceholder
from langchain.chat_models import ChatOpenAI
from langchain.agents.agent_types import AgentType
from langchain.agents import initialize_agent, Tool, load_tools
from langchain.prompts.chat import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    AIMessagePromptTemplate,
    HumanMessagePromptTemplate,
)
from langchain.schema import SystemMessage
from langchain.schema import BaseMessage, BaseChatMessageHistory
from libs.CustomChatMessageHistory import CustomChatMessageHistory
from tools.webSearchTool import WebSearchTool
from langchain import LLMMathChain

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

class BotRepository:
    def __init__(self):
        self._map :dict = dict()

    def get_agent(self, userid ):
        agent:BotAgent = self._map.get(userid)
        if agent is None:
            agent = BotAgent(userid)
            self._map[userid] = agent
        return agent
class Personality:
    def __init__(self):
        self.name = ''
        self.main_prompt = ''
        self.post_process : function = None
TERMLIST=[ 
        ["ありません。", "ないニャ。"],["ください。","にゃ。"],
        ["できません。", "できないニャ。"],
        ["できます。", "できるニャ。"],
        ["ありません。", "ないニャ。"],["ありますか。","あるニャ？"],
        ["ですか？", "ニャ？"],
        ["ましたね。","ましたニャ。"],
        ["したよね。","したニャ。"],["ません。","ないニャ。"],
        ["ですね。","だニャ。"],
        ["ですよ。","だニャ。"],
        ["です。","だニャ。"],["いたしますよ。","するニャ。"],["いたします。","するニャ。"]
     ]
REPLIST=[ 
        ["ごめんなさい、", "ごめんニャ、"],
        ["ただし、", "でもニャ、"],
        ["でも、", "でもニャ、"],
        ["ので、", "ニャ、"],
        ["ですから、", "だからニャ、"],
     ]

def default_post_process( mesgs, origs):
    result = []
    for i,m in enumerate(mesgs):
        for j,e, in enumerate(TERMLIST):
            if m.endswith(e[0]):
                m = m[:-len(e[0])] + e[1]
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
        self.tools=[]
        self.tools += [
            web_tool,
            #langchain.tools.PythonAstREPLTool(),
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
        self.personality.main_prompt = "You are a stray cat and an lady cat. powerd by OpenAI. You complain and make fun of people on a whim. Keep your remarks short. Talk casually and lethargic"
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
        mem_llm = ChatOpenAI(temperature=0, max_tokens=2000, model=self.openai_model)
        self.agent_memory = ConversationSummaryBufferMemory(llm=mem_llm, max_token_limit=600, memory_key="memory_hanaya", return_messages=True)
        self.memory : CustomChatMessageHistory = CustomChatMessageHistory()
        self.agent_memory.chat_memory : BaseChatMessageHistory=self.memory #Field(default_factory=ChatMessageHistory)
        self.name = ''

    def llm_run(self,query):
        agent_chain = None
        agent_llm = None
        try:
            print(f"[LLM] you text:{query}")
            # 現在の時刻を取得
            formatted_time = formatted_datetime()
            # メインプロンプト構築
            mp = ""
            if self.personality:
                mp = f"Your name is {self.personality.name}." if self.personality.name else ""
                mp += self.personality.main_prompt if self.personality.main_prompt else ""
                self.memory.post_process = self.personality.post_process
            mp += 'Use language of '+self.lang_out + " ( current time: " + formatted_time + " " + self.current_location +")"
            # メインプロンプト設定
            self.main_prompt_message.content = mp
            # ポスト処理
            # prompt
            agent_llm = ChatOpenAI(temperature=0.7, max_tokens=2000, model=self.openai_model, streaming=True)
            # エージェントの準備
            agent_chain = initialize_agent(
                self.tools, 
                agent_llm, 
                agent=AgentType.OPENAI_FUNCTIONS,
                verbose=False, 
                memory=self.agent_memory,
                agent_kwargs=self.agent_kwargs, 
                handle_parsing_errors=_handle_error
            )
            res_text = agent_chain.run(input=query)
            print(f"[LLM] GPT text:{res_text}")
            anser = self.agent_memory.chat_memory.messages[-1].content
            print(f"[LLM] GPT text:{anser}")
            return anser

        except KeyboardInterrupt as ex:
            print("[LLM] cancel" )
        except openai.error.APIError as ex:
            print(ex)
        except Exception as ex:
            print(ex)
        finally:
            if agent_chain:
                del agent_chain
            if agent_llm:
                del agent_llm

    def dump_mem(self):
        for m in self.agent_memory.chat_memory.messages:
            print( f"{m}")

def main():
    repo : BotRepository = BotRepository()
    userid='a001'
    agent : BotAgent = repo.get_agent(userid)
    print(f"agent {agent.userid}")
    agent2 : BotAgent = repo.get_agent(userid)
    print(f"agent {agent2.userid}")

    agent2.llm_run('こんにちはい')


if __name__ == "__main__":
    main()