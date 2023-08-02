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
    def __init__(self, bot_id:str, date_time:str, purpose:str=None, action:str=None ):
        self.task_id = AITask._instance_count
        AITask._instance_count+=1
        self.bot_id = bot_id
        self.date_time = date_time
        self.time_sec = Utils.to_unix_timestamp_seconds(date_time)
        self.purpose = Utils.strip(purpose)
        self.action = Utils.strip(action)

    def is_valid(self) -> bool:
        if self.time_sec<10:
            return False
        if self.purpose is not None and len(self.purpose)>0:
            return True
        if self.action is not None and len(self.action)>0:
            return True
        return False

    def to_string(self):
        if self.action is not None and len(self.action)>0:
            return f"{self.date_time} {self.action}"
        elif self.purpose is not None and len(self.purpose)>0:
            return f"{self.date_time} {self.purpose}"
        return f"{self.date_time} None"

class AITaskRepo:

    def __init__(self):
        self._task_list : list[AITask] = list[AITask]()
        self._last_call = 0
        self.task_queue = queue.Queue()
        self._cv = threading.Condition()

    def logdump(self):
        with self._cv:
            dump = "\n".join([ f"{t.bot_id} {t.date_time} {t.time_sec} {t.purpose} {t.action}" for t in self._task_list])
            logger.debug( f"task dump\n{dump}")

    def call( self, bot_id:str, cmd : TaskCmd, date_time : str, purpose: str = None, action: str = None ):
        with self._cv:
            try:
                result = None
                if cmd == TaskCmd.add:
                    task = AITask( bot_id, date_time, purpose, action )
                    if task.time_sec>10:
                        self._task_list.append(task)
                        result = "Reserved at "+date_time
                    else:
                        result = f"Invalid date time \"{date_time}\""
                elif cmd == TaskCmd.cancel:
                    new_list = []
                    for t in self._task_list:
                        if t.bot_id != bot_id or t.date_time != date_time or (action and t.action != action):
                            new_list.append(t)
                    removed = len(self._task_list)-len(new_list)
                    if removed>0:
                        self._task_list = new_list
                        result = "Cancelled from " + date_time
                    else:
                        result = "Not found task in " + date_time
                elif cmd == TaskCmd.get:
                    if len(self._task_list)>0:
                        result = " ".join([ t.to_string() for t in self._task_list if t.is_valid() and t.bot_id==bot_id])
                    else:
                        result = "no tasks."
                logger.info(f"task repo call {bot_id} {cmd} {date_time} {purpose} {action} result {result}")
            except:
                logger.exception(f"eror in task repo call {bot_id} {cmd} {date_time} {purpose} {action}")
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
                            logger.debug( f"timer_event get {t.bot_id} {t.date_time} {t.time_sec} {t.purpose} {t.action}" )
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
    cmd: TaskCmd
    date_time: str = Field( '', description='Time to reserve a task by YYYY/MM/DD HH:MM:SS. If you unclear the time, then ask to user')
    purpose: str = Field( '', description='why do it and goals to achieve')
    action: str = Field( '', description='what you should do.')

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

    def _run( self, cmd:TaskCmd, date_time: str='', purpose:str='', action:str='', run_manager: Optional[CallbackManagerForToolRun] = None ) -> str:
        result = None
        try:
            if self.task_repo is None:
                logger.error("task_repo is null")
                result = "out of service."
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
                    res = self.task_repo.call( self.bot_id, cmd, date_time, purpose, action)
                    if res:
                        result = header + res
                    else:
                        logger.error(f"task_repo.call() returned None")
                        result = "Repository as problem?"
        except Exception as ex:
            logger.exception("")
            result = "System Error"
        logger.info(f"TaskTool {cmd},{date_time},{purpose},{action} result {result}")
        return result

    async def _arun(self, query: str, run_manager: Optional[AsyncCallbackManagerForToolRun] = None) -> str:
        """Use the tool asynchronously."""
        raise NotImplementedError("custom_search does not support async")
    

