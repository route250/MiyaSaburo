import os
from pathlib import Path
from dotenv import load_dotenv
import openai  # OpenAIのクライアントライブラリをインポート
from openai import OpenAI
from openai.types.chat import ChatCompletion

"""
OpenAIのchat apiを使ったチャットプログラム
メッセージ履歴を追加
"""

def setup_openai_api():
    """
    OpenAI APIをセットアップする関数です。
    .envファイルからAPIキーを読み込み、表示します。
    """
    dotenv_path = os.path.join(Path.home(), 'Documents', 'openai_api_key.txt')
    load_dotenv(dotenv_path)
    
    api_key = os.getenv("OPENAI_API_KEY")
    print(f"OPENAI_API_KEY={api_key[:5]}***{api_key[-3:]}")

global_messages=[]
def get_response_from_openai(user_input):
    """
    OpenAIのAPIを使用してテキスト応答を取得する関数です。
    """
    global global_messages

    # OpenAI APIの設定値
    openai_timeout = 5.0  # APIリクエストのタイムアウト時間
    openai_max_retries = 2  # リトライの最大回数
    openai_llm_model = 'gpt-3.5-turbo'  # 使用する言語モデル
    openai_temperature = 0.7  # 応答の多様性を決定するパラメータ
    openai_max_tokens = 1000  # 応答の最大長
    # リクエストを作ります
    local_messages = []
    local_messages.append( {"role": "system", "content": "You are a helpful assistant."} )
    for m in global_messages:
        local_messages.append( m )
    local_messages.append( {"role": "user", "content": user_input} )
    
    # OpenAIクライアントを初期化します。
    client:OpenAI = OpenAI( timeout=openai_timeout, max_retries=openai_max_retries )
    # 通信します
    response:ChatCompletion = client.chat.completions.create(
        model=openai_llm_model,
        messages=local_messages,
        max_tokens=openai_max_tokens,
        temperature=openai_temperature,
    )
    # AIの応答を取得します
    ai_response = response.choices[0].message.content
    # 履歴に記録します。
    global_messages.append( {"role": "user", "content": user_input} )
    global_messages.append( {"role": "assistant", "content": ai_response} )
    # AIの応答を返します
    return ai_response

def process_chat():
    """
    ユーザーからの入力を受け取り、OpenAI APIを使用して応答を生成し、
    その応答を表示する関数です。
    """
    try:
        while True:
            user_input = input("何か入力してください（Ctrl+DまたはCtrl+Zで終了）: ")
            response = get_response_from_openai(user_input)
            print(response)
    except EOFError:
        print("\nプログラムを終了します。")

def main():
    """
    メイン関数です。APIのセットアップを行い、チャット処理を開始します。
    """
    setup_openai_api()
    process_chat()

if __name__ == "__main__":
    main()


import os
from pathlib import Path
from dotenv import load_dotenv
import openai

def setup_openai_api():
    """OpenAI APIキーのセットアップ"""
    dotenv_path = os.path.join(Path.home(), 'Documents', '.env')
    load_dotenv(dotenv_path)
    openai.api_key = os.getenv("OPENAI_API_KEY")

def get_response_from_openai(messages):
    """OpenAI APIを使用してテキスト応答を取得"""
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=messages,
        max_tokens=1000,
        temperature=0.7,
    )
    return response.choices[0].message['content']

def handle_chat():
    """ユーザー入力に基づいてチャット処理を行う"""
    messages = []
    try:
        while True:
            user_input = input("何か入力してください（Ctrl+DまたはCtrl+Zで終了）: ")
            messages.append({"role": "user", "content": user_input})
            
            if len(messages) > 10:
                messages = messages[-10:]  # メッセージ履歴を最新の10件に保持
            
            response = get_response_from_openai(messages)
            print(response)
            messages.append({"role": "assistant", "content": response})  # 応答を履歴に追加
            
            if len(messages) > 10:
                messages = messages[-10:]  # 応答を含めても履歴を最新の10件に保持
    except EOFError:
        print("\nプログラムを終了します。")

def main():
    """メイン関数"""
    setup_openai_api()
    handle_chat()

if __name__ == "__main__":
    main()
