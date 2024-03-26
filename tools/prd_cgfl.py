#!/usr/bin/env python3

import sys, os
import shlex, subprocess
import re

from prd_cfg import *

from prdtools import cgfl,elf


def checkCGFLsuccess(cgfl,known_faulty_fns,cgfl_dir,logf=sys.stdout):
    f=open(f"{cgfl_dir}/cgfl_results.txt",'w')
    success_cnt=0
    for x in known_faulty_fns:
        if x in cgfl:
            success_cnt+=1
            f.write(f"'{x}': SUCCESS\n")
        else:
            f.write(f"'{x}': FAIL\n")
    
    sucrate=float(success_cnt)/float(len(known_faulty_fns))*100
    f.write(f"SUCCESS_RATE: {success_cnt}/{len(known_faulty_fns)}\n")
    f.write(f"PERCENTAGE: {sucrate}\n")
    success=sucrate>0.
    if success:
        print(f"[CGFL] [SUCCESS] Successfully identified {success_cnt} of {len(known_faulty_fns)} faulty function.",file=logf)
    else:
        print(f"[CGFL] [FAILURE] Failed to identify any faulty function [# of faulty functions: {len(known_faulty_fns)}].",file=logf)

    return success

def getCGFL(ext,cgfl_data,topk):
    funcs=None
    if ext!=".list" and isinstance(cgfl_data,dict):
        # uh-oh, something went wrong with RankAggreg (R set up issue?)
        print(f"We have a problem - only have the raw CGFL results data, no aggregation across metrics")
        fncnt=len(cgfl_data["tarantula"])
        top_k_num=min(
            [ max(
                    [10,int(
                        ((float(fncnt)*float(topk))/100.)+0.5
                        )
                    ]
                ),
                fncnt 
            ])
        print(f"INSTEAD, I'm just collecting the unique top-k results [count={top_k_num}]")
        print(f"total # fns: {fncnt}")
        funcs=set()
        #["tarantula","ochiai","op2","barinel","dstar"]
        cgflk=list(cgfl_data.keys())
        idx=0
        last_val=[None for i in range(0,len(cgflk))]
        proceed=[True for i in range(0,len(cgflk))]
        while any(proceed) and idx<len(cgfl_data[cgflk[0]]):
            for i in range(0,len(cgflk)):
                x=cgflk[i]
                cur_val=cgfl_data[x][idx]['value']
                cur_name=cgfl_data[x][idx]['name'].strip()
                if cur_val>0. and proceed[i]:
                    # we're going to finish across ranks and collect all ties
                    # for the last ranked val of each sbfl metric
                    if (len(funcs)>=top_k_num) and (last_val[i]!=cur_val):
                        proceed[i]=False
                    else:
                        funcs.add(cur_name)
                        last_val[i]=cur_val
            idx+=1
    else:
        funcs=cgfl_data
    print(f"topk={top_k_num}, actual number of functions: {len(funcs)}")
    return funcs        


