def main():
    while True:  # 無限ループ
        user_input = input("何か入力してください（終了するには「end」と入力）: ")

        # ユーザーが「end」と入力したらループを抜ける
        if user_input == "end":
            print("プログラムを終了します。")
            break  # while ループを終了

        # ユーザーの入力をプリントする
        print("あなたが入力したのは: " + user_input)

if __name__ == "__main__":
    main()
