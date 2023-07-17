
import os
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

app = Flask(__name__)

#環境変数取得
YOUR_CHANNEL_ACCESS_TOKEN = 'Z1oJC74ZloKFspen/GHxF8P/xx70DYD0Oig+0VrKWWJaQ4xKYYtnRx/K69KMtv/a1PprYuuC66RkYK0eR56Nm87vcSocyPVKYJhjHQNvrqPZcpTSg8AifLa/EpBQYG+vlQn2LqnV0rwvRe119z0z5AdB04t89/1O/w1cDnyilFU=' # os.environ["YOUR_CHANNEL_ACCESS_TOKEN"]
YOUR_CHANNEL_SECRET = '0418b62d0703c5ffa6fb05698c92280d' # os.environ["YOUR_CHANNEL_SECRET"]

line_bot_api = LineBotApi(YOUR_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(YOUR_CHANNEL_SECRET)

Repo = BotRepository()

@app.route("/callback", methods=['POST'])
def callback():
    # get X-Line-Signature header value
    signature = request.headers['X-Line-Signature']

    # get request body as text
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    # handle webhook body
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'


@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
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



if __name__ == "__main__":
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
