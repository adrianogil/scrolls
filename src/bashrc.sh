if [ -z "$SCROLLS_TERMINAL_PYTHON_PATH" ]
then
    export SCROLLS_TERMINAL_PYTHON_PATH=$SCROLLS_TERMINAL_DIR/python/
    export PYTHONPATH=$SCROLLS_TERMINAL_PYTHON_PATH:$PYTHONPATH
fi

alias scrolls-server="python3 $SCROLLS_TERMINAL_DIR/python/scrolls/terminal_server.py"
alias scrolls-client="python3 $SCROLLS_TERMINAL_DIR/python/scrolls/terminal_client.py"
