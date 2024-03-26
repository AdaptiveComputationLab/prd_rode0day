#!/usr/bin/env python3

import sys, os, copy, subprocess
sys.path.append(f"{os.getenv('PRD_BASE_DIR')}/tools")
sys.path.insert(0,f"{os.getenv('PRD_BASE_DIR')}/tools/prdtools")
sys.path.append(f"{os.getenv('APR_EVAL_DIR')}")

#from prdtools import elf,decompile
import elf
import decompile
from framework import testing
import prog_cfg
import prd_cgfl

from framework import testing, program

from shutil import copy as shcopy
from shutil import copytree

support={'binaries':True,'stripped':False}

binary_info_file="binary_info.json"

def generate_binary_info(outdir:str,binary:str,debug:bool=False):
    x=collect_binary(os.path.realpath(binary),debug)
    dump_binary_info(f"{outdir}/{binary_info_file}",x)
    return x

def collect_binary(binary:str,debug:bool=False):
    
    return elf.elf_file(binary,True,debug,True)

def get_binary_info(outdir:str,binary:str,debug:bool=False):
    binfo=f"{outdir}/{binary_info_file}"
    if os.path.exists(binfo):
        e=elf.elf_file(debug=debug)
        e.load_json(binfo)
        return e
    else:
        return generate_binary_info(outdir,binary,debug)

def dump_binary_info(outjson:str,bininfo:elf.elf_file):
    assert outjson and bininfo;
    if not os.path.exists(os.path.dirname(outjson)):
        os.makedirs(os.path.dirname(outjson))
    bininfo.dump_json(outjson)

