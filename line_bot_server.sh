#!/bin/bash

if [ -r ../setup.sh ]; then
    source ../setup.sh
fi

if [ -z "$OPENAI_API_KEY" ]; then
    echo "ERROR: OEPNAI_API_KEY is not present."
    exit 1
fi
if [ -z "$LINE_CHANNEL_ACCESS_TOKEN" ]; then
    echo "ERROR: LINE_CHANNEL_ACCESS_TOKEN is not present."
    exit 1
fi
if [ -z "$LINE_CHANNEL_SECRET" ]; then
    echo "ERROR: LINE_CHANNEL_SECRET is not present."
    exit 1
fi
if [ -z "$LINE_WEBHOOK_PORT" ]; then
    echo "ERROR: LINE_WEBHOOK_PORT is not present."
    exit 1
fi

deactive >/dev/null 2>&1

source ../.Bot/bin/activate

mkdir -p logs

python3 MiyaSaburo/line_bot_server.py

