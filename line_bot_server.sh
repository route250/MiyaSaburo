#!/bin/bash


if [ -z "$OPENAI_API_KEY" ]; then
    echo "ERROR: OEPNAI_API_KEY is not present."
    exit 1
fi

deactive >/dev/null 2>&1

source ../.Bot/bin/activate

python3 MiyaSaburo/line_bot_server.py

