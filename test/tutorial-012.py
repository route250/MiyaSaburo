import re
import time

def respond_to_user(input):
    """ユーザーの入力に応じて返答する"""
    # 入力パターン（正規表現）と返答のペアを二次元配列で定義
    patterns_responses = [
        (r"こんにちは|こんばんは|おはよう", "挨拶ありがとうございます！どうしましたか？"),
        (r"お疲れ様", "お疲れ様です！今日も一日お疲れさまでした。"),
        (r"ありがとう", "どういたしまして！")
    ]
    
    response = ""
    # 各パターンに対してユーザーの入力をチェック
    for pattern, anser in patterns_responses:
        if re.search(pattern, input):
            response = anser
            break
    
    # 対応する返答がない場合のデフォルトの返答
    if not response:
        response = "ごめんなさい、よくわかりません。"
    
    for cc in response:
        time.sleep(0.2)
        yield cc

def main():
    try:
        while True:
            user_input = input("何か入力してください（Ctrl+DまたはCtrl+Zで終了）: ")
            response = respond_to_user(user_input)
            for cc in response:
                print(cc,end="")
            print()
    except EOFError:
        print("\nプログラムを終了します。")

if __name__ == "__main__":
    main()