class prd_cfg(prog_cfg.prog_cfg):
    enabled_apr={'GENPROG':True,'PROPHET':True,'ANGELIX':False}
    prd_fn_results=dict()
    use_prdbuild=False

    def update_for_prd(self,proginfo,relevant_):
        
        prdprog=copy.deepcopy(proginfo)
        prdprog['build_info']['build_src']=relevant_
            
        prdprog['program_info']['exe']=f"{self.prd_build_info['exe']}.trampoline.bin"
        if not self.use_prdbuild:
            prdprog['build_info']['build_type']='MAKEFILE'
            prdprog['build_info']['build_targets']={'FULL':'clean all','EXE':'clean all'}
            prdprog['build_info']['compile_cmd']=['make', '-f', 'Makefile.prd', 'clean', 'all']
        else:
            prdprog['build_info']['build_type']='SHELL'
            del prdprog['build_info']['build_targets']
            prdprog['build_info']['compile_cmd']=['./prdbuild.sh']

        del prdprog['build_info']['exe_out_dir']
        prdprog['PRD']=True
        return prdprog
    

    def setup_prd_build(self):
        prd_base_dir=os.getenv("PRD_BASE_DIR",None)
        decomptool_dir=os.getenv("PART_DECOMP_DIR",None)
        assert prd_base_dir and decomptool_dir
        relexp=self.getExe(); exe=os.path.basename(relexp); exep=os.path.realpath(f"{self.sourceDir()}/{relexp}")
        prd_build_info=self.getBaseDirs();
        default_dirs={
            'prd_cfg':f"{self.workRootDir()}/prd_cfg",
            'hexrays_script':decomptool_dir,
            'prd_base':prd_base_dir,
            'template':f"{prd_base_dir}/tools/templates",
            'rel_exep':relexp,
            'exe':exe,
            'exep':exep,
            'pname':self.getProgram(),
            'prebuilt':self.getBuildDir(),
            'cgfl':f"{self.workRootDir()}/cgfl",
            'decompile':f"{self.workRootDir()}/decomp",
            'raw_decomp':f"{self.workRootDir()}/raw_decomp_out",
            'apr_eval_root':f"{self.destDir()}/apr_evals",
            'prd_destroot':f"{self.destDir()}/prd",
            'prd_pkl':f"{self.destDir()}/prd/pkl",
            'inline_asm_cmd':f"{prd_base_dir}/tools/create_asm_multidetour.py"+\
                ' --json-in prd_info.json'+\
                ' --file-to-objdump libhook.so'+\
                f" --source {exe}_recomp.c"
        }
        for k,v in default_dirs.items():
            if not prd_build_info.get(k,None):
                prd_build_info[k]=v
        return prd_build_info

    def __init__(self,base_dir:dict,cfg,sanitychk:bool=False,debug:bool=False,dirToStoreDecomps:str=None,
        build_cfg:dict=None,use_prdbuild:bool=None):
        # init: initialize the directory
        # static : enable static compilation (if applicable)
        # config : apply the configuration command
        # compile : compile using the compilation command
        super().__init__(base_dir=base_dir,cfg=cfg,sanitychk=sanitychk,debug=debug,
            build_cfg=build_cfg)
        if use_prdbuild:
            self.use_prdbuild=use_prdbuild
        self.prd_build_info=self.setup_prd_build()

    
        if debug:
            print(f"Collecting binary information from '{self.prd_build_info['exep']}'",file=sys.stderr)
        self.binary_info=get_binary_info(self.prd_build_info['source'],self.prd_build_info['exep'])
        
        #self.template_dir=f"{self.prd_dir}/tools/templates"
        #self.bin=self.progcfg["program_info"]["exe"]
    
    def dump_binary_info(self,json_out:str):
        self.binary_info.dump_json(json_out)
    
    def getExePath(self):
        return super().getExe()

    def check_compile_log(self,compile_log):
        print(compile_log)
        print(os.getcwd())
        assert os.path.exists(compile_log)
        cmd=f"egrep -c 'ERROR \! Unbound functions\!' {compile_log}"
        x=subprocess.Popen(cmd,shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        ret=x.wait()
        serr=x.stderr.read().decode('utf-8')
        sout=x.stdout.read().decode('utf-8')
        #print(f"RET:{ret}\nSERR:{serr}\nSOUT:{sout}")
        res=int(sout.strip())
        
        return res==0

    def generate_inline_asm(self,prd_dir_info):
        cmd=prd_dir_info['inline_asm_cmd']
        destdir=prd_dir_info['dest']
        id_=prd_dir_info['id']
        outfile=cmd.strip().rsplit(' ',1)[-1]
        inlineasm_f=f"{destdir}/{id_}.inlineasm.log"
        fh=open(inlineasm_f,"w")
        p=subprocess.Popen(cmd,shell=True,cwd=destdir,
            stdout=fh,stderr=subprocess.STDOUT)
        pret= p.wait()
        #print(f"[INLINE ASM] output: >>\n{p.stdout.read().decode('utf-8')}\n<<",
        #    file=fh)
        dret=1
        outpath=f"{destdir}/{outfile}"
        if os.path.exists(f"{outpath}.orig"):
            diffcmd=f"diff {outfile} {outfile}.orig"
            fh.write(f"Checking INLINE ASM output results by diffing.\n")
            d=subprocess.Popen(diffcmd,shell=True,cwd=prd_dir_info['dest'],
                stdout=fh,stderr=subprocess.STDOUT)
                #stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
            # if the diffs are the same, then inline asm insertion failed
            # diff returns 0 if they're the same, else it returns 1 when inputs differ
            #print(f"[INLINE ASM] DIFF results: >>\n{d.stdout.read().decode('utf-8')}\n<<",
            #    file=fh)
            
            dret=1 if (d.wait()==0) else 0
        else: 
            print(f"[ERROR] {outfile}.orig does not exist.",file=fh)
        print(f"INLINE ASM : {'SUCCESS' if dret==0 else 'FAIL'}.", file=fh)
        print(f"[INLINE ASM] | {prd_dir_info['id']} | {'SUCCESS' if dret==0 else 'FAIL'}.")
        fh.close()
        return dret,inlineasm_f


        

    def build_prd_eval(self,prdsubcfg:str,prd_dir_info:dict,id_:str,seed:int):
        build_passes,recomp_passes,inlineasm_passes,tests_pass,test_results=(
                "NOT-RUN","NOT-RUN","NOT-RUN","NOT-RUN",None
        )
        
        prd_build_cfg={
            'init':True,
            'static':False,
            'config':False,
            'compile':True,
            'requires_comp_success':False
        }
        prd_compile_log=f"{prd_dir_info['source']}/{id_}.compile.log"
        prd_inline_log=f"{prd_dir_info['source']}/{id_}.inlineasm.log"
        prd_testresults_log=f"{prd_dir_info['source']}/{id_}.testing.log"

        prdprogcfg=prog_cfg.prog_cfg(
            base_dir=prd_dir_info,
            cfg=prdsubcfg,
            sanitychk=True,
            debug=True,
            build_cfg=prd_build_cfg
        )

        build_ret= prdprogcfg.check_build(id_)
        build_passes= (build_ret==0)
        recomp_passes= build_passes and self.check_compile_log(prdprogcfg.getCompileLog())
        shcopy(prdprogcfg.getCompileLog(),prd_compile_log)
        
        if recomp_passes:
            ret,inline_f=self.generate_inline_asm(prd_dir_info)
            shcopy(inline_f,prd_inline_log)
            inlineasm_passes=(ret==0)
        

        prdprogcfg.create_seed_file(seed)
        
        #summary=f"{id_} PRD Results\n"
        if recomp_passes and (inlineasm_passes==True):
            prdprogcfg.check_test_setup()
            tests_pass,test_results=prdprogcfg.run_tests(expect_neg_to_fail=False)
            print(f"[PRD TEST-EQUIV RESULTS] | {id_} | {'SUCCESS' if tests_pass else 'FAIL'}.")
            shcopy(prdprogcfg.getTestLog(),prd_testresults_log)
        result={
            'id':id_,
            'decomp_passes':True,
            'build_passes':build_passes,
            'recomp_passes':recomp_passes,
            'inlineasm_passes':inlineasm_passes,
            'tests_pass':tests_pass,
            'test_results':test_results,
            'prog_cfg':prdprogcfg,
            'bson':prdsubcfg
            }
        return result

    def get_prd_results_from_file(self,infile):
        results=prog_cfg.readpickle(infile)
        return results

    def cgfl(self,cgfldir,seed,top_k,byte_thresh,dbitest,logf=sys.stdout):
        print(f"[START] CGFL -- {self.prd_build_info['exe']}")
        fault_info={'files':[],'funcs':[]}
        
        for x in range(1,self.numNegTests()+1):
            fault=self.getNegTestFaultLocale(x-1)
            if fault:
                for floc in list(fault_info.keys()):
                    flt=fault.get(floc,None)
                    fault_info[floc].extend(flt)
        buildtestinfo={
            'name':self.prd_build_info['pname'],
            'exe':self.prd_build_info['exe'],
            'exep':self.prd_build_info['exep'],
            'pos_test_info':[
                ('p',x,self.getPosTestTimeout(x-1,False)) for x in range(1,self.numPosTests()+1)
                ],
            'pos_test_dbiinfo':[
                ('p',x,self.getPosTestTimeout(x-1,True)) for x in range(1,self.numPosTests()+1)
                ],
            'neg_test_info':[
                ('n',x,self.getNegTestTimeout(x-1,False)) for x in range(1,self.numNegTests()+1)
                ],
            'neg_test_dbiinfo':[
                ('n',x,self.getNegTestTimeout(x-1,True)) for x in range(1,self.numNegTests()+1)
                ],
            'fault':fault_info,  
            'build_dir':self.prd_build_info['prebuilt']
        }
        if not os.path.exists(cgfldir):
            os.makedirs(cgfldir)
        # CGFL stage
        cgfl_=prd_cgfl.prd_cgfl(cgfl_dir=cgfldir,
            prd=buildtestinfo,
            elfbin=self.binary_info,
            seed=seed,topK=top_k,
            byte_threshold=byte_thresh)
        cgfl_data,datafile_info=cgfl_.coverage(srcdir=super().getSrcDir(),
            test_script=dbitest,
            timeout_override=None,
            debug=False
            )

        funcs=prd_cgfl.getCGFL(datafile_info[1],cgfl_data,top_k)
        ground_truth=fault_info['funcs']
        cgfl_success=False
        if len(ground_truth)>0:
            print(f"[CGFL] [{self.prd_build_info['exe']}] Ground truth available to evaluate CGFL effectiveness.",file=logf)
            cgfl_success=prd_cgfl.checkCGFLsuccess(funcs,ground_truth,cgfl_dir=cgfldir,logf=logf)
        else:
            print(f"[CGFL] [{self.prd_build_info['exe']}] WARNING!! No ground truth available to evaluate CGFL effectiveness.",file=logf)
        print(f"[DONE] CGFL -- {self.prd_build_info['exe']}")
        cgfl_results={
            'ground_truth':copy.copy(ground_truth),
            'funcs':funcs,
            'success':cgfl_success
        }
        return buildtestinfo,funcs,cgfl_results
        
    def decompile(self,resultdir:str,workdir:str,
        funcs:list,id_:str,enableGhidraForCPPfails:bool=False):
        print(f"[START] DECOMPILATION -- {self.prd_build_info['exe']}")
        print(f"[DECOMPILATION] Functions to be decompiled '{funcs}'")
        #$TOOL_DIR/prdtools/decompile.py -p $cb_build/$cb --target-list $din/$cb.$i.target_list \
        #    -l $dout/multidecomp.log -o $dout -s $DECOMP_TOOL_DIR -f $f
        hexrays_scriptdir=self.prd_build_info['hexrays_script']
        
        decompile.ghidra_enable=enableGhidraForCPPfails
        decomp_target=f"{workdir}/{id_}.target"
        decomp_log=f"{workdir}/{id_}.prd_decomp.log"
        decompresdir=None
        needed_files=None
        
        decompresdir,ret=decompile.call_hexrays(self.prd_build_info['exep'],
            funcs,
            hexrays_scriptdir,
            decomp_target,
            resultdir,
            decomp_log,
            self.prd_build_info['raw_decomp'],
            True
            )
        if ret == 0:
            needed_files=self.get_prd_needed(decompresdir)
            print(f"[DONE] DECOMPILATION -- {self.prd_build_info['exe']} [SUCCESS: {funcs}]")
        else:
            print(f"[DONE] DECOMPILATION -- {self.prd_build_info['exe']} [FAIL   : {funcs}]")
        return decompresdir,needed_files

            
    def get_prd_needed(self,decompresdir):
        template_dir=self.prd_build_info['template']
        exe=self.prd_build_info['exe']
        needed_files=[ 
            self.prd_build_info['exep'],
            f"{template_dir}/Makefile.prd",
            f"{template_dir}/script.ld",
            f"{template_dir}/prdbuild.sh",
            f"{decompresdir}/{exe}_recomp.c",
            f"{decompresdir}/defs.h",
            f"{decompresdir}/prd_include.mk",
            f"{decompresdir}/resolved-types.h",
            f"{decompresdir}/prd_info.json"
            ]
        return needed_files
    
    def generatePRDbson(self,bsondestfile:str,resultdir:str,need:list,reducepath:bool=False):
        destdir=os.path.dirname(os.path.realpath(bsondestfile))
        if not os.path.exists(destdir):
            os.makedirs(destdir)
        print([destdir,resultdir])
        cpath=os.path.commonpath([destdir,resultdir])
        len_cpath=len(cpath)
        #need=copy.copy(needed)
        if reducepath:
            if len_cpath>1:
                for i in range(0,len(need)):
                    if need[i].startswith(cpath):
                        need[i]="."+need[i][len_cpath:]
        prdprog=self.update_for_prd(self.getProgramCfg(),need)
        prog_cfg.writebson(bsondestfile,prdprog)
        return bsondestfile

    def get_summary_line(self,results):
        r_=[
            ('CGFL',results['cgfl_passes']),
            ('CGFL-GT',results['ground_truth_in_valid']),
            ('DECOMP',results['decomp_passes']), 
            ('RECOMP',results['recomp_passes']), 
            ('INLN-ASM',results['inlineasm_passes']),
            ('TESTS',results['tests_pass'])
          ]
        fld_=" {:9}"
        hfmt='{:30s} |'
        f=['program.func']
        s=[]
        for i,X_ in enumerate(r_):
            y,x=X_
            if x is not None:
                f.append(y)
                hfmt+=fld_
                v=x
                if not isinstance(x,str):
                    v='PASS' if x else 'FAIL'
                s.append(v)
        summary_=[results['id']]+s
        summary=hfmt.format(*summary_)
        #f"{results['id']:25s} | {summary_[0]:7} {summary_[1]:7} {summary_[2]:7} {summary_[3]:7} {summary_[4]:7}"
        summary_hdr=hfmt.format(*f)
        return summary,summary_hdr



    def eval_fncs(self,fncs,fid_,dirinfo,test,prd_build_info,
        ghidra,successes_:tuple):
        cgfl_success,gndtruth_success=successes_
        fn_decompdir_=dirinfo['decompbase_dir']#f"{fn_decompdir}/{fid_}"
        fn_workdir_=dirinfo['decompwork_dir']#f"{fn_decompworkdir}/{fid_}"
        fn_decompdir__=dirinfo['decompresults_dir']
        prdcfgdir=dirinfo['prdcfg_dir']
        bsonf=f"{prdcfgdir}/{fid_}.prd.bson"
        
        for x in [fn_decompdir_,fn_workdir_,prdcfgdir]:
            if not os.path.exists(x):
                os.makedirs(x)

        # Decompile Stage
        fn_decompdir__,decomp_out_=self.decompile(
            resultdir=fn_decompdir_,
            workdir=fn_workdir_,
            funcs=fncs,
            id_=fid_,
            enableGhidraForCPPfails=ghidra
            )
        prd_results={
            'id':fid_,
            'decomp_passes':True if decomp_out_ is not None else False,
            'build_passes':"NOT-RUN",
            'recomp_passes':"NOT-RUN",
            'inlineasm_passes':"NOT-RUN",
            'tests_pass':"NOT-RUN",
            'test_results':None,
            'prog_cfg':None,
            'bson':None,
            'cgfl_passes':cgfl_success,
            'ground_truth_in_valid':gndtruth_success
            }
        

        if decomp_out_ is not None:
            needed=[ os.path.realpath(test) ]+decomp_out_
            bsonf=f"{prdcfgdir}/{fid_}.prd.bson"
            self.generatePRDbson(
                bsondestfile=bsonf,
                resultdir=fn_decompdir_,
                need=needed,
                reducepath=False)
            fn_dest=f"{prd_build_info['prd_destroot']}/{fid_}"
            fn_work=f"{prd_build_info['workroot']}/prd/{fid_}"
        
            fn_prdbson=os.path.realpath(bsonf)
            fn_prdbldinfo=copy.deepcopy(prd_build_info)
            fn_prdbldinfo['source']=fn_workdir_
            fn_prdbldinfo['dest']=fn_dest
            fn_prdbldinfo['work']=fn_work
            fn_prdbldinfo['id']=fid_
            from random import getrandbits
            fn_prdbldinfo['seed']=getrandbits(32)
            fn_results=self.build_prd_eval(
                prdsubcfg=fn_prdbson,
                prd_dir_info=fn_prdbldinfo,
                id_=f"{fid_}",
                seed=fn_prdbldinfo['seed']
                )
            prd_results.update(fn_results)
        sum_,sumhdr_=self.get_summary_line(prd_results)
        prd_results['summary']=sum_
        prd_results['summary_hdr']=sumhdr_
        return prd_results



    def init(self,seed:int,bash_script:str,
            rid:str,
            byte_thresh:int,top_k:int=35,ghidra:bool=False,
            eval_recomp:bool=False):
        test,dbitest=super().init(seed,bash_script,rid)
        prog=self.prd_build_info['pname']
        if self.prd_fn_results.get(prog,None)==None:
            self.prd_fn_results[prog]=dict()
        if not eval_recomp:
            return self.full_prd_eval(seed,(test,dbitest),
                rid,byte_thresh,top_k,ghidra)    
        else:
            return self.recomp_prd_eval(test,
                rid,ghidra)    

    def get_all_funcs(self):
        #funcs=list()
        #if self.binary_info.get('symbols',None) is not None:
        #    lsyms_typs=['t','T'] # get text symbols, both local and global
        #    for lsymt in lsym_typs:
        #        lsyms=self.binary_info['symbols'].get(lsymt,None)
        #        if lsyms:
        #            funcs+=[i['name'] for i in lsyms]

        funcs=[x[0] for x in self.binary_info.get_local_symbols() if not x[0].startswith('_') and not x[0].startswith('.L')]
        return funcs

    def recomp_prd_eval(self,test,rid,ghidra:bool=False):
        reslog=list()
        #test,dbitest=super().init(seed,bash_script,rid)
        prog=self.prd_build_info['pname']
        #if self.prd_fn_results.get(prog,None)==None:
        #    self.prd_fn_results[prog]=dict()
        exe=self.prd_build_info['exe']
        workdir=self.prd_build_info['work']
        baseworkrootdir=os.path.realpath(self.prd_build_info['workroot'])
        baseworkdir=os.path.realpath(workdir)
        
        decompdir=f"{baseworkdir}/decomp"
        decompworkdir=self.prd_build_info['raw_decomp']
        
        fn_decompdir=f"{baseworkrootdir}/decomp_fn"
        fn_decompworkdir=fn_decompdir#f"{baseworkrootdir}/decompwork_fn"
        fn_results_dir=f"{fn_decompdir}"
        
        prdcfgdir=os.path.realpath(self.prd_build_info['prd_cfg'])
        prd_results_=dict()
        good_fns=list()
        
        prd_results_['func_results']=dict()
        no_header=True
        funcs=set(self.get_all_funcs())
        
        decomps_pass=0
        builds_pass=0
        recomps_pass=0
        inlineasms_pass=0
        tot_tests_pass=0
        print(f"PRD Evaluation for {prog}.")
        # START: good candidate for parallelism ::::::: => probably Multiprocessing + Queue?
        for idx,f in enumerate(funcs):
            fid_=f"{prog}.{f}"
            fn_results_pkl = f"{fn_results_dir}/prd_results.{fid_}.pkl"
            fn_results=None
            prd_results_['func_results'][f]=None
            prdprog,build_passes,decomp_passes,recomp_passes,inlineasm_passes,tests_pass,summary,summary_hdr=(
                None,"NOT-RUN","NOT-RUN","NOT-RUN","NOT-RUN","NOT-RUN","",""
                )
            
            if self.prd_fn_results[prog].get(f,None) is not None:
                print(f"[prd_cfg.init] NOTE: Loading existing results for {prog} and {f} from previously run results.")
                fn_results=self.prd_fn_results[prog][f]
            elif os.path.exists(fn_results_pkl):
                print(f"[prd_cfg.init] NOTE: Loading existing results for {prog} and {f} from pickle file.")
                fn_results=self.get_prd_results_from_file(fn_results_pkl)
                self.prd_fn_results[prog][f] = fn_results
            if not ( (fn_results is not None) and isinstance(fn_results,dict) and 
                all(
                    [x in list(fn_results.keys()) for x in ['prog_cfg','decomp_passes','recomp_passes','inlineasm_passes','tests_pass','summary']]
                )
            ):
                dirinfo={
                    'decompbase_dir':f"{fn_decompdir}/{fid_}",
                    'decompwork_dir':f"{fn_decompworkdir}/{fid_}",
                    'decompresults_dir':f"{fn_decompdir}/{fid_}/{exe}",
                    'prdcfg_dir':prdcfgdir
                }
                fn_results=self.eval_fncs([f],fid_,dirinfo,test,self.prd_build_info,ghidra,(None,None))
                self.prd_fn_results[prog][f]=fn_results
                prog_cfg.writepickle(fn_results_pkl,fn_results)

            prdprog=fn_results['prog_cfg']
            builds_pass+= 1 if fn_results['build_passes']==True else 0
            decomps_pass+= 1 if fn_results['decomp_passes']==True else 0
            recomps_pass+= 1 if fn_results['recomp_passes']==True else 0
            inlineasms_pass+= 1 if fn_results['inlineasm_passes']==True else 0
            tot_tests_pass+= 1 if fn_results['tests_pass']==True else 0

            summary_hdr=fn_results['summary_hdr']
            summary=fn_results['summary']

            if no_header:
                reslog.append("")
                reslog.append(summary_hdr)
                reslog.append("-"*80)
                no_header=False
            reslog.append(summary)
            prd_results_['func_results'][f]=fn_results
            
            if recomp_passes and tests_pass:
                good_fns.append(f)
        # END: good candidate for parallelism :::::::
        
        reslog.append(f"Total Functions evaluated: {len(funcs)}")
        reslog.append(f"Total Decompilations PASSED: {decomps_pass}")
        reslog.append(f"Total Builds PASSED: {builds_pass}")
        reslog.append(f"Total Recomps PASSED: {recomps_pass}")
        reslog.append(f"Total Inline ASM PASSED: {inlineasms_pass}")
        reslog.append(f"Total Test-Equivalencies PASSED: {tot_tests_pass}")
        return "\n".join(reslog)


    def full_prd_eval(self,seed:int,tests:tuple,
            rid:str,
            byte_thresh:int,top_k:int,ghidra:bool=False):
        reslog=list()
        test,dbitest=tests
        apr_eval_candidate=False
        #test,dbitest=super().init(seed,bash_script,rid)
        prog=self.prd_build_info['pname']
        #if self.prd_fn_results.get(prog,None)==None:
        #    self.prd_fn_results[prog]=dict()
        exe=self.prd_build_info['exe']
        workdir=self.prd_build_info['work']
        baseworkrootdir=os.path.realpath(self.prd_build_info['workroot'])
        baseworkdir=os.path.realpath(workdir)
        
        decompdir=f"{baseworkdir}/decomp"
        decompworkdir=self.prd_build_info['raw_decomp']
        
        fn_decompdir=f"{baseworkrootdir}/decomp_fn"
        fn_decompworkdir=fn_decompdir#f"{baseworkrootdir}/decompwork_fn"
        fn_results_dir=f"{fn_decompdir}"
        
        prdcfgdir=os.path.realpath(self.prd_build_info['prd_cfg'])

        cgfldir=os.path.realpath(self.prd_build_info['cgfl'])
        
        if not os.path.exists(baseworkrootdir):
            os.makedirs(baseworkrootdir)
        
        reslog.append(f"Process '{rid}'.")
        # CGFL stage
        buildtestinfo,funcs,cgfl_results=self.cgfl(cgfldir,seed,top_k,byte_thresh,dbitest)

        prd_results_=dict()
        prd_results_['cgfl']=cgfl_results
        reslog.append(f"{rid} |  CGFL  | {'FAIL' if len(funcs)==0 else 'PASS'}")

        good_fns=list()
        
        prd_results_['func_results']=dict()
        no_header=True
        for idx,f in enumerate(funcs):
            fid_=f"{prog}.{f}"
            prdbuildinfo=copy.copy(self.prd_build_info)
            while prdbuildinfo['prd_destroot'].endswith('/'):
                prdbuildinfo['prd_destroot']=prdbuildinfo['prd_destroot'][:-1]
            prdbuildinfo['prd_destroot'] = f"{prdbuildinfo['prd_destroot']}_funcs"
            fn_results_pkl = f"{fn_results_dir}/prd_results.{fid_}.pkl"
            fn_results=None
            prd_results_['func_results'][f]=None
            prdprog,build_passes,decomp_passes,recomp_passes,inlineasm_passes,tests_pass,summary,summary_hdr=(
                None,"NOT-RUN","NOT-RUN","NOT-RUN","NOT-RUN","NOT-RUN","",""
                )
            if self.prd_fn_results[prog].get(f,None) is not None:
                print(f"[prd_cfg.init] NOTE: Loading existing results for {prog} and {f} from previously run results.")
                fn_results=self.prd_fn_results[prog][f]
            elif os.path.exists(fn_results_pkl):
                print(f"[prd_cfg.init] NOTE: Loading existing results for {prog} and {f} from pickle file.")
                fn_results=self.get_prd_results_from_file(fn_results_pkl)
                self.prd_fn_results[prog][f] = fn_results
            if not ( (fn_results is not None) and isinstance(fn_results,dict) and 
                all(
                    [x in list(fn_results.keys()) for x in ['prog_cfg','recomp_passes','inlineasm_passes','tests_pass','summary']]
                )
            ):
                dirinfo={
                    'decompbase_dir':f"{fn_decompdir}/{fid_}",
                    'decompwork_dir':f"{fn_decompworkdir}/{fid_}",
                    'decompresults_dir':f"{fn_decompdir}/{fid_}/{exe}",
                    'prdcfg_dir':prdcfgdir
                }
                fn_results=self.eval_fncs([f],fid_,dirinfo,test,prdbuildinfo,ghidra,(None,None))
                self.prd_fn_results[prog][f]=fn_results
                prog_cfg.writepickle(fn_results_pkl,fn_results)

            prdprog=fn_results['prog_cfg']
            build_passes=fn_results['build_passes']
            recomp_passes=fn_results['recomp_passes']
            inlineasm_passes=fn_results['inlineasm_passes']
            tests_pass=fn_results['tests_pass']
            summary_hdr=fn_results['summary_hdr']
            summary=fn_results['summary']

            if no_header:
                reslog.append("")
                reslog.append(summary_hdr)
                no_header=False
            reslog.append(summary)
            prd_results_['func_results'][f]=fn_results
            
            if recomp_passes and tests_pass:
                good_fns.append(f)
        
        totresult,totprdbson=(None,None)
        totprdprog,totrecomp_pass,tottest_pass,totsummary,tothdr=(None,None,None,"","")
        cgfl_success=cgfl_results['success']
        apr_eval_candidate=False
        gndtruth_success=None
        if len(good_fns)>0:
            print(f"CGFL SUCCESS = {cgfl_success}")
            cgfl_gndtruth=cgfl_results.get('ground_truth',None)

            reslog.append(f"{rid} | RECOMP | SUCCESS RATE | {len(good_fns)}/{len(funcs)} decompiled functions successfully recompiled and passed tests")
            if cgfl_gndtruth is None:
                apr_eval_candidate=True
            else:
                cgfl_=[g in cgfl_gndtruth for g in good_fns]
                gndtruth_success=True if any(cgfl_) else False
                apr_eval_candidate=gndtruth_success
                cgfl_r='SUCCESS : at least one ground truth function is in set of recompilable functions' if any(cgfl_) \
                    else 'FAILED : no ground truth functions successfully recompiled'
                reslog.append(f"{rid} |  CGFL-RECOMP | {cgfl_r}")
            reslog.append(f"{rid} | RECOMP | Aggregating recompilable functions => {good_fns}")

            # aggregate
            aggdirinfo={
                'decompbase_dir':decompdir,
                'decompwork_dir':workdir,
                'decompresults_dir':f"{fn_decompdir}/{fid_}/{exe}",
                'prdcfg_dir':prdcfgdir,
            }
            
            totresult=self.eval_fncs(good_fns,rid,aggdirinfo,test,self.prd_build_info,ghidra,(cgfl_success,gndtruth_success))   
            totprdprog=totresult['prog_cfg']
            totrecomp_pass=totresult['recomp_passes']
            tottests_pass=totresult['tests_pass']
            totsummary=totresult['summary']
            tothdr=totresult['summary_hdr']
            reslog.extend(["","",f"Aggregated PRD Results {rid}",tothdr,totsummary,""])
            
        tot_results_pkl = f"{self.prd_build_info['prd_pkl']}/prd_results.{rid}.pkl"
        prd_results_["valid_prd_fns"]=good_fns
        prd_results_["aggregation"]=totresult
        prog_cfg.writepickle(tot_results_pkl,prd_results_)
        success = totrecomp_pass and tottests_pass
        #with open(f"{self.prd_build_info['prd_destroot']}/prd_results.{rid}.log","w") as fh:
        prddestdir=f"{self.prd_build_info['prd_destroot']}/{rid}"
        if not os.path.exists(f"{prddestdir}"):
            os.makedirs(f"{prddestdir}")
        with open(f"{prddestdir}/prd_results.log","w") as fh:
            fh.write("\n".join(reslog))
            fh.close()

        if apr_eval_candidate and success:
            aprroot=f"{self.prd_build_info['apr_eval_root']}/baseline"
            if not os.path.exists(aprroot):
                os.makedirs(aprroot)
            if os.path.exists(f"{aprroot}/{rid}"):
                os.rmtree(f"{aprroot}/{rid}")
            copytree(f"{self.prd_build_info['prd_destroot']}/{rid}",
                    f"{aprroot}/{rid}")
            bson=prd_results_['aggregation']['bson']
            assert bson
            totprdbson=os.path.join(aprroot,rid,os.path.basename(bson))
            shcopy(bson,totprdbson)
        return (totprdbson,totprdprog,success,"\n".join(reslog))
