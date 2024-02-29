def respond_to_user(input):
    """ユーザーの入力に応じて返答する"""
    if input == "こんにちは":
        return "こんにちは！どうしたの？"
    elif input == "おはよう":
        return "おはようございます！今日はいい天気ですね。"
    elif input == "こんばんは":
        return "こんばんは。今日の夜は何をして過ごす予定ですか？"
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
