
import os
import time
import queue
import threading

from flask import Flask, request, abort, jsonify
from flask.logging import default_handler
from linebot.v3 import (
    WebhookHandler
)
from linebot.v3.exceptions import (
    InvalidSignatureError
)
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    PushMessageRequest,
    TextMessage,
    ApiException
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent
)
from bot_agent import BotRepository, BotAgent
from tools.ChatNewsTool import (
    NewsData,NewsRepo
)
from tools.task_tool import TaskCmd, AITask, AITaskRepo, AITaskTool
from libs.utils import Utils

#-----------------------------------------
# ログ設定
#-----------------------------------------
import logging
from logging.handlers import TimedRotatingFileHandler
log_date_format = '%Y-%m-%d %H:%M:%S'
log_format = '%(asctime)s [%(levelname)s] %(name)s %(message)s'
log_formatter = logging.Formatter(log_format, log_date_format)
root_logger : logging.Logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)
root_fh = TimedRotatingFileHandler('logs/line-bot_log',when='midnight',backupCount=7,interval=1,encoding='utf-8')
root_fh.setFormatter(log_formatter)
root_fh.setLevel(logging.DEBUG)
root_logger.addHandler(root_fh)

console_hdr = logging.StreamHandler()
console_hdr.setLevel( logging.INFO )
console_hdr.setFormatter(log_formatter)
root_logger.addHandler( console_hdr )

openai_logger = logging.getLogger("openai")
openai_logger.setLevel( logging.DEBUG )
openai_logger.propagate = False
openai_fh = TimedRotatingFileHandler('logs/openai_log',when='midnight',backupCount=7,interval=1,encoding='utf-8')
openai_fh.setFormatter(log_formatter)
openai_logger.addHandler(openai_fh)

app = Flask(__name__)
app.logger.removeHandler(default_handler)
app.logger.propagate = True

botlogger = logging.getLogger("line_bot")
botlogger.setLevel( logging.DEBUG )

#-----------------------------------------
# 処理キュー
msg_accept_queue : queue.Queue = queue.Queue()
msg_exec_queue : queue.Queue = queue.Queue()
msg_running : bool = False

#環境変数取得
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN",None)
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET",None)
LINE_WEBHOOK_PORT = os.environ.get("LINE_WEBHOOK_PORT",None)

line_config = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN) if LINE_CHANNEL_ACCESS_TOKEN else None
line_webhook_handler = WebhookHandler(LINE_CHANNEL_SECRET) if LINE_CHANNEL_SECRET else None

agent_repo_path = "agents"
os.makedirs(agent_repo_path,exist_ok=True)
bot_repo = BotRepository(agent_repo_path)
news_repo = NewsRepo('ニュース AND 猫 OR キャット OR にゃんこ')
task_repo = AITaskRepo()

@app.route("/callback", methods=['POST'])
def callback():
    # get X-Line-Signature header value
    signature = request.headers['X-Line-Signature']
    # get request body as text
    body : bytes = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)
    # handle webhook body
    try:
        line_webhook_handler.handle(body, signature)
    except ApiException as e:
        app.logger.warn("Got exception from LINE Messaging API: %s\n" % e.body)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@line_webhook_handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event:MessageEvent):
    msg_accept_queue.put(event)

@app.route("/debug", methods=['POST'])
def debug_service():
    try:
        data = request.json  # 受信したJSONデータを取得
        botlogger.debug("xxx start")

        userid = data.get('userid','debug')
        query = data.get('query','テスト')
        
        agent = bot_repo.get_agent(userid)
        agent.task_repo = task_repo
        agent.news_repo = news_repo
        reply = agent.llm_run(query)
        
        data['reply'] = reply
        return jsonify(data)  # 受信したデータをJSON形式で返信
    except Exception as e:
        return jsonify({'error': str(e)})

from abc import ABC, ABCMeta, abstractmethod, abstractstaticmethod    

class RequestData(ABC):
    def __init__(self, userid: str):
        self.userid = userid

    @abstractmethod
    def response_message(self, talk_id: str, message: str ) -> None:
        pass

