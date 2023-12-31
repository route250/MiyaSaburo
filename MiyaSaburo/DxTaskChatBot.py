import os,sys,threading
from enum import Enum
import time
import json
import traceback
import concurrent.futures
import queue
from queue import Queue
from concurrent.futures import ThreadPoolExecutor, Future
from DxBotUtils import BotCore, BotUtils, ToolBuilder, RecognizerEngine, TtsEngine
import DxChatBot
from DxChatBot import DxChatBot
from DxBotUI import debug_ui
from tools.webSearchTool import WebSearchModule
from urllib.parse import urlparse

class DxTaskChatBot(DxChatBot):
    def __init__(self):
        super().__init__()

class DxTask(BotCore):
    def __init__(self,task_queue, args):
        super().__init__()
        self.start = False
        self.done = False
        self._quque:queue.Queue = task_queue
        self._job_text = BotUtils.str_strip_or_default(args.get('委譲する内容'))
        if self._job_text is None:
            self._job_text = BotUtils.str_strip_or_default(args.get('出力内容'))
        if self._job_text is None:
            self._job_text = BotUtils.str_strip_or_default(args.get('実行する処理内容'))
        self.mesg_thread:list[dict] = []
        self.response = None

        output:str = ""
        if self._job_text is None:
            output += "処理内容が記載されていない。"
        if len(output)>0:
            self.done = True
            self.response = output
            return

        prompt:str = BotUtils.str_indent(f"""
            # 貴方は他のAIから依頼された処理を実行するAIです
            下記のタスクを実行してください。
            処理内容: {self._job_text}
            # 以下の手順で処理して下さい。
            1.時間、日付、期間が含まれる場合、具体的な指定がされているか判断し、昨日や明日、昼や夕方、最近など曖昧な表現があれば依頼元へのエラーメッセージを生成する
                例) 期間は具体的に、1ヶ月、1日間、3時間、5分後など具体的数値で指定して下さい。
                  日付は具体的に2023-01-01のように具体的に指定して下さい。
            2. 処理内容から、求められる結果をまとめて下さい。
            3. 処理内容から、詳細な処理手順を作成して下さい。
            4. 処理内容が実行可能であるかを判断して下さい。
            5. 実行できないと判断した場合は、依頼元へのエラーメッセージを生成して下さい。
                例) ....は処理できません
            6. これまでの情報に基づいて、処理を実行して下さい。
        """)
        prompt:str = BotUtils.str_indent("""# You are an AI that executes processes requested by other AIs
            Please perform the tasks below.
            Processing details: {self._job_text}
            # Please follow the steps below.
            1. If time, date, or period is included, determine whether a specific specification has been made, and if there is an ambiguous expression such as yesterday, tomorrow, afternoon, evening, recent, etc., generate an error message to the requester.
                Example) Please specify the period using specific values ​​such as 1 month, 1 day, 3 hours, 5 minutes, etc.
                  Please specify the date specifically, such as 2023-01-01.
            2. Please summarize the desired results based on the processing details.
            3. Create a detailed processing procedure based on the processing content.
            4. Determine whether the processing content is executable.
            5. If you determine that it cannot be executed, please generate an error message to the requester.
                Example) ... cannot be processed
            6. Take action based on the information you have so far.""")
        
        self.mesg_thread.append(
            { 'role': 'system', 'content': prompt }
        )
        self._tools = [
            ToolBuilder('errorRetern')
                .param('エラーメッセージ','依頼元へのエラーメッセージ')
                .build(),
            ToolBuilder('WebSearch')
                .param('検索キーワード','検索キーワードは空白で区切って複数指定した場合AND検索となります')
                .build(),
        ]

    def start(self):
        self.start = True
        self.run()

    def send(self, data ):
        self.mesg_thread.append(
            { 'role': 'system', 'content': data }
        )

    def run(self):
        if self.done : return
        print( f"[TASK] run......" )
        content, tool_calls = self.ChatCompletion2(self.mesg_thread,tools=self._tools)
        if isinstance(tool_calls,list):
            self.mesg_thread.append( { 'role': 'assistant', 'content': content, 'tool_calls': tool_calls } )

            # errorReternだけ先に処理
            confirm_list = []
            for call in tool_calls:
                fn = call.get('function',{})
                fn_name = fn.get('name')
                fn_args = fn.get('arguments')
                if 'errorRetern' == fn_name:
                    args = json.loads( fn_args)
                    txt:str = args.get('エラーメッセージ')
                    if txt:
                        confirm_list.append(txt)
            if len(confirm_list)>0:
                print( f"[TASK] response error {confirm_list}" )
                self.response = "エラーメッセージ:\n"+("\n".join(confirm_list))
                self._quque.put(self)
                return

            # confirm以外を処理する
            for call in tool_calls:
                fn = call.get('function',{})
                fn_name = fn.get('name')
                if 'errorRetern' == fn_name:
                    continue
                fn_args = fn.get('arguments')
                print( f"[TASK] content function {fn_name}  args={fn_args}")
                self.response = "明日の天気 晴れ 最低気温 4℃ 最高気温 16℃ 降水確率 10%"
                self._quque.put(self)

        else:
            print(f"[TASK] response content:{content}")

    def run_websearch(self, args):
        keyword = BotUtils.str_strip_or_default( args.get('検索キーワード'))
        if keyword is None:
            return "検索キーワードが指定されてません。"
        return self.tool_websearch( keyword )
    
    def tool_websearch(self, keyword):
        keyword_list = [keyword]
        module:WebSearchModule = WebSearchModule()
        ite = module.google_custom_search(keyword)
        for d in ite:
            site_title: str = d.get('title',"")
            site_link: str = d.get('link',"")
            site_prop: dict = d.get('prop',{})
            site_url: str = urlparse(site_link)
            site_hostname: str = site_url.netloc
            print(f"---------------------\n{site_title}\n{site_link}")
            site_text: str = module.get_content( site_link, type="title", timeout=15 )
            print(f"---------------------\n{site_text}")

