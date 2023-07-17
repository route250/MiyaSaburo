#!/bin/bash


export OPENAI_API_KEY='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'

deactive >/dev/null 2>&1

source ../.Bot/bin/activate

python3 MiyaSaburo/line_bot_server.py

