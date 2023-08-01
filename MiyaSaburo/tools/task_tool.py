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

class AITaskRepo:

    def __init__(self):
        self._task_list : list[AITask] = list[AITask]()
        self._last_call = 0
        self.task_queue = queue.Queue()

    def call( self, bot_id:str, cmd : TaskCmd, date_time : str, purpose: str = None, action: str = None ):
        if cmd == TaskCmd.add:
            task = AITask( bot_id, date_time, purpose, action )
            self._task_list.append(task)
            return "Reserved at "+date_time
        elif cmd == TaskCmd.cancel:
            new_list = []
            for t in self._task_list:
                if t.bot_id != bot_id or t.date_time != date_time or (action and t.action != action):
                    new_list.append(t)
            removed = len(self._task_list)-len(new_list)
            if removed>0:
                self._task_list = new_list
                return "Cancelled from " + date_time
            else:
                return "Not found task in " + date_time
        elif cmd == TaskCmd.get:
            if len(self._task_list)>0:
                return " ".join([ f"{t.date_time} {t.action}" for t in self._task_list if t.bot_id==bot_id])
            else:
                return "no tasks."

    def timer_event(self) -> list[AITask]:
        now_sec = int( time.time() )
        task_list = []
        submit_list = []
        for t in self._task_list:
            if t.time_sec<=now_sec:
                submit_list.append(t)
            else:
                task_list.append(t)
        self._task_list = task_list
        return submit_list

    def get_task(self,ai_id:str) -> AITask:
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
        return submit

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
        try:
            logger.info(f"start {cmd},{date_time},{purpose},{action}")
            header = ""
            now = int(time.time())
            sec = Utils.to_unix_timestamp_seconds(date_time) if date_time and len(date_time)>0 else 0
            if sec < 10:
                if cmd == TaskCmd.add:
                    return f"\"{date_time}\" is ambiguous. Ask the user for the time."
                elif cmd == TaskCmd.cancel:
                    cmd = TaskCmd.get
                    header = f"\"{date_time}\" is ambiguous. Select from belows. "
            elif sec < (now-10):
                if cmd == TaskCmd.add:
                    return f"\"{date_time}\" is passt time. Ask the user for the time."
            if self.task_repo:
                res = self.task_repo.call( self.bot_id, cmd, date_time, purpose, action)
                if res:
                    logger.info(f"end {header+res}")
                    return header + res
                if cmd == TaskCmd.add:
                    logger.info(f"fail")
                    return "Reserved at "+date_time
                elif cmd == TaskCmd.cancel:
                    logger.info(f"fail")
                    return "Cancelled " + date_time
                elif cmd == TaskCmd.get:
                    logger.info(f"fail")
                    return "Cancelled " + date_time
            else:
                logger.error("task_repo is null")
                return "out of service."
        except Exception as ex:
            logger.exception("")
        return "System Error"

    async def _arun(self, query: str, run_manager: Optional[AsyncCallbackManagerForToolRun] = None) -> str:
        """Use the tool asynchronously."""
        raise NotImplementedError("custom_search does not support async")
    

def main():

    sec1 = int( time.time() )
    dt1 = Utils.from_unix_timestamp_seconds(sec1)
    sec2 = Utils.to_unix_timestamp_seconds(dt1)
    dt2 = Utils.from_unix_timestamp_seconds(sec2)
    print(sec1)
    print(dt1)
    print(sec2)
    print(dt2)

if __name__ == '__main__':
    main()