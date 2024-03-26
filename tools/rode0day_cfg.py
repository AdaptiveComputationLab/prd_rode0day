#!/usr/bin/env python3

import shutil, re, json, os, sys, stat, subprocess, copy
import rode0day_yaml

import prd_cfg
import prog_cfg

support=prd_cfg.support

def re_sub(from_str,to_str,d):
    if isinstance(d,str):
        d=re.sub(from_str,to_str,d)
    elif isinstance(d,list):
        for idx in range(0,len(d)):
            d[idx]=re_sub(from_str,to_str,d[idx])
    elif isinstance(d,dict):
        for k,v in d.items():
            d[k]=re_sub(from_str,to_str,d[k])
    return d


class rode0day_cfg:
    def __init__(self,inputYAML:str,only_prd:bool=False):
        rode0day=rode0day_yaml.rode0day_info(inputYAML)
        self.program_names=rode0day.getBinaryChallengeNames();
        self.programs=rode0day.getAllPrograms();
        self.dirinfo=rode0day.getDirInfo()
        self.decomp_eval_only=only_prd
    
    def getProgramNames(self):
        return self.program_names;

    def setup(self,destdir,workdir,program_name,force_binmode:bool=True,indep_negs:bool=True):
        program=self.programs.get(program_name,None);  assert program
        program['use_source_dir'] = False
        program['compile_cmd'] = ['build.sh']
        copy_src=False
        if not support['stripped'] and not program['source_provided']:
            # we're going to call the build.sh during setup 
            # which builds executable in the 'rebuilt' directory
            copy_src = True
            program['compile_cmd'] = ['make']
            program['source_path']='src'
        
        pname,prog_info=self.generate_prog_info(prog=program, force_binary_mode=force_binmode)
        cfgs=self.generate_cfgs(prog=prog_info,treat_negtests_independently=indep_negs)

        basedir=f"{workdir}/baseline"
        dupdir=f"{workdir}/subcfgs"
        evaldir=f"{workdir}/eval"
        destbasedir=f"{destdir}/baseline"
        destprddir=f"{destdir}/prd"
        destaprdir=f"{destdir}/apr_evals"
        
        resdir,basecfgfile,basecfg=self.setup_base(base_dupdir=basedir,prog=prog_info,
             copyme=copy_src)
        base_dir_info={
            'root':destdir,
            'workroot':evaldir,
            'destroot':destbasedir,
            'source':resdir,
            'raw_decomp':f"{workdir}/raw_decomp",
            'prd_cfg':f"{workdir}/prd_cfg",
            'prd_destroot':destprddir,
            'apr_eval_root':destaprdir,
            'pname':program_name
            #"dest","work","source","workroot"
        }
        mybuild_cfg={
            'init':True,
            'static':False,
            'config':False,
            'compile':False,
            'requires_comp_success':True
        }
        not_binary=prog_info['not_binary']
        run_cfgs=list()
        for id_,pcfg in cfgs:
            # if PRD doesn't support stripped binaries (rode0day are by default stripped)
            # let's just regenerate
            
            #bsonf=f"{bsondir}/{id_}.bson"
            dupcfg=f"{dupdir}/{id_}"
            subdestdir=f"{destbasedir}/{id_}"
            subworkdir=f"{evaldir}/{id_}"
            #prog_cfg.writebson(bsonf,pcfg['prog_info'])
            destpdir,bson_file,trans_prog=self.setup_reqs(duplication_dir=dupcfg,prog=pcfg,source_dir=resdir)
            subcfg=None
            runcfg=None
            base_dirs=copy.copy(base_dir_info);
            base_dirs.update({
                'dest':subdestdir,
                'work':subworkdir,
                'source':destpdir,
                'cgfl':f"{subworkdir}/cgfl",
                'decompile':f"{subworkdir}/decomp",
                'build_id':id_
            })
            
            
            if not_binary:
                subcfg=prog_cfg.prog_cfg(base_dir=base_dirs,cfg=pcfg['prog_info'],sanitychk=False,debug=False,
                    build_cfg=mybuild_cfg)
            else:
                subcfg=prd_cfg.prd_cfg(base_dir=base_dirs,cfg=pcfg['prog_info'],sanitychk=False,debug=False,
                    build_cfg=mybuild_cfg)
            runcfg={
                "cfg":subcfg,
                "rid":id_,
                "not_binary":not_binary,
                "base_dirs":base_dirs
                }
            run_cfgs.append(runcfg)
        
        return run_cfgs

    def initialize(self,seed:int,runcfg:dict,byte_thresh:int=None,top_k:int=None,ghidra:bool=None):
        return self.init(
            seed=seed,
            progcfg=runcfg['cfg'],
            rid=runcfg['rid'],
            byte_thresh=byte_thresh,
            top_k=top_k,
            ghidra=ghidra
            )
        

    def init(self,seed:int,progcfg,
            rid:str,byte_thresh:int=None,top_k:int=None,ghidra:bool=None):

        
        args=[seed,"test.sh",rid]
        
        if isinstance(progcfg,prd_cfg.prd_cfg):
            args=[seed,"test.sh",rid,byte_thresh,top_k,ghidra,self.decomp_eval_only]
        elif not isinstance(progcfg,prog_cfg.prog_cfg):
            assert isinstance(progcfg,prog_cfg.prog_cfg)
        x= progcfg.init(*args)
        summary=x
        passes=True
        if not isinstance(x,str):
            summary=x[3]
            passes=x[2]
        return passes,summary
        

    def getProgBasePath(self,prog:dict):
        full_basepath=self.dirinfo['download']
        pname=prog['name']
        pdir=os.path.join(full_basepath,pname)
        return pdir
    
    def getSourcePath(self,prog:dict):
        full_basepath=self.dirinfo['source']
        pname=prog['name']
        pdir=os.path.join(full_basepath,pname)
        return pdir

    def setup_base(self,base_dupdir:str,prog:dict,copyme:bool=False):
        assert base_dupdir and prog;
        #if not os.path.exists(duplication_dir):
        #    os.makedirs(duplication_dir)
        full_basepath=self.dirinfo['download']
        pname=prog['name']
        pdir=os.path.join(full_basepath,pname)
        negtest_dir=f"{self.dirinfo['negtest']}/{pname}"
        neglocaldir=self.negtestdir()
        destpdir=f"{base_dupdir}/{pname}"   # <PROG_BASE_DIR>
        destnegdir=os.path.join(destpdir,neglocaldir) # <PROG_NEGTEST_DIR>
        if not os.path.exists(destpdir):
            destpdir=shutil.copytree(pdir,destpdir); 
            destnegdir=os.path.join(destpdir,neglocaldir) # <PROG_NEGTEST_DIR>
            if copyme:
                #PROG_SRCBASE_DIR
                srcpath=self.getSourcePath(prog)
                destpath=f"{base_dupdir}/{pname}"
                if not os.path.exists(destpath):
                    os.makedirs(destpath)
                #["src","Makefile"]:
                for i in os.listdir(srcpath):
                    srcf=f"{srcpath}/{i}"
                    destf=f"{destpath}/{i}"
                    if os.path.isdir(srcf):
                        shutil.copytree(srcf,destf)
                    else:
                        shutil.copy(srcf,destf)
            shutil.copytree(negtest_dir,destnegdir);
        srcpath=None
        
        #if prog['source_provided']:
        #    srcpath=os.path.join(destpdir,prog['source_path']) # not used
        
        if not support['stripped']:
            exep_=prog['prog_info']['build_info']['exe_out_dir']
            exe_=prog['prog_info']['program_info']['exe']
            exe=f"{exep_}/{exe_}"
            res_exe=f"{destpdir}/{exe}"
            #mypath={"PATH":f"{os.getenv('PATH',None)}:{destpdir}"}
            #myenv=os.environ; myenv.update(mypath)
            cmd=prog['prog_info']['build_info']['compile_cmd']; 
            if prog['source_provided']:
                cmd[0]=f"./{cmd[0]}"
            
            
            print(f"RUNNING build command : '{cmd}' in {destpdir}",flush=True)
            compile_log=f"{destpdir}/base.compile.log"
            tmpfh=open(compile_log,'w')
            p=subprocess.Popen(
                cmd,
                cwd=destpdir,
                stdout=tmpfh,
                stderr=subprocess.STDOUT
                )
            p.wait()
            tmpfh.close()
            print(f"RESULT  build command : {'PASS' if p.returncode==0 else 'FAIL'}",flush=True)
            if prog['source_provided']:
                shutil.copy(f"{destpdir}/re{exe}",res_exe)
                prog['prog_info']['build_info']['exe_out_dir']=f"re{exep_}"
            else:
                e=os.path.basename(exe)
                shutil.copy(f"{destpdir}/src/{e}",res_exe)
            print(f"Obtaining binary information from {res_exe}",flush=True)
            prd_cfg.get_binary_info(destpdir,res_exe)
        

        trans_prog=re_sub("<PROG_BASE_DIR>",os.path.realpath(destpdir),prog['prog_info'])
        trans_prog=re_sub("<PROG_NEGTEST_DIR>",neglocaldir,trans_prog)
        bson_file=os.path.join(base_dupdir,f"{pname}.bson")
        print(f"Generating program BSON file [{bson_file}]",flush=True)
        prog_cfg.writebson(bson_file,trans_prog)

        return destpdir,bson_file,trans_prog


    def negtestdir(self):
        return "neginputs"

    def setup_reqs(self,duplication_dir:str,prog:dict,source_dir:str):
        assert duplication_dir and prog;
        #if not os.path.exists(duplication_dir):
        #    os.makedirs(duplication_dir)
        full_basepath=self.dirinfo['download']
        pname=prog['name']
        pdir=os.path.join(full_basepath,pname)
        neglocaldir=self.negtestdir()
        destpdir=duplication_dir
        if not os.path.exists(duplication_dir):
            destpdir=shutil.copytree(source_dir,duplication_dir); # <PROG_BASE_DIR>            
        trans_prog=re_sub("<PROG_BASE_DIR>",os.path.realpath(destpdir),prog['prog_info'])
        trans_prog=re_sub("<PROG_NEGTEST_DIR>",neglocaldir,trans_prog)
        bson_file=os.path.join(destpdir,f"{pname}.bson")
        prog_cfg.writebson(bson_file,trans_prog)
        # we'll update this in the prd directory generation
        #exe=prog['binary_path'] if not_binary else prog['binary_path']+".trampoline.bin"
        #compile_cmd=['build.sh'] if not_binary else ['make","-f Makefile.prd","all']
        return destpdir,bson_file,trans_prog

    def run_test(self,full_exe,b_args,test,inputdir):
        bargs=re.sub(r"\{input_file\}",f"{test}",b_args)
        cmd=re.sub(r"\{install_dir\}",inputdir,f"{full_exe} {bargs}")
        import shlex
        p=subprocess.Popen(shlex.split(cmd));
        p.wait()
        
        return p.returncode

    def generate_prog_info(self, prog, force_binary_mode:bool=False):
        collective=list()
        apr_dict=dict()
        x=prog
        prog_srcfiles=[ f"<PROG_BASE_DIR>/{x}" for x in os.listdir(self.getProgBasePath(prog))]+\
        [f"<PROG_BASE_DIR>/{self.negtestdir()}"]
        if x['use_source_dir']:
            prog_srcfiles += [
                f"<PROG_BASE_DIR>/{x}" for x in os.listdir(self.getSourcePath(prog))
            ]

        #for x in self.programs:
        not_binary=( (x['source_provided'] or x['use_source_dir']) and not force_binary_mode)
        build_type="SHELL"            

        exedir=os.path.dirname(x['binary_path'])+"/"
        exe=os.path.basename(x['binary_path'])
        pname=x['name']
        compile_cmd=x['compile_cmd']

        p_=[]
        n_=[]
        
        base_dir=os.path.join(self.dirinfo['download'],pname)
        full_exepath=os.path.join(base_dir,x['binary_path'])
        
        
        # positive tests
        # PEMMA
        for p in x['sample_inputs']:
            postest_=os.path.join(base_dir,p)
            pret=self.run_test(full_exepath,b_args=x['binary_arguments'],test=postest_,inputdir=base_dir)
            p_.append((p,pret))
        for n,fault in x['bugs']:
            negtest_=os.path.join(self.dirinfo['negtest'],pname,n)
            nret=self.run_test(full_exepath,b_args=x['binary_arguments'],test=negtest_,inputdir=base_dir)
            n_.append((n,fault,nret))

        


        #binargs=re.sub(r"\{install_dir\}",destpdir,x['binary_arguments'])
        binargs=re.sub(r"\{install_dir\}","<PROG_BASE_DIR>",x['binary_arguments'])
        import shlex
        posbinargs=shlex.split(re.sub(r"\{input_file\}","<POS_TEST>",binargs))
        negbinargs=shlex.split(re.sub(r"\{input_file\}","<NEG_TEST>",binargs))
        pos_tests= [ 
            {
                "CHECK":"RETURN", 
                "PASS":f"{pret}", 
                "POS_TEST":f"<PROG_BASE_DIR>/{ptest}",
                "TIMEOUT":5
            } for ptest,pret in p_
        ]
        neg_tests= [ 
            {
                "CHECK":"RETURN", 
                "FAIL":f"{pret}", 
                "NEG_TEST":f"<PROG_BASE_DIR>/<PROG_NEGTEST_DIR>/{p}",
                "TIMEOUT":5,
                "FAULTS":fault
            } for p,fault,pret in n_
        ]
        
        apr_info={
            "program_info":{
                "program":x['name'],
                "exe":exe
            },
            "downloads":{
                "wget":[],
                "batch":[]
            },
            "build_info":{
                "build_type":build_type,
                "timeouts":{"compile":360},
                "compile_cmd":compile_cmd,
                "build_targets": {},
                "build_src": prog_srcfiles, 
                "exe_out_dir":exedir,
                "compiler":{"C":"gcc","CC":"gcc","CXX":"g++","ASM":"gcc"},
                "env":{}
            },
            "test_info":{
                "test_src":[],
                "test_script":{
                    "POS":["<BIN>"]+posbinargs,
                    "POS_DBI":["<DBI>","<BIN>"]+posbinargs,
                    "NEG":["<BIN>"]+negbinargs,
                    "NEG_DBI":["<DBI>","<BIN>"]+negbinargs,
                },
                "timeouts":{"POS":3,"POS_DBI":20,"NEG":3,"NEG_DBI":20},
                "test_script_stdout":[],
                "positive_tests":pos_tests,
                "negative_tests":neg_tests,    
                "replace_me":[]         
            }
        }
        proginfo={
            "name":pname,
            "not_binary":not_binary,
            "prog_info":apr_info,
            "yaml":x,
            "source_provided":x['source_provided'],
            "source_path":x['source_path'] if x['source_provided'] else None
            };
        return pname,proginfo
        
    def generate_cfgs(self,prog,treat_negtests_independently:bool=True):
        not_binary=prog['not_binary']
        prog_info=prog['prog_info']
        yaml=prog['yaml']
        pname=prog['name']
        negs=copy.deepcopy(prog_info['test_info']['negative_tests'])
        cfgs=list()
        # this could be put into the prog_cfg, but putting something together quickly
        if self.decomp_eval_only or not treat_negtests_independently or len(negs)==1:
            cfgs.append((pname,prog))
        else:
            n=[(f"n{i+1}",[x]) for i,x in enumerate(negs)]
            #DEBUG ME: n=[(f"n{i+1}",[x]) for i,x in enumerate([negs[0]])]
            for id_,neg_ in n:
                pr_=copy.deepcopy(prog)
                pr_['prog_info']['test_info']['negative_tests']=neg_
                cfgs.append((f"{pname}.{id_}",pr_))
            #cfgs.append((f"{pname}.all",prog))
        return cfgs


