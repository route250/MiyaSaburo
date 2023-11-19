import sys,os,json
import queue
import traceback
import tkinter as tk
from tkinter import ttk
from tkinter import scrolledtext
from DxBotUtils import BotCore, BotUtils

def exp_ui( root, parent, bot:BotCore ):
    def create_prompt():
        try:
            fmt_txt = input_2.get('1.0', tk.END)
            fmt:dict = json.loads(fmt_txt)
            prompt_txt = BotUtils.to_prompt( fmt )
            input_12.delete('1.0', tk.END)
            input_12.insert(tk.END, prompt_txt)
        except:
            traceback.print_exc()

    # LLMへプロンプトを送信する関数
    def send_prompt():
        try:
            prompt1 = input_11.get('1.0', tk.END)
            prompt2 = input_12.get('1.0', tk.END)
            response = bot.Completion(prompt1+"\n"+prompt2)
            output_1.delete('1.0', tk.END)
            output_1.insert(tk.END, response)
        except:
            traceback.print_exc()

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
    # 左側の列
    input_11 = scrolledtext.ScrolledText(parent, height=5)
    input_11.insert(tk.INSERT, p1)
    input_11.grid(row=0, column=0, padx=10, pady=5, sticky="nsew")
    input_12 = scrolledtext.ScrolledText(parent, height=5)
    input_12.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")

    button_1 = tk.Button(parent, text="Send Prompt", command=send_prompt)
    button_1.grid(row=2, column=0, padx=10, pady=5, sticky="ew")

    output_1 = scrolledtext.ScrolledText(parent, height=5)
    output_1.grid(row=3, column=0, padx=10, pady=5, sticky="nsew")

    # 真ん中の列
    button_21 = tk.Button(parent, text="create prompt", command=create_prompt)
    button_21.grid(row=1, column=1, padx=10, pady=5, sticky="ew")
    button_22 = tk.Button(parent, text="Parse Response", command=parse_response_from_llm)
    button_22.grid(row=3, column=1, padx=10, pady=5, sticky="ew")

    # 右側の列
    input_2 = scrolledtext.ScrolledText(parent, height=5)
    input_2.insert(tk.INSERT, p2)
    input_2.grid(row=0, rowspan=2, column=2, padx=10, pady=5, sticky="nsew")

    output_2 = scrolledtext.ScrolledText(parent, height=5)
    output_2.grid(row=3, column=2, columnspan=2, padx=10, pady=5, sticky="nsew")

    # ウィンドウのグリッド設定
    parent.grid_columnconfigure(0, weight=1)
    parent.grid_columnconfigure(1, weight=0)
    parent.grid_columnconfigure(2, weight=1)
    parent.grid_rowconfigure(0, weight=1)
    parent.grid_rowconfigure(1, weight=1)
    parent.grid_rowconfigure(2, weight=0)
    parent.grid_rowconfigure(3, weight=2)

