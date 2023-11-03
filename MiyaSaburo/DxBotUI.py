import sys,os,json
import queue
import traceback
import tkinter as tk
from tkinter import scrolledtext
from DxBotUtils import BotCore, BotUtils

def exp_ui( bot ):
    def create_prompt():
        try:
            fmt_txt = input_2.get('1.0', tk.END)
            fmt:dict = json.loads(fmt_txt)
            prompt_txt = BotUtils.to_prompt( fmt )
            input_12.delete('1.0', tk.END)
            input_12.insert(tk.END, prompt_txt)
        except:
            traceback.format_exc

    # LLMへプロンプトを送信する関数
    def send_prompt():
        try:
            prompt1 = input_11.get('1.0', tk.END)
            prompt2 = input_12.get('1.0', tk.END)
            response = bot.Completion(prompt1+"\n"+prompt2)
            output_1.delete('1.0', tk.END)
            output_1.insert(tk.END, response)
        except:
            traceback.format_exc

    # LLMからの返信をパースする関数
    def parse_response_from_llm():
        try:
            response_text = output_1.get('1.0', tk.END)
            fmt_txt = input_2.get('1.0', tk.END)
            fmt:dict = json.loads(fmt_txt)
            parsed_result = BotUtils.parse_response(fmt, response_text)
            json_string = json.dumps(parsed_result, ensure_ascii=False, indent=4)
            output_2.delete('1.0', tk.END)
            output_2.insert(tk.END, json_string)
        except:
            traceback.format_exc
    # 初期値
    p1 = "あなたの目標と計画を設定してください。\n以下のフォーマットで返信してください。"
    p2 = "{\n  \"目標\": \"bbbb\",\n  \"計画\": \"xxxx\"\n}"
    # GUIを作成する
    root = tk.Tk()
    root.title("LLM Interaction GUI")
    # 画面サイズを縦長に設定（幅x高さ）
    root.geometry("1000x800")
    # 左側の列
    input_11 = scrolledtext.ScrolledText(root, height=5)
    input_11.insert(tk.INSERT, p1)
    input_11.grid(row=0, column=0, padx=10, pady=5, sticky="nsew")
    input_12 = scrolledtext.ScrolledText(root, height=5)
    input_12.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")

    button_1 = tk.Button(root, text="Send Prompt", command=send_prompt)
    button_1.grid(row=2, column=0, padx=10, pady=5, sticky="ew")

    output_1 = scrolledtext.ScrolledText(root, height=5)
    output_1.grid(row=3, column=0, padx=10, pady=5, sticky="nsew")

    # 真ん中の列
    button_21 = tk.Button(root, text="create prompt", command=create_prompt)
    button_21.grid(row=1, column=1, padx=10, pady=5, sticky="ew")
    button_22 = tk.Button(root, text="Parse Response", command=parse_response_from_llm)
    button_22.grid(row=3, column=1, padx=10, pady=5, sticky="ew")

    # 右側の列
    input_2 = scrolledtext.ScrolledText(root, height=5)
    input_2.insert(tk.INSERT, p2)
    input_2.grid(row=0, rowspan=2, column=2, padx=10, pady=5, sticky="nsew")

    output_2 = scrolledtext.ScrolledText(root, height=5)
    output_2.grid(row=3, column=2, columnspan=2, padx=10, pady=5, sticky="nsew")

    # ウィンドウのグリッド設定
    root.grid_columnconfigure(0, weight=1)
    root.grid_columnconfigure(1, weight=0)
    root.grid_columnconfigure(2, weight=1)
    root.grid_rowconfigure(0, weight=1)
    root.grid_rowconfigure(1, weight=1)
    root.grid_rowconfigure(2, weight=0)
    root.grid_rowconfigure(3, weight=2)

    # GUIを起動する
    root.mainloop()


def debug_ui( bot ):
    # キューの作成
    update_queue = queue.Queue()

    # GUIを作成する
    root = tk.Tk()
    root.title("LLM Interaction GUI")

    # 画面サイズを縦長に設定（幅x高さ）
    root.geometry("1000x800")
    # 左側の列
    history_textarea = scrolledtext.ScrolledText(root, height=10)
    history_textarea.grid(row=0, column=0, padx=10, pady=5, sticky="nsew")

    send_textarea = scrolledtext.ScrolledText(root, height=3)
    send_textarea.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")

    def send_to_bot():
        response_text = send_textarea.get('1.0', tk.END)
        if bot.add_talk( response_text.strip() ):
            send_textarea.delete('1.0',tk.END)

    send_button = tk.Button(root, text="Send Prompt", command=send_to_bot)
    send_button.grid(row=2, column=0, padx=10, pady=5, sticky="ew")

    # ウィンドウのグリッド設定
    root.grid_columnconfigure(0, weight=1)
    root.grid_rowconfigure(0, weight=10)
    root.grid_rowconfigure(1, weight=3)
    root.grid_rowconfigure(2, weight=1)

    def append_message( role, message ):
        current:str = history_textarea.get(1.0,tk.END)
        text:str = f"{role}: {message}"
        if len(current.strip())==0:
            history_textarea.delete(1.0,tk.END)
            history_textarea.insert(1.0,text)
        else:
            history_textarea.insert(tk.END,"\n"+text)

    bot.chat_callback = lambda role,message: append_message(role,message)

    # GUIを更新するためにメインスレッドで定期的に呼び出される関数
    def check_queue():
        try:
            while not update_queue.empty():
                func = update_queue.get_nowait()
                func()  # ラムダ式や関数を実行する
            # 100ms後に再度この関数を呼び出す
        finally:
            root.after(100, lambda: check_queue() )
    check_queue()
    # GUIを起動する
    root.mainloop()

