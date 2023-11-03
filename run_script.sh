#!/bin/bash

# check whether the file args exists or not
if [ -z "$1" ]; then
  echo "Provide python file name"
  exit 1
fi

# execute the given python file
python "$1"