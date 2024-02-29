import re

def respond_to_user(input):
    """ユーザーの入力に応じて返答する"""
    if re.search(r"こんにちは|こんばんは|おはよう", input):
        return "挨拶ありがとうございます！どうしましたか？"
    elif re.search(r"お疲れ様", input):
        return "お疲れ様です！今日も一日お疲れさまでした。"
    elif re.search(r"ありがとう", input):
        return "どういたしまして！"
    else:
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
