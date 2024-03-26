#!/usr/bin/env bash

INVOKEDIR=$PWD
SCRIPT=$(realpath ${BASH_SOURCE[0]})
BASE_DIR=$(dirname -- $(realpath -- $SCRIPT))

if [[ -z $PRD_BASE_DIR ]]; then 
   echo "Need to set-up PRD infrastructure first!"
   echo "Exiting."
   exit -1
fi

ln -sf $PRD_BASE_DIR/tools/prdtools .

export RODE0DAYPRD_REPO_DIR=$BASE_DIR
export PRD_RODE0DAY_TOOLS=$BASE_DIR/tools
export APR_EVAL_DIR=$RODE0DAYPRD_REPO_DIR/apr-evals

RODE0DAY_version="19.11"
export RODE0DAY_REPO_DIR="$RODE0DAYPRD_REPO_DIR/$RODE0DAY_version"
RODE0DAY_TAR="$RODE0DAY_version.tar.gz"
RODE0DAY_TAR_URL="https://rode0day.mit.edu/static/archive/$RODE0DAY_TAR"

VENV=$(whoami)"-TEMP-prd-rode0day-venv"

echo "BASE_DIR=$BASE_DIR"
pushd $BASE_DIR &> /dev/null
if [[ ! -f "$BASE_DIR/$RODE0DAY_TAR" ]]; then
echo "wget -q -c $RODE0DAY_TAR_URL"
wget -q -c $RODE0DAY_TAR_URL
fi
if [[ ! -f "$BASE_DIR/$RODE0DAY_TAR" ]]; then
echo "WARNING!!!  Issue downloading rode0day tar file."
echo "Exiting."
popd &> /dev/null
return
fi

if [[ ! -d "$RODE0DAY_REPO_DIR" ]]; then
tar xvzf $RODE0DAY_TAR
fi

# temporary set up before integrating into PRD repo
if [[ ! -z $PRD_BASE_DIR ]]; then 
if [[ ! -z "$VIRTUAL_ENV" && $VIRTUAL_ENV != "$PRD_BASE_DIR/prd-env" ]]; then
  echo "Another Virtual Environment [ $VIRTUAL_ENV ] is set up."
  echo "Please 'deactivate' and rerun to continue"
  popd &> /dev/null
  return 1
fi
# once this is integrated into PRD repo as a submodule, comment out the PRD_BASE_DIR stuff
else
if python3 -m venv $VENV; then
source $VENV/bin/activate
fi
fi

pip install -r requirements.txt

if [[ -z $PYTHONPATH ]] ; then
export PYTHONPATH=$BASE_DIR:$BASE_DIR/apr-evals
else
export PYTHONPATH=$PYTHONPATH:$BASE_DIR:$BASE_DIR/apr-evals
fi


popd&> /dev/null

