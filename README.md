# 音声チャットボット MiyaSaburo

音声チャットボット MiyaSaburoは、音声認識とLangChain、OpenAIのAPIを使用したチャットボットプログラムです。

## 特徴と目的

- AIとの音声対話が可能です。
- 自然な会話を実現するために調整されています。
- AIの発話中にユーザーが割り込むことができます。

## 起動方法


## LineBot起動方法

lineDevelopersでlineボットのチャンネルを作って下さい

サーバーにコピーして下さい
$ git clone https://github.com/route250/MiyaSaburo.git

設定ファイルを作って下さい
$ cd MiyaSaburo
$ vi ../setup.sh
export LINE_CHANNEL_ACCESS_TOKEN='xxxxx'
export LINE_CHANNEL_SECRET='xxxxx'
export LINE_WEBHOOK_PORT='5000'
export OPENAI_API_KEY='xxxxxx'

ポート開放して下さい
firewall-cmdやufwコマンド等

lineボットのwebhookを設定して下さい
https://あなたのサーバ:5000/callback