def test():
    bot: DxTaskChatBot = DxTaskChatBot()
    debug_ui(bot)

qqq:queue.Queue = queue.Queue()
def add_qqqq(data):
    qqq.put(data)

def test2():
    
    bot: DxTaskChatBot = DxTaskChatBot()
    xtools = [
        ToolBuilder('submitTask','貴方が実行出来ない処理を、他のAIへ委譲するときに使えます。')
            .param('委譲する内容','委譲する処理内容を、具体的、論理的にリストアップして下さい。日付、時間、期間、などの処理に必要な情報は可能な限り具体的な数値で指定して下さい。')
            .param('実行結果として要求する内容','Taskの結果として必要な内容を具体的に端的にリストアップして下さい。')
            .build(),
        # ToolBuilder('sendToTask')
        #     .param('confirm','Taskから要求された確認事項')
        #     .param('response','確認事項に対する返答')
        #     .build(),
    ]
    mesg_thread = []
    mesg_thread.append( { 'role': 'user', 'content': BotUtils.str_indent(
                """
                明日の天気はどうかな？
                """)})

    tk:DxTask = None
    tools = xtools
    while True:
        content, tool_calls = bot.ChatCompletion2( mesg_thread, tools=tools )
        if content is None and tool_calls is None:
            return
        st:DxTask = None
        if isinstance(tool_calls,list):
            mesg_thread.append( { 'role': 'assistant', 'content': content, 'tool_calls': tool_calls } )
            tools = None
            sx:bool = False
            for call in tool_calls:
                call_id = call.get("id")
                fn = call.get("function",{})
                fn_name = fn.get("name")
                if 'submitTask' == fn_name:
                    fn_args = json.loads( fn.get("arguments") ) 
                    print( f"function {fn_name}  args={fn_args}")
                    st = DxTask(qqq, fn_args)
                    qqq.put(st)
                    #mesg_thread.append( { 'role': 'assistant', 'content': f"タスク 処理内容:{fn_args['処理内容']} を実行" })
                    #mesg_thread.append( { 'role': 'assistant', 'content': None, 'tool_calls': ret })
                    #mesg_thread.append( { 'role': 'system', 'content': f"「{fn_args['処理内容']}」という処理をバックグラウンドで開始しました。結果後で通知します。" })
                    mesg_thread.append( { 'role': 'tool', 'content': f"タスク処理が開始されました。", 'tool_call_id': call_id })
                    #sx = True
                elif 'sendToTask' == fn_name:
                    fn_args = json.loads( fn.get("arguments") ) 
                    print( f"function {fn_name}  args={fn_args}")
                    mesg_thread.append( { 'role': 'tool', 'content': "not found tool: {fn_name}", 'tool_call_id': call_id })
                    #tk.send( fn_args['response'])
                    #qqq.put(tk)
                else:
                    mesg_thread.append( { 'role': 'tool', 'content': "not found tool: {fn_name}", 'tool_call_id': call_id })

            if sx:
                continue
        else:
            tools = xtools
            mesg_thread.append( { 'role': 'assistant', 'content': content })
            print( f"\nAI:{content}")

        try:
            tk = qqq.get_nowait()
            if tk.response:
                print( f"TaskToAI:{tk.response}")
                ms = [ m for m in mesg_thread if m.get('role')=='tool' and m.get('tool_call_id') == call_id ]
                if ms and len(ms)>0:
                    m = ms[-1]
                    m['content'] = f"{tk.response}"
                else:
                    mesg_thread.append( { 'role': 'tool', 'content': f"{tk.response}", 'tool_call_id': call_id })
            else:
                tk.run()
            continue
        except queue.Empty:
            pass
        
        user_input = ""
        while user_input is None or len(user_input)==0:
            user_input = input(">>> ")
        mesg_thread.append( { 'role': 'user', 'content': user_input })

if __name__ == "__main__":
    test2()