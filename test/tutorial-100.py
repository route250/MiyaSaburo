import os
from pathlib import Path
from dotenv import load_dotenv
import openai  # OpenAIのクライアントライブラリをインポート
from openai import OpenAI
from openai.types.chat import ChatCompletion

"""OpenAIのchat apiを使ったチャットプログラム"""
def setup_openai_api():
    """
    OpenAI APIをセットアップする関数です。
    .envファイルからAPIキーを読み込み、表示します。
    """
    dotenv_path = os.path.join(Path.home(), 'Documents', 'openai_api_key.txt')
    load_dotenv(dotenv_path)
    
    api_key = os.getenv("OPENAI_API_KEY")
    print(f"OPENAI_API_KEY={api_key[:5]}***{api_key[-3:]}")

def get_response_from_openai(user_input):
    """
    OpenAIのAPIを使用してテキスト応答を取得する関数です。
    """
    # OpenAI APIの設定値
    openai_timeout = 5.0  # APIリクエストのタイムアウト時間
    openai_max_retries = 2  # リトライの最大回数
    openai_llm_model = 'gpt-3.5-turbo'  # 使用する言語モデル
    openai_temperature = 0.7  # 応答の多様性を決定するパラメータ
    openai_max_tokens = 1000  # 応答の最大長
    
    # OpenAIクライアントを初期化します。
    client:OpenAI = OpenAI( timeout=openai_timeout, max_retries=openai_max_retries )
    response:ChatCompletion = client.chat.completions.create(
        model=openai_llm_model,
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": user_input},
        ],
        max_tokens=openai_max_tokens,
        temperature=openai_temperature,
    )
    
    ai_response = response.choices[0].message.content
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
