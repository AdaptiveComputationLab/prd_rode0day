#!/bin/bash 
YAML=19.11/download/info.yaml

DATE=$(date +"%H.%M-%m.%d.%Y")
id0="-all-decomp-evals-$DATE"
TESTDIR=TEST$id0
WORKDIR=WORK$id0
if [[ -e $TESTDIR ]]; then rm -rf $TESTDIR; fi
if [[ -e $WORKDIR ]]; then rm -rf $WORKDIR; fi
python3 ./tools/rode0day_cfg.py --work-dir $WORKDIR --build-dir $TESTDIR --yml $YAML --eval-prd-decomp-only &> run$id0.log&

id1="-all-apr-evals-$DATE"
TESTDIR=TEST$id1
WORKDIR=WORK$id1
OUT=./RODE0DAY-APR-EVAL-$DATE

if [[ -e $TESTDIR ]]; then rm -rf $TESTDIR; fi
if [[ -e $WORKDIR ]]; then rm -rf $WORKDIR; fi
python3 ./tools/rode0day_cfg.py --work-dir $WORKDIR --build-dir $TESTDIR --yml $YAML &> run$id1.log
ret=$?
echo "$id1 => $ret return value"
rm -rf $OUT
mkdir $OUT
for i in $(ls -d $TESTDIR/apr_evals/baseline/*); do
    cfg=$(basename -- $i)
    bson=$WORKDIR/prd_cfg/$cfg.prd.bson
    src=$i
    name=$(echo $cfg | perl -p -e's/\..*$//')
    ./apr-evals/framework/transform-prd.py --out $OUT --src $src --name $name --bson-cfg $bson --timeout 8
done

echo "#!/bin/bash" > runme-genprog-$DATE.bash
cnt=0
for XX in $(find $OUT -type f -name "runme.bash" ); do
   (( cnt+=1 ))
   if (( $cnt==8 )); then
      echo "sleep 8h" >> runme-genprog-$DATE.bash
      cnt=0
   fi
   echo "   $XX &" >> runme-genprog-$DATE.bash
done
chmod +x runme-genprog-$DATE.bash
./runme-genprog-$DATE.bash &