def parse_args():
    import sys,argparse,os
    env=os.environ
    parser = argparse.ArgumentParser(description="Generate APR infrastructures for rode0day")
    parser.add_argument("--no-indep-negs",dest="indepnegs", default=True, action='store_false',
        help="assume that negative tests are not independent")
    parser.add_argument("--no-prd",dest="forcebin", default=True, action='store_false',
        help="do not force APR evaluations to use PRD, i.e. when source is available, use standard source-based APR tools")
    parser.add_argument("--work-dir",dest="work",type=str, 
        required=True,
        help="specify directory where intermediate workfiles are stored")
    parser.add_argument("--build-dir",dest="build",type=str, default=None, 
        required=True,
        help="specify directory where APR-compatible build infrastructure is generated")
    parser.add_argument("--yml",dest="yml",type=str, required=True, 
        help="specify input YAML file from rode0days")
    parser.add_argument("--rseed",dest="rseed",type=int,default=0, 
        help="specify seed for random number generator [default:0]")
    parser.add_argument("--byte-thresh",dest="bytemin",type=int,default=45, 
        help="only decompile functions that are at least this number of bytes")
    parser.add_argument("--top-k",dest="topk",type=int,default=35, 
        help='identify the top N percentage from CGFL')
    parser.add_argument("--eval-prd-decomp-only",dest="only_eval_prd_decomp",default=False, action='store_true', 
        help='evaluate PRD Decompilation effectiveness, i.e., apply PRD to all functions of a binary and check test-equivalency to original binary')
    parser.add_argument("--ghidra",dest="ghidra",default=False, action='store_true', 
        help='apply ghidra during decompilation failures (only applicable to CPP-sourced bins)')
    parser.add_argument("--list-programs",dest="showp",default=False, action='store_true', 
        help='Show the list of available programs')
    parser.add_argument("--program",dest="prog",type=str, required=False, default=None,
        help='Evaluate on specific program')
        
    
    args=parser.parse_args()
    return args

        
if __name__ == "__main__":
    args=parse_args()
    rode0cfg=rode0day_cfg(args.yml,only_prd=args.only_eval_prd_decomp)
    import random
    random.seed(args.rseed)
    if args.showp:
        print('\n'.join(rode0cfg.getProgramNames()))
    else:
        for p in rode0cfg.getProgramNames():
            if args.prog is None or p==args.prog:
                print(f"Configuring {p}")
                subpcfgs=rode0cfg.setup(destdir=args.build,workdir=args.work,
                    program_name=p,force_binmode=args.forcebin,
                    indep_negs=args.indepnegs)    
                
                for subp in subpcfgs:
                    #prdsubpbson,prdsubp,success,summary
                    success,summary=rode0cfg.initialize(seed=random.getrandbits(20),runcfg=subp,
                        byte_thresh=args.bytemin,top_k=args.topk,ghidra=args.ghidra)   
                    
                    print(summary,flush=True)
                    if not success:
                        print(f"[ERROR] Compilation failed for prd subconfiguration for {p}")
                
                
            