class prd_cgfl:
    def __init__(self,cgfl_dir:str,prd:dict,elfbin:elf.elf_file,seed:int,
            topK:int=35,byte_threshold:int=45,instr_threshold:int=None):
        print(f"[prd_cgfl.__init__] {cgfl_dir}")
        
        self.cgfl_dir=cgfl_dir
        self.prd_=prd
        exe=self.prd_["exe"]
        self.topK=topK
        self.elfinfo=elfbin
        self.exclude_these_syms=cgfl.syms2exclude_
        self.updateSatisfyingSymbols(byte_threshold)
        self.run_id=seed    

    def updateSatisfyingSymbols(self,byte_threshold:int=None):
        print(f"[prd_cgfl.updateSatisfyingSymbols] byte_threshold={byte_threshold}")
        if byte_threshold:
            self.byte_threshold=byte_threshold
        self.satisfied_syms = cgfl.get_satisfying_symbols(self.elfinfo,
            "|".join(self.exclude_these_syms),
            minbytes=self.byte_threshold)
        
    def addSymbolsToExclude(self,exclusions:list):
        self.exclude_these_syms.extend(exclusions)

    def coverage(self,srcdir:str,test_script:str="test.bash",timeout_override:int=None,debug:bool=False):
        
        self.collect_coverage(test_script=test_script,timeout_override=timeout_override)
        covdir=f"{self.cgfl_dir}/cgfl_cov"
        
        return self.process_coverage(covdir=covdir,srcdir=srcdir,debug=debug)

    def collect_coverage(self,test_script:str,timeout_override:int=None):
        """
        we're using the GenProg compatible test.sh script to run CGFL stuff
        """
        
        pt=self.prd_['pos_test_dbiinfo']
        nt=self.prd_['neg_test_dbiinfo']
        exe=self.prd_['exep']
        blddir=self.prd_["build_dir"]
        testdir=os.path.dirname(test_script)
        exepath=f"{testdir}/{exe}" if exe[0]!='/' else exe
        cgfl_res=dict()
        for tt,indx,to_dbi in pt+nt:
            test=f"{tt}{indx}"
            outfile=f"{self.cgfl_dir}/{test}.cg.out"
            logfile=f"{self.cgfl_dir}/{test}.cgfl.log"
            if os.path.exists(outfile) and os.path.getsize(outfile)>0:
                cgfl_res[test]={"ret":0,"out":outfile,"log":logfile}
                continue
            else:
                dbi=["/usr/bin/valgrind",
                "--tool=callgrind",
                f"--log-file={logfile}",
                f"--callgrind-out-file={outfile}"]
                dbi_="'"+" ".join(dbi)+"'"
                cmd=[test_script,exepath,test,dbi_]
                import subprocess
                to=to_dbi if not timeout_override else timeout_override
                print(f"[prd_cgfl][collect_coverage] Running \"{' '.join(cmd)}\"")
                ret=subprocess.run(" ".join(cmd),timeout=to,shell=True)
                cgfl_res[test]={"ret":ret.returncode,"out":outfile,"log":logfile}
        return cgfl_res
    
    def process_coverage(self,covdir:str,srcdir:str,debug:bool=False):
        
        exe=self.prd_['exe']
        resdir=f"{self.cgfl_dir}" #/results"
        cgfl_ = cgfl.cgfl(cb=exe,src=srcdir,inputdir=covdir,outputdir=resdir,
                    valid_funcs=self.satisfied_syms)
        cgfl_.annotate()
        if debug:
            screened=','.join(cgfl_.screen_dicts("|".join(self.exclude_these_syms)))
            print(f"Screened out these functions: {screened}",file=sys.stderr)
        cgfl_.write_raw_dicts()
        cgfl_.write_screened_dicts()
        return self.calculate_suspiciousness_metrics(resdir,self.cgfl_dir)


    def calculate_suspiciousness_metrics(self,resdir,run_R:bool=True):
        exe=self.prd_['name']
        if run_R and not os.path.exists(f"/usr/bin/Rscript"):
            print(f"WARNING: Cannot run Rank-Aggreg - Rscript is not installed")
            print(f"Overriding r-script execution.")
            run_R=False

        pickled_sbfl_dir=f"{self.cgfl_dir}/sbfl_pkl"
        calc_exe=f"{cgfl.script_dir}/calc_susp_pp.py"+\
        f" --ext '.dict' --in {resdir}"+\
        f" --out {self.cgfl_dir} --all_rank"+\
        f" --pickle --dest {pickled_sbfl_dir}"+\
        f" --standardize --print --r_input --r-out {self.cgfl_dir}"+\
        f" --cb {exe} --top-k-percent {self.topK}"+\
        f" --debug --r-seed {self.run_id} "+\
        f" --log {self.cgfl_dir}/susp-fn.log"
        cmd=shlex.split(calc_exe)
        
        proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        sout,serr=proc.communicate()
        for s_,fx in [(sout,f"{resdir}/{exe}.calc_susp_pp.log"),(serr,f"{resdir}/{exe}.rscript.log")]:
            output = s_.decode('utf-8')
            with open(fx,'w') as f:
                f.write(output)
                f.close()
        
        
        # the following should be where the R script
        # for rank-aggregation calculation should be
        if run_R:            
            r_out=f"{self.cgfl_dir}/{exe}.r"
            assert os.path.exists(r_out);
            cmd=shlex.split(f"./{exe}.r")
            #print(f"pushd {self.cgfl_dir};{' '.join(cmd)}; popd")

            proc=subprocess.Popen(cmd, stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT,cwd=self.cgfl_dir,shell=True)
            sout,serr=proc.communicate()
            for s_,fx in [(sout,f"{self.cgfl_dir}/{exe}.cgfl.log")]:
                output = s_.decode('utf-8')
                with open(fx,'w') as f:
                    f.write(output)
                    f.close()
            r_proc_out=f"{self.cgfl_dir}/{exe}.{self.topK}.seed_{self.run_id}.results.log"
            results=None
            with open(r_proc_out,"r") as fr:
                results=" ".join([x.strip() for x in fr.readlines()]).split(" ")
                fr.close()
            assert results
            return results,self.generateTopRankList(self.cgfl_dir,exe,results)
        else:
            sbfl_pkl_file=f"{pickled_sbfl_dir}/sbfl_metrics.pkl"
            import pickle
            sbfl_metrics=pickle.load(open(sbfl_pkl_file,"rb"))
            return sbfl_metrics,(sbfl_pkl_file,".pkl")

        def generateTopRankList(self,exe,results):
            top_rank=f"{self.cgfl_dir}/{exe}.top_rank.list"
            with open(top_rank,"w") as fr:
                fr.write(":".join(results))
                fr.close()
            return top_rank,".list"
        
            # note that if any ground truth is provided, can do something similar to 
            # cgfl_status_pp.bash
            
