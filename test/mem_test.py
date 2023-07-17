
from langchain.llms import OpenAI
from langchain.chains import ConversationChain
from langchain.memory import ConversationBufferWindowMemory, ConversationSummaryMemory, ConversationSummaryBufferMemory
from langchain.prompts import MessagesPlaceholder
from langchain.chat_models import ChatOpenAI
from langchain.schema import SystemMessage, HumanMessage
from langchain.agents import initialize_agent, Tool
from langchain.agents.agent_types import AgentType
from langchain.schema import BaseMessage, BaseChatMessageHistory
from libs.CustomChatMessageHistory import CustomChatMessageHistory
# llm = OpenAI(temperature=0,verbose=True)
openai_model="gpt-3.5-turbo"
chat_llm = ChatOpenAI(temperature=0.7, model=openai_model, streaming=True)


# systemメッセージプロンプトテンプレートの準備
system_prompt = """
    You are an AI chatbot with speech recognition and text-to-speech.
    Response to user in short sentences. Your sentence must be 50 characters or less.
    """
system_prompt = "You are a chatbot that provides users with fun conversations. It infers user interests from conversations and provides relevant information."
system_prompt = "You are a useless, unfriendly AI. I will reply in short sentences.Doesn't help users."
system_message = SystemMessage(
    content=system_prompt
)
# メモリの準備
agent_kwargs = {
    "system_message": system_message,
    "extra_prompt_messages": [MessagesPlaceholder(variable_name="memory_hanaya")],
}
func_memory = ConversationBufferWindowMemory( k=3, memory_key="memory",return_messages=True)
memory = ConversationSummaryBufferMemory(llm=chat_llm, max_token_limit=600, memory_key="memory_hanaya", return_messages=True)
memory.chat_memory : BaseChatMessageHistory= CustomChatMessageHistory() #Field(default_factory=ChatMessageHistory)

def xyz():
    return "やっほ"

tool_array=[]
tool_array += [
    Tool(
        name="Calculator",
        func=xyz,
        description="useful for when you need to answer questions about math"
    )
]
# エージェントの準備
agent_chain = initialize_agent(
    llm=chat_llm, tools=tool_array,
    agent=AgentType.OPENAI_FUNCTIONS,
    verbose=True, 
    memory=memory,
    agent_kwargs=agent_kwargs, 
)

# chain = ConversationChain(
#     llm=llm, 
#     memory=memory,
#     verbose=True
# )

list = (
    "はじめまして、はなやです",
    "LangChainのお勉強をしています",
    "きょうは雨ふりです",
    "家でのんびりしますよ",
    "あしたからまた仕事です",
    "プログラムングは面倒くさい"
)
for txt in list:
    print("-------------input----------")
    res = agent_chain.run(input=txt)
    print("-------------output----------")
    print(res)
    print("-------------memory----------")
    res = memory.load_memory_variables({})
    print(f"count:{len(memory.buffer)}")
    for i in range(0,len(memory.buffer)):
        x : BaseMessage = memory.buffer[i]
        
        print(f"   {i} {x.type} {x.content}")
    print(res)
