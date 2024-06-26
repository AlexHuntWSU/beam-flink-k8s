#!/bin/sh

# Source: https://github.com/lyft/flinkk8soperator/blob/master/examples/beam-python/docker-entrypoint.sh
# The container may not be able to find this file, this can be resolved by changing the end of line sequence from CRLF to LF (VSCode).

drop_privs_cmd() {
    if [ $(id -u) != 0 ]; then
        # Don't need to drop privs if EUID != 0
        return
    elif [ -x /sbin/su-exec ]; then
        # Alpine
        echo su-exec
    else
        # Others
        #echo gosu flink
        echo ""
    fi
}

# Add in extra configs set by the operator
if [ -n "$FLINK_PROPERTIES" ]; then
    echo "$FLINK_PROPERTIES" >> "$FLINK_HOME/conf/flink-conf.yaml"
fi

envsubst < $FLINK_HOME/conf/flink-conf.yaml > $FLINK_HOME/conf/flink-conf.yaml.tmp
mv $FLINK_HOME/conf/flink-conf.yaml.tmp $FLINK_HOME/conf/flink-conf.yaml

COMMAND=$@

if [ $# -lt 1 ]; then
    COMMAND="local"
fi
echo "COMMAND: $COMMAND"

if [ "$COMMAND" = "help" ]; then
    echo "Usage: $(basename "$0") (jobmanager|taskmanager|local|help)"
    exit 0
elif [ "$COMMAND" = "jobmanager" ]; then
    echo "Starting Job Manager"
    echo "config file: " && grep '^[^\n#]' "$FLINK_HOME/conf/flink-conf.yaml"
    exec $(drop_privs_cmd) "$FLINK_HOME/bin/jobmanager.sh" start-foreground
elif [ "$COMMAND" = "taskmanager" ]; then
    echo "Starting Task Manager"
    echo "config file: " && grep '^[^\n#]' "$FLINK_HOME/conf/flink-conf.yaml"
    exec $(drop_privs_cmd) "$FLINK_HOME/bin/taskmanager.sh" start-foreground
elif [ "$COMMAND" = "local" ]; then
    echo "Starting local cluster"
    exec $(drop_privs_cmd) "$FLINK_HOME/bin/jobmanager.sh" start-foreground local
fi

exec "$@"