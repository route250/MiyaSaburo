
import os
import time
import queue
import threading

from flask import Flask, request, abort

from linebot import (
    LineBotApi, WebhookHandler
)
from linebot.exceptions import (
    InvalidSignatureError
)
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
)
from bot_agent import BotRepository, BotAgent

import logging
logger = logging.getLogger("openai")
logger.setLevel( logging.DEBUG )
fh = logging.FileHandler("logs/linebot-openai.log")
logger.addHandler(fh)

app = Flask(__name__)

# 処理キュー
msg_accept_queue : queue.Queue = queue.Queue()
msg_exec_queue : queue.Queue = queue.Queue()
msg_running : bool = False

#環境変数取得
LINE_CHANNEL_ACCESS_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
LINE_CHANNEL_SECRET = os.environ["LINE_CHANNEL_SECRET"]

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

Repo = BotRepository()

@app.route("/callback", methods=['POST'])
def callback():
    # get X-Line-Signature header value
    signature = request.headers['X-Line-Signature']
    # get request body as text
    body : bytes = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)
    # handle webhook body
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event:MessageEvent):
    msg_accept_queue.put(event)

def timer_loop_thread():
    global msg_running
    while msg_running:
        try:
            time.sleep(0.2)
        except Exception as ex:
            time.sleep(0.2)
        finally:
            pass

def message_accept_thread():
    global msg_running
    while msg_running:
        try:
            event = msg_accept_queue.get(block=True,timeout=5)
            if event:
                msg_accept_queue.task_done()
                msg_exec_queue.put( event )
        except Exception as ex:
            time.sleep(0.2)
        finally:
            pass

def message_loop_thread():
    global msg_running
    while msg_running:
        try:
            event:MessageEvent = msg_exec_queue.get(block=True,timeout=5)
            if event:
                try:
                    message_threadx(event)
                finally:
                    msg_exec_queue.task_done()
        except Exception as ex:
            time.sleep(0.2)
            pass
        finally:
            pass

def message_threadx(event:MessageEvent):
    reply = 'zzzzz.......'
    try:
        userid = event.source.user_id
        query = event.message.text
        agent = Repo.get_agent(userid)
        reply = agent.llm_run(query)
    except Exception as ex:
        print(ex)
    try:
        line_bot_api.reply_message( event.reply_token, TextSendMessage(text=reply))
    except Exception as ex:
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
    pem_file = 'certs/fullchain.pem'
    Key_file = 'certs/privkey.pem'

    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
    ssl_context.load_cert_chain( pem_file, Key_file )
#    app.run()
    #port = int(os.getenv("PORT", 5000))
    #app.run(host="0.0.0.0", port=port)
    app.run( host='0.0.0.0', ssl_context=ssl_context )

    # スレッドの終了を待機
    msg_running = False
    for t in threads:
        t.join()

if __name__ == "__main__":
    main()