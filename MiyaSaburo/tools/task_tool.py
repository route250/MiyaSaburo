import queue
import time
from zoneinfo import ZoneInfo
from enum import Enum
from pydantic import Field, BaseModel
from typing import Optional, Type, Callable
from datetime import datetime, timezone
import threading
from langchain.callbacks.manager import AsyncCallbackManagerForToolRun, CallbackManagerForToolRun
from langchain.tools.base import BaseTool

JST = ZoneInfo("Asia/Tokyo")

def to_unix_timestamp_seconds( date_time:str) -> int:
    # 日付文字列をdatetimeオブジェクトに変換
    dt_object = datetime.strptime(date_time, '%Y/%m/%d %H:%M:%S')
    # Unix時間に変換 (秒単位)
    time = int(dt_object.replace(tzinfo=JST).timestamp())
    return time
def from_unix_timestamp_seconds(unix_time: int) -> str:
    # Unix時間をdatetimeオブジェクトに変換
    dt_object = datetime.fromtimestamp(unix_time, JST)
    # フォーマットに変換して返す
    return dt_object.strftime('%Y/%m/%d %H:%M:%S')
class TaskCmd(str, Enum):
    add = 'add'
    cancel = 'cancel'
    get = 'get'

class AITask:
    _instance_count = 0
    def __init__(self, ai_id:str, date_time:str, task:str ):
        self.task_id = AITask._instance_count
        AITask._instance_count+=1
        self.ai_id = ai_id
        self.date_time = date_time
        self.time_sesc = to_unix_timestamp_seconds(date_time)
        self.task = task

class AITaskRepo:

    def __init__(self):
        self._task_list : list[AITask] = list[AITask]()
        self._last_call = 0
        self.task_queue = queue.Queue()

    def call( self, bot_id:str, cmd : TaskCmd, date_time : str, task: str ):
        if cmd == TaskCmd.add:
            task = AITask( bot_id, date_time, task )
            self._task_list.append(task)
            return "Reserved at "+date_time
        elif cmd == TaskCmd.cancel:
            tt = []
            for t in self._task_list:
                if t.date_time != date_time or (task and t.task != task):
                    tt.append(t)
            removed = len(self._task_list)-len(tt)
            if removed>0:
                self._task_list = tt
                return "Cancelled from " + date_time
            else:
                return "Not found task in " + date_time
        elif cmd == TaskCmd.get:
            if len(self.task_task_list_map)>0:
                return " ".join([ f"{t.date_time} {t.task}" for t in self._task_list])
            else:
                return "no tasks."

    def timer_event(self) -> list[AITask]:
        now_sec = int( time.time() )
        task_list = []
        submit_list = []
        for t in self._task_list:
            if t.time_sesc<=now_sec:
                submit_list.append(t)
            else:
                task_list.append(t)
        self._task_list = task_list
        return submit_list

    def get_task(self,ai_id:str) -> AITask:
        now_sec = int( time.time() )
        task_list = []
        submit = None
        for t in self._task_list:
            if submit or t.ai_id != ai_id or t.time_sesc>now_sec:
                task_list.append(t)
            else:
                submit = t
        self._task_list = task_list
        return submit

# 入力パラメータを定義するモデル
class AITaskInput(BaseModel):
    cmd: TaskCmd
    date_time: str = Field( ..., description='Time to reserve a task by YYYY/MM/DD HH:MM:SS')
    task: str = Field( ..., description='Instructions for you to perform this task')

class AITaskTool(BaseTool):

    name = "AITaskTool"
    description = ( "Schedule your tasks for the future." )
    # 入力パラメータのスキーマを定義
    args_schema: Optional[Type[BaseModel]] = AITaskInput

    bot_id : str = None
    task_repo: AITaskRepo = None

    def _run( self, cmd:TaskCmd, date_time: str='', task:str='', run_manager: Optional[CallbackManagerForToolRun] = None ) -> str:
        try:
            res = self.task_repo.call( self.bot_id, cmd, date_time, task )
            if res:
                return res
            if cmd == TaskCmd.add:
                return "Reserved at "+date_time
            elif cmd == TaskCmd.cancel:
                return "Cancelled " + date_time
            elif cmd == TaskCmd.get:
                return "Cancelled " + date_time
        except Exception as ex:
            print(ex)
        return "System Error"

    async def _arun(self, query: str, run_manager: Optional[AsyncCallbackManagerForToolRun] = None) -> str:
        """Use the tool asynchronously."""
        raise NotImplementedError("custom_search does not support async")
    

def main():

    sec1 = int( time.time() )
    dt1 = from_unix_timestamp_seconds(sec1)
    sec2 = to_unix_timestamp_seconds(dt1)
    dt2 = from_unix_timestamp_seconds(sec2)
    print(sec1)
    print(dt1)
    print(sec2)
    print(dt2)

if __name__ == '__main__':
    main()