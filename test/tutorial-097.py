import os
from pathlib import Path

def main():
    # ユーザーのホームディレクトリのパスを取得します。
    home_path = Path.home()
    
    # ドキュメントフォルダのパスを組み立てます。
    # 注意: Windowsでは "Documents"、macOSやLinuxでは場所が異なる場合があります。
    doc_path = os.path.join(home_path, 'Documents')
    
    print(f"ドキュメントフォルダの内容をチェック中: {doc_path}\n")

    # ドキュメントフォルダ内のファイルとディレクトリをリストアップします。
    for item in os.listdir(doc_path):
        # 完全なパスを取得します。
        item_path = os.path.join(doc_path, item)
        
        # アイテムがディレクトリかファイルかを判断し、表示します。
        if os.path.isdir(item_path):
            print(f"ディレクトリ: {item}")
        else:
            print(f"ファイル: {item}")

    print("\n.openai_key.txtの内容を読み込みます。\n")

    # .openai_key.txtファイルのパスを作成します。
    env_path = os.path.join(doc_path, '.openai_key.txt')
    
    try:
        # ファイルを開いて内容を表示します。
        with open(env_path, 'r') as file:
            for line in file:
                print(f"行: {line.strip()}")  # .strip()で末尾の改行を取り除きます。
    except FileNotFoundError:
        # ファイルが見つからない場合のエラーメッセージを表示します。
        print(f"エラー: ファイル'{env_path}'が見つかりません。")

if __name__ == "__main__":
    main()