def chat_ui( root, parent, bot:BotCore ):
    # キューの作成
    update_queue = queue.Queue()

    # 分割
    HSplit:tk.PanedWindow = tk.PanedWindow( parent, orient='horizontal', sashwidth=8 )

    # 左側の列
    left_frame:tk.PanedWindow = tk.PanedWindow( HSplit, orient='vertical', sashwidth=8 )
    # 左側の上
    history_textarea = scrolledtext.ScrolledText(left_frame)
    # 左側の下
    input_frame = tk.Frame( left_frame )
    status_label = tk.Label(input_frame)
    status_label.pack( expand=False, fill='x' )
    send_textarea = scrolledtext.ScrolledText(input_frame, height=3)
    send_textarea.pack( expand=True, fill='both')
    send_button = tk.Button(input_frame, text=">>")
    send_button.pack( fill='none' )
    input_frame.pack( expand=True, fill='both' )

    # 右側の列
    # Notebook（タブコンテナ）の作成
    right_panel = ttk.Notebook(HSplit)

    # タブ1のフレームを作成
    info_tab = ttk.Frame(right_panel )
    info_textarea = scrolledtext.ScrolledText(info_tab )
    info_textarea.pack( expand=True, fill='both' )
    info_tab.pack( expand=True, fill='both' )

    # タブ2のフレームを作成
    log_tab = ttk.Frame(right_panel)
    log_textarea = scrolledtext.ScrolledText(log_tab )
    log_textarea.pack( expand=True, fill='both' )
    log_tab.pack( expand=True, fill='both' )

    # タブをNotebookに追加
    right_panel.add(info_tab, text='Info')
    right_panel.add(log_tab, text='Log')

    right_panel.pack( fill='both' )

    # ウィンドウのグリッド設定
    left_frame.add( history_textarea, stretch='first' )
    left_frame.add( input_frame, stretch='first' )
    left_frame.pack( expand=True, fill='both' )
    HSplit.add( left_frame, stretch='first' )
    HSplit.add( right_panel )
    HSplit.pack( expand=True, fill='both' )

    def send_to_bot():
        response_text = send_textarea.get('1.0', tk.END)
        if response_text is not None:
            response_text = response_text.strip()
            if len(response_text)>0:
                if bot.send_message( response_text ):
                    send_textarea.delete('1.0',tk.END)
                    log_textarea.delete(1.0,tk.END)
            else:
                send_textarea.delete('1.0',tk.END)
    send_button.config(command=send_to_bot)
    def ev_enter(ev):
        send_to_bot()
    send_textarea.bind( '<Return>', ev_enter )

    def append_message( role, message:str, emotion:int=0, tts_model:str=None ):
        current:str = history_textarea.get(1.0,tk.END)
        text:str = f"{role}: {message}"
        if len(current.strip())==0:
            history_textarea.delete(1.0,tk.END)
            history_textarea.insert(1.0,text)
        else:
            history_textarea.insert(tk.END,"\n"+text)
        history_textarea.see( tk.END )

    bot.chat_callback = lambda role,message,emotion=0,tts_model=None : append_message(role,message,emotion,tts_model)

    def update_info( data ):
        message:str = json.dumps( data, indent=4, ensure_ascii=False, sort_keys=True )
        info_textarea.delete(1.0,tk.END)
        info_textarea.insert(1.0,message)
    bot.info_callback = lambda data: update_info(data)

    def update_log( message ):
        text:str = BotUtils.to_str(message)
        log_textarea.insert(tk.END, "\n"+text)

    bot.log_callback = lambda message: update_log(message)

    # GUIを更新するためにメインスレッドで定期的に呼び出される関数
    def check_queue():
        try:
            try:
                while not update_queue.empty():
                    func = update_queue.get_nowait()
                    func()  # ラムダ式や関数を実行する
            except:
                traceback.print_exc()
            bot.timer_task()
        finally:
            # 100ms後に再度この関数を呼び出す
            root.after(100, lambda: check_queue() )
    check_queue()

    bot.start()

def debug_ui( bot: BotCore ):

    # GUIを作成する
    root = tk.Tk()
    root.title("LLM Interaction GUI")

    # 画面サイズを縦長に設定（幅x高さ）
    root.geometry("1000x600")

    # Notebook（タブコンテナ）の作成
    notebook = ttk.Notebook(root)
    notebook.grid( row=0, column=0, padx=4, pady=4, sticky="nsew" )

    # タブ1のフレームを作成
    frame1 = ttk.Frame(notebook)
    frame1.grid( row=0, column=0, padx=0, pady=0, sticky="nsew" )

    # タブ2のフレームを作成
    frame2 = ttk.Frame(notebook)
    frame2.grid( row=0, column=0, padx=0, pady=0, sticky="nsew" )

    # タブをNotebookに追加
    notebook.add(frame1, text='Chat')
    notebook.add(frame2, text='Exp')

    # タブ1の内容
    chat_ui( root, frame1, bot )

    # タブ2の内容
    exp_ui( root, frame2, bot )

    root.grid_columnconfigure(0, weight=10)
    root.grid_rowconfigure(0, weight=10)
    # メインループ
    root.mainloop()
    bot.stop()