class LineRepRequest(RequestData):
    def __init__(self, event: MessageEvent ):
        super().__init__( event.source.user_id )
        self.message_event:MessageEvent = event
        self.query = event.message.text

    def response_message(self, talk_id: str, message: str ) -> None:
        try:
            botlogger.debug("line_reply start")
            with ApiClient(line_config) as api_client:
                line_bot_api = MessagingApi(api_client)
                line_bot_api.reply_message_with_http_info(
                    ReplyMessageRequest(
                        replyToken=self.message_event.reply_token,
                        messages=[TextMessage(text=message)]
                    )
                )
        except Exception as ex:
            botlogger.exception("")
            print(ex)
        botlogger.debug("line_reply end")

class LineTaskRequest(RequestData):
    def __init__(self, task:AITask ):
        super().__init__( task.bot_id )
        self.task:AITask = task
        self.query = f"This is a notice from the schedule timer. It's time for your reservation. Inform time and schedule to user, and do the folowing: \"{Utils.empty_to_blank(task.what_to_do)} {Utils.empty_to_blank(task.how_to_do)}\"."

    def response_message(self, talk_id: str, message: str ) -> None:
        try:
            botlogger.debug("line_push start")
            with ApiClient(line_config) as api_client:
                line_bot_api = MessagingApi(api_client)
                line_bot_api.push_message(
                    PushMessageRequest(
                        to=self.userid,
                        messages=[TextMessage(text=message)]
                    )
                )
        except Exception as ex:
            botlogger.exception("")
            print(ex)
        botlogger.info("line push end")

def message_accept_thread():
    global msg_running
    while msg_running:
        try:
            event : MessageEvent = msg_accept_queue.get(block=True,timeout=5)
            if event:
                botlogger.debug("accept")
                msg_exec_queue.put( LineRepRequest(event=event) )
                msg_accept_queue.task_done()
        except queue.Empty:
            time.sleep(0.2)
        except Exception as ex:
            botlogger.exception("")
            time.sleep(0.2)
        finally:
            pass

def timer_loop_thread():
    global msg_running
    while msg_running:
        try:
            time.sleep(0.5)
            list : list[AITask]= task_repo.timer_event()
            if list:
                for t in list:
                    msg_exec_queue.put(LineTaskRequest(task=t))
            else:
                news_repo.call_timer()
                bot_repo.call_timer()
        except Exception as ex:
            botlogger.exception("")
            time.sleep(0.2)
        finally:
            pass

def message_loop_thread():
    global msg_running
    while msg_running:
        try:
            request:RequestData = msg_exec_queue.get(block=True,timeout=5)
            if request:
                try:
                    message_threadx(request)
                finally:
                    msg_exec_queue.task_done()
        except queue.Empty:
            time.sleep(0.2)
        except Exception as ex:
            botlogger.exception("")
            time.sleep(0.2)
        finally:
            pass

#　これが３スレッド動くはず
def message_threadx(request:RequestData):
    reply = 'zzzzz.......'
    try:
        botlogger.debug("xxx start")
        userid = request.userid
        query = request.query
        agent = bot_repo.get_agent(userid)
        agent.task_repo = task_repo
        agent.news_repo = news_repo
        agent.callback = request.response_message
        reply = agent.llm_run(query)
    except Exception as ex:
        reply = "(orz)"
        botlogger.exception("")
        print(ex)

def main():
    global msg_running
    msg_running = True
    num_threads = 3
    threads = []
    threads.append(threading.Thread(target=timer_loop_thread))    
    threads.append(threading.Thread(target=message_accept_thread))    
    for _ in range(num_threads):
        threads.append(threading.Thread(target=message_loop_thread))
    for t in threads:
        t.daemon = True
        t.start()

    # ssl
    import ssl
    certs_dir = "/usr/local/etc/letsencrypt/live/chickennanban.ddns.net"
    pem_file = certs_dir + '/fullchain.pem'
    Key_file = certs_dir + '/privkey.pem'

    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_context.load_cert_chain( pem_file, Key_file )

    port = Utils.to_int(LINE_WEBHOOK_PORT, 5001)
    app.run( host='0.0.0.0', port=port, ssl_context=ssl_context )

    # スレッドの終了を待機
    msg_running = False
    for t in threads:
        t.join()

if __name__ == "__main__":
    main()