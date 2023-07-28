
import os
import time
import queue
import threading

from flask import Flask, request, abort
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
    TextMessage
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
root_logger = logging.getLogger()
fh = logging.FileHandler("logs/linebot-openai.log")
root_logger.addHandler(fh)

logger = logging.getLogger("openai")
logger.setLevel( logging.DEBUG )

app = Flask(__name__)
app.logger.removeHandler(default_handler)
app.logger.addHandler(fh)

botlogger = logging.getLogger("line_bot")
botlogger.setLevel( logging.DEBUG )

#-----------------------------------------
# 処理キュー
msg_accept_queue : queue.Queue = queue.Queue()
msg_exec_queue : queue.Queue = queue.Queue()
msg_running : bool = False

#環境変数取得
LINE_CHANNEL_ACCESS_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
LINE_CHANNEL_SECRET = os.environ["LINE_CHANNEL_SECRET"]
LINE_WEBHOOK_PORT = os.environ["LINE_WEBHOOK_PORT"]

line_config = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
line_webhook_handler = WebhookHandler(LINE_CHANNEL_SECRET)

agent_repo_path = "agents"
os.makedirs(agent_repo_path,exist_ok=True)
bot_repo = BotRepository(agent_repo_path)
news_repo = NewsRepo('ニュース AND 猫 OR キャット OR にゃんこ',qdr="h48")
task_repo = AITaskRepo()

@app.route("/callback", methods=['POST'])
def callback():
    botlogger.error("callback")
    # get X-Line-Signature header value
    signature = request.headers['X-Line-Signature']
    # get request body as text
    body : bytes = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)
    # handle webhook body
    try:
        line_webhook_handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

class RequestData:
    def __init__(self,event:MessageEvent=None, task:AITask=None):
        self.message_event:MessageEvent = None
        self.task:AITask = None
        if event:
            self.userid = event.source.user_id
            self.query = event.message.text
            self.message_event:MessageEvent = event
        elif task:
            self.userid = task.bot_id
            self.query = "It's the reserved time, so you do \"" + task.action + "\" in now for \"" + task.purpose +"\"."
            self.task:AITask = task
        else:
            raise Exception("invalid request?")

@line_webhook_handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event:MessageEvent):
    botlogger.error("handle_message")
    msg_accept_queue.put(event)

def message_accept_thread():
    global msg_running
    while msg_running:
        try:
            event : MessageEvent = msg_accept_queue.get(block=True,timeout=5)
            if event:
                botlogger.debug("accept")
                msg_exec_queue.put( RequestData(event=event) )
                msg_accept_queue.task_done()
        except Exception as ex:
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
                    msg_exec_queue.put(RequestData(task=t))
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
        except Exception as ex:
            time.sleep(0.2)
            pass
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
        reply = agent.llm_run(query)
    except Exception as ex:
        reply = "(orz)"
        botlogger.exception("")
        print(ex)
    try:
        botlogger.debug("response")
        with ApiClient(line_config) as api_client:
            line_bot_api = MessagingApi(api_client)
            if request.message_event:
                line_bot_api.reply_message_with_http_info(
                    ReplyMessageRequest(
                        replyToken=request.message_event.reply_token,
                        messages=[TextMessage(text=reply)]
                    )
                )
            elif request.task:
                line_bot_api.push_message(
                    PushMessageRequest(
                        to=userid,
                        messages=[TextMessage(text=reply)]
                    )
                )
            else:
                logger.error("invalid request. no event and no task")
    except Exception as ex:
        botlogger.exception("")
        print(ex)
    botlogger.info("xxx end")

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