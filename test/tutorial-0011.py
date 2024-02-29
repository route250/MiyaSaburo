import re

def respond_to_user(input):
    """ユーザーの入力に応じて返答する"""
    # 入力パターン（正規表現）と返答のペアを二次元配列で定義
    patterns_responses = [
        (r"こんにちは|こんばんは|おはよう", "挨拶ありがとうございます！どうしましたか？"),
        (r"お疲れ様", "お疲れ様です！今日も一日お疲れさまでした。"),
        (r"ありがとう", "どういたしまして！")
    ]
    
    # 各パターンに対してユーザーの入力をチェック
    for pattern, response in patterns_responses:
        if re.search(pattern, input):
            return response
    
    # 対応する返答がない場合のデフォルトの返答
    return "ごめんなさい、よくわかりません。"

def main():
    try:
        while True:
            user_input = input("何か入力してください（Ctrl+DまたはCtrl+Zで終了）: ")
            response = respond_to_user(user_input)
            print(response)
    except EOFError:
        print("\nプログラムを終了します。")

if __name__ == "__main__":
    main()
