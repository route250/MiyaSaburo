# 音声チャットボット MiyaSaburo

音声チャットボット MiyaSaburoは、音声認識とLangChain、OpenAIのAPIを使用したチャットボットプログラムです。

## 特徴と目的

- AIとの音声対話が可能です。
- 自然な会話を実現するために調整されています。
- AIの発話中にユーザーが割り込むことができます。

## 稼働環境
以下の環境で動作確認しています。
- ubuntu 22.04
- Raspberry Pi OS (bullseye)

### rasberry Pi OS (bullseye)の場合の注意事項
- 追加パッケージ(参考)
  ```
  apt install gfortran libopenblas-dev
  ```
- bullseyeの標準のrustcではtiktokenがインストール出来ません。
  公式の手順を参考にrustcをインストールして下さい
  https://forge.rust-lang.org/infra/other-installation-methods.html


# 起動方法

## 音声チャットボット

## Lineボット

Miyasaburoをlinebotとして起動できます。Flaskで動作します。


注意事項)
 line-bot-sdk 3.1.0を使用して下さい。
 line-bot-sdk 3.2.0は、langchain,openaiとpydanticの要求バージョンが異るのでインストール出来ませんでした。

## LineBot起動方法

1. lineDevelopersでlineボットのチャンネルを作って下さい

2. python仮想環境を作って下さい
```
$ python3 -m venv .Bot
```
3. pythonモジュールをインストールして下さい
```
$ source .Bot/bin/active
$ pip inlstall -U pip
$ pip install flask line-bot-sdk==3.1.0 langchain openai tiktoken lxml matplotlib pandas scipy scikit-learn lxml
```

4. サーバーにコピーして下さい
$ git clone https://github.com/route250/MiyaSaburo.git

5. 設定ファイルを作って下さい
```
$ cd MiyaSaburo
$ vi ../setup.sh
export LINE_CHANNEL_ACCESS_TOKEN='xxxxx'
export LINE_CHANNEL_SECRET='xxxxx'
export LINE_WEBHOOK_PORT='5000'
export OPENAI_API_KEY='xxxxxx'
```

6. ポート開放して下さい
firewall-cmdやufwコマンド等

7. lineボットのwebhookを設定して下さい
https://あなたのサーバ:5000/callback

参考)
仮想マシンへのPortForward
https://redj.hatenablog.com/entry/2019/02/18/025503
仮想マシンの固定IP
https://seekt.hatenablog.com/entry/2022/05/21/102603
