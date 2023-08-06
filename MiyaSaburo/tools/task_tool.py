import queue
import time
from enum import Enum
from pydantic import Field, BaseModel
from typing import Optional, Type, Callable

import threading
from langchain.callbacks.manager import AsyncCallbackManagerForToolRun, CallbackManagerForToolRun
from langchain.tools.base import BaseTool
from libs.utils import Utils

import logging
logger = logging.getLogger("task_tool")

class TaskCmd(str, Enum):
    add = 'add'
    cancel = 'cancel'
    get = 'get'

class AITask:
    _instance_count = 0
    def __init__(self, bot_id:str, date_time:str, how_to_do:str=None, what_to_do:str=None ):
        self.task_id = AITask._instance_count
        AITask._instance_count+=1
        self.bot_id = bot_id
        self.date_time = date_time
        self.time_sec = Utils.to_unix_timestamp_seconds(date_time)
        self.how_to_do = Utils.strip(how_to_do)
        self.what_to_do = Utils.strip(what_to_do)

    def is_valid(self) -> bool:
        if self.time_sec<10:
            return False
        if Utils.is_empty(self.how_to_do) and Utils.is_empty(self.what_to_do):
            return False
        return True

    def to_string(self):
        return f"{Utils.empty_to_blank(self.date_time)} {Utils.empty_to_blank(self.what_to_do)} {Utils.empty_to_blank(self.how_to_do)}"

class AITaskRepo:

    def __init__(self):
        self._task_list : list[AITask] = list[AITask]()
        self._last_call = 0
        self.task_queue = queue.Queue()
        self._cv = threading.Condition()

    def logdump(self):
        with self._cv:
            dump = "\n".join([ f"{t.bot_id} {t.date_time} {t.time_sec} {t.how_to_do} {t.what_to_do}" for t in self._task_list])
            logger.debug( f"task dump\n{dump}")

    def call( self, bot_id:str, cmd : TaskCmd, date_time : str, how_to_do: str = None, what_to_do: str = None ):
        with self._cv:
            try:
                result = None
                if cmd == TaskCmd.add:
                    task = AITask( bot_id, date_time, how_to_do, what_to_do )
                    if task.is_valid():
                        self._task_list.append(task)
                        result = "Reserved at "+date_time
                    else:
                        result = f"Invalid date time \"{date_time}\""
                elif cmd == TaskCmd.cancel:
                    new_list = []
                    for t in self._task_list:
                        if t.bot_id != bot_id or t.date_time != date_time or (what_to_do and t.what_to_do != what_to_do):
                            new_list.append(t)
                    removed = len(self._task_list)-len(new_list)
                    if removed>0:
                        self._task_list = new_list
                        result = "Cancelled from " + date_time
                    else:
                        result = "Not found task in " + date_time
                elif cmd == TaskCmd.get:
                    if len(self._task_list)>0:
                        result = " , ".join([ t.to_string() for t in self._task_list if t.is_valid() and t.bot_id==bot_id])
                        result = f"Your task is {result}"
                    else:
                        result = "no tasks."
                logger.info(f"task repo call {bot_id} {cmd} {date_time} {how_to_do} {what_to_do} result {result}")
            except:
                logger.exception(f"eror in task repo call {bot_id} {cmd} {date_time} {how_to_do} {what_to_do}")
                result = None
            self.logdump()
            return result

    def timer_event(self) -> list[AITask]:
        with self._cv:
            try:
                now_sec = int( time.time() )
                task_list = list[AITask]()
                submit_list = list[AITask]()
                for t in self._task_list:
                    if t.is_valid():
                        if t.time_sec>now_sec:
                            task_list.append(t)
                        else:
                            submit_list.append(t)
                            logger.debug( f"timer_event get {t.bot_id} {t.date_time} {t.time_sec} {t.how_to_do} {t.what_to_do}" )
                self._task_list.clear()
                self._task_list = task_list
                if len(submit_list)>0:
                    self.logdump()
                return submit_list
            except:
                logger.exception(f"eror in task repo timer_event")
            return []

    def get_task(self,ai_id:str) -> AITask:
        with self._cv:
            try:
                size = len(self._task_list)
                if size==0:
                    return None
                now_sec = int( time.time() )
                idx = 0
                while idx<size:
                    task = self._task_list[idx]
                    if task.bot_id == ai_id and task.time_sec <= now_sec:
                        break
                    idx+=1
                if idx>=size:
                    return None
                submit = self._task_list[idx]
                del self._task_list[idx]
                self.logdump()
                return submit
            except:
                logger.exception(f"eror in task repo get_task {ai_id}")
            return None

# Toolの入力パラメータを定義するモデル
class AITaskInput(BaseModel):
    cmd: TaskCmd = Field(None, description='command')
    date_time: str = Field( '', description='Time to reserve a task by YYYY/MM/DD HH:MM:SS. If you unclear the time, then ask to user')
    how_to_do: str = Field( '', description='How to do this task')
    what_to_do: str = Field( '', description='What to do or What are you talking about.')

# LangChainのAgentに渡すtool
class AITaskTool(BaseTool):

    name = "AITaskTool"
    description = ( "Schedule your tasks for the future." )
    # 入力パラメータのスキーマを定義
    args_schema: Optional[Type[BaseModel]] = AITaskInput

    # Repoは、複数のAIで共用するが
    # Toolは一つのAIに対して一個インスタンスすること
    bot_id : str = None
    task_repo: AITaskRepo = None

    convert = {
        "教える": "時間になったのを知らせる",
        "教えること": "時間になったのを知らせる",
        "知らせる": "時間になったのを知らせる",
    }
    def _run( self, cmd:TaskCmd = None, date_time: str='', how_to_do:str='', what_to_do:str='', run_manager: Optional[CallbackManagerForToolRun] = None ) -> str:
        result = None
        try:
            if self.task_repo is None:
                logger.error("task_repo is null")
                result = "out of service."
            elif cmd is None:
                result = "invalud arguments"
            else:
                header = ""
                now = int(time.time())
                sec = Utils.to_unix_timestamp_seconds(date_time) if date_time and len(date_time)>0 else 0
                if sec < 10 and cmd == TaskCmd.cancel:
                    cmd = TaskCmd.get
                    header = f"\"{date_time}\" is ambiguous. Select from belows."
                if sec < 10 and cmd == TaskCmd.add:
                    result = f"\"{date_time}\" is ambiguous. Ask the user for the time."
                elif sec < (now-10) and cmd == TaskCmd.add:
                    result = f"\"{date_time}\" is passt time. Ask the user for the time."
                else:
                    if cmd == TaskCmd.add:
                        how_to_do = self.convert.get(how_to_do,how_to_do)
                        what_to_do = self.convert.get(what_to_do,what_to_do)
                    res = self.task_repo.call( self.bot_id, cmd, date_time, how_to_do, what_to_do)
                    if res:
                        result = header + res
                    else:
                        logger.error(f"task_repo.call() returned None")
                        result = "Repository as problem?"
        except Exception as ex:
            logger.exception("")
            result = "System Error"
        logger.info(f"TaskTool {cmd},{date_time},{how_to_do},{what_to_do} result {result}")
        return result

    async def _arun(self, query: str, run_manager: Optional[AsyncCallbackManagerForToolRun] = None) -> str:
        """Use the tool asynchronously."""
        raise NotImplementedError("custom_search does not support async")
    

