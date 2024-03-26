#!/bin/bash
ID=$1
#ID=12.23-01.11.2023

SCRIPTDIR=$(dirname -- $(realpath ${BASH_SOURCE[0]})) 
#run-all-decomp-evals$ID.jpegS5.log
RESULTSLOGS=$SCRIPTDIR/run-all-decomp-evals$ID.*.log
LOG=$SCRIPTDIR/TEST-all-decomp-evals$ID/partdecomp_results.log
WORK=$SCRIPTDIR/WORK-all-decomp-evals$ID/eval/decomp_fn
#WORK-all-decomp-evals$ID/eval/decomp_fn/fileS5.bs1/file/basic.c
BASICLOG=$SCRIPTDIR/TEST-all-decomp-evals$ID/make.basic_results.log
BASICLOG_=$SCRIPTDIR/TEST-all-decomp-evals$ID/logs/make.basic_results.log
rm $BASICLOG
mkdir -p $(dirname --  $BASICLOG_)
echo "program.func,DECOMP,RECOMP,INLINE-ASM,TEST-EQUIV,BASIC" > $LOG
#for i in $(ls TEST-all-decomp-evals$ID/prd/ ); do 
for i in fileS5.check_format_type; do
echo "pushd TEST-all-decomp-evals$ID/prd/$i"
pushd TEST-all-decomp-evals$ID/prd/$i &> /dev/null
if [[ ! -e basic.c ]]; then 
perl -p -e's#; weak#; // weak#' $WORK/$i/*/basic.c > basic.c
fi
make -f Makefile.prd basic |& tee $BASICLOG_-$i 
XX=$?
res="FAIL"
if (( $XX==0 )); then res="PASS"; fi;
#line="$i,,,,,"
#if (( $(egrep "^$i" $RESULTSLOGS | wc -l)>0 )); then 
#line=$(egrep "^$i" $RESULTSLOGS | tail -n 1 | perl -p -e'chomp($_);s/\s+/,/g;s#,\|,#,#;s/^.*://')
#fi
#echo "$line$res" | perl -p -e's/PASS/PASSED/g;s/FAIL/FAILED/g;s#NOT-RUN#N/A#g;' >> $LOG
echo "$i : $res"
done

#echo -e "Results at: \n$LOG"
