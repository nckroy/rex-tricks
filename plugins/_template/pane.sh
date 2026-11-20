#!/bin/sh
# What runs in the pane. Settings arrive as environment variables.
while :; do
  clear
  date '+%A %e %B, %H:%M:%S'
  sleep "${MY_PLUGIN_INTERVAL:-1}"
done
