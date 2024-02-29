import os
from pathlib import Path
from dotenv import load_dotenv

def load_config():
    # .env ファイルのパスを指定して読み込む
    dotenv_path = os.path.join( Path.home(), 'Documents', 'openai_key.txt' )
    load_dotenv(dotenv_path)
    # 環境変数を使用
    api_key = os.getenv("OPENAI_API_KEY")
    # 環境変数の値を表示して確認
    print(f"OPENAI_API_KEY={api_key[:5]}***{api_key[-3:]}")

def main():
    load_config()

if __name__ == "__main__":
    main()