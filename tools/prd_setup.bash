#!/bin/bash

# this script should only be run to set up a directory to support automated binary repair via PRD
DESTDIR=$(realpath -- $1)
if [[ -z $DESTDIR ]]; then 
DESTDIR=$PWD
fi

if [[ -z $PRD_BASE_DIR ]]; then
   echo "ERROR! PRD / BinREPARED is not set up!"
   return 0
fi

templates=("Makefile.prd" "prd_include.mk")
for j in ${templates[@]}; do
   s=$PRD_BASE_DIR/tools/templates/$j
   d=$DESTDIR/$j
   if  [[ ! -e $d ]] ; then
       cp $s $d
   fi
done
