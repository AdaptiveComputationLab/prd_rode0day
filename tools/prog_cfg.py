#!/usr/bin/env python3

import sys, os, bson, json, re, subprocess, shlex
from framework import testing, program
from bson import json_util

import pickle

support={'GenProg':False,'Prophet':False,'Angelix':False}

def writebson(bson_file,data,mode:str='w'):
    if not os.path.exists(os.path.dirname(bson_file)):
        os.makedirs(os.path.dirname(bson_file))
    with open(bson_file,mode) as bf:
        if data is not None:
            bf.write(json_util.dumps(data,indent=4));
        bf.close()

def readbson(bson_file,mode:str='rb'):
    f=open(bson_file, mode);
    pstr=f.read()
    return json_util.loads(pstr)

def writepickle(pkl_file,data):
    if not os.path.exists(os.path.dirname(pkl_file)):
        os.makedirs(os.path.dirname(pkl_file))
    f=open(pkl_file,'wb')
    if data is not None:
        pickle.dump(data,f)
    f.close()

def readpickle(pkl_file):
    f=open(pkl_file,'rb')
    return pickle.load(f)

class setup_cfg:
    work_dir=None
    root_path=None
    def __init__(self,work,root=None):
        self.work_dir=work
        self.root_path=root
        if not self.root_path:
            self.root_path=os.cwd()
    def __dict__(self):
        return {
            'work':self.work_dir,
            'root':self.root_path
        }
    def work_path(self):
        return f"{self.root_path}/{self.work_dir}"            


default_build_cfg={
    'init':True,'static':False,
    'config':True,'compile':True,
    'requires_comp_success':True
}

class prog_cfg:
    eval_root=None
    test_log=None   
    def getTestInfo(self):
        return self.test.test_info
    
    def getDefaultEnv(self):
        return self.test.test_info.get("env",None)


    def getDefaultTimeout(self,ttype):
        return self.test.test_info["timeouts"].get(ttype)

    def getPosTest(self,indx):
        assert indx<self.numPosTests();
        return self.test.test_info['positive_tests'][indx]

    def getNegTest(self,indx):
        assert indx<self.numNegTests();
        return self.test.test_info['negative_tests'][indx]
    
    def numPosTests(self):
        return len(self.test.test_info['positive_tests'])

    def getPosTestEnv(self,indx):
        p=self.getPosTest(indx)
        penv= p.get("ENV",None)
        if not penv:
            penv=self.getDefaultEnv()
        return penv


    def getPosTestTimeout(self,indx,dbi:bool=False):        
        assert indx<self.numPosTests();
        p=self.getPosTest(indx)
        ttyp="POS" if not dbi else "POS_DBI"
        timeout=None
        if not p.get(ttyp,None):
            timeout= self.getDefaultTimeout(ttyp)
        else:
            timeout = p.get(ttyp)
        return timeout

    def getPosTestInfo(self,indx):
        pinfo=dict()
        pinfo['ENV']=self.getPosTestEnv(indx)
        p=self.getPosTest(indx)
        for i in ['CHECK','PASS','FAIL']:
            pinfo[i]=p.get(i,None)
        return pinfo

    def getNegTestInfo(self,indx):
        ninfo=dict()
        ninfo['ENV']=self.getNegTestEnv(indx)
        n=self.getNegTest(indx)
        for i in ['CHECK','PASS','FAIL']:
            ninfo[i]=n.get(i,None)
        return ninfo

    def getNegTestEnv(self,indx):
        p=self.getNegTest(indx)
        penv= p.get("ENV",None)
        if not penv:
            penv=self.getDefaultEnv()
        return penv


    def getNegTestTimeout(self,indx,DBI:bool=False):        
        assert indx<self.numNegTests();
        p=self.getNegTest(indx)
        ttyp="NEG" if not DBI else "NEG_DBI"
        timeout=None
        if not p.get(ttyp,None):
            timeout= self.getDefaultTimeout(ttyp)
        else:
            timeout = p.get(ttyp)
        return timeout

    #"FAULTS":{"files":[],"funcs":[]}
    def getNegTestFaultLocale(self,indx):
        assert indx<self.numNegTests();
        p=self.getNegTest(indx)
        return p.get("FAULTS",None)
    
    def numNegTests(self):
        return len(self.test.test_info['negative_tests'])

    def getCfg(self,cfg_file:str):
        progcfg=None
        ext = os.path.splitext(cfg_file)[1]
        f=open(cfg_file, 'rb');
        if ext==".bson":
            import bson
            from bson import json_util
            pstr=f.read()
            progcfg=json_util.loads(pstr)
            # note that the bson.decode_all sometimes has issues with large content
            #progcfg = bson.decode_all(f.read()) 
        elif ext==".json":
            import json
            progcfg=json.load(f)
        elif ext==".yaml" or ext==".yml":
            import yaml
            progcfg=yaml.safe_load(f)
        else:
            print(f"Unsupported extension: {ext} [cfgfile={cfg_file}]",file=sys.stderr)
            print(f"Exiting.",file=sys.stderr)
            sys.exit(-1);    
        f.close()
        return progcfg
        
    def workRootDir(self):
        return self.basedir.get("workroot")

    def workDir(self):
        return self.basedir.get("work")
    def destDir(self):
        return self.basedir.get("dest")

    def destRootDir(self):
        return self.basedir.get("destroot")

    def sourceDir(self):
        return self.basedir.get("source")

    def getBaseDirs(self):
        return self.basedir

    def __init__(self,base_dir:dict,cfg,sanitychk:bool=False,debug:bool=False,
        build_cfg:dict=None):
        
        # init: initialize the directory
        # static : enable static compilation (if applicable)
        # config : apply the configuration command
        # compile : compile using the compilation command
        self.basedir=base_dir
        
        assert not any([self.basedir.get(x,None)==None for x in ["dest","destroot","work","source","workroot"]])
        if self.basedir.get('apr_eval_root',None) is None:
            self.basedir['apr_eval_root']=f"{self.basedir['destroot']}/apr_evals"
        self.getTestLog()
        if not build_cfg:
            build_cfg=default_build_cfg
        else:
            for k,v in default_build_cfg.items():
                if build_cfg.get(k,None)==None:
                    build_cfg[k]=v
                    
        self.toolsdir=os.path.dirname(__file__)
        self.sanity_check=sanitychk # if possible sanity check tests with binary that is fixed
        # the cfg here is either 
        # 1. the configuration file that follows the example in templates/PROG.bson (yaml, json, bson supported)
        # -or-
        # 2. is the actual program configuration object that's been externally parsed and objectified
        self.progcfg=self.getCfg(cfg) if isinstance(cfg,str) else cfg
        assert isinstance(self.progcfg,dict)


        self.program=program.Program(cfg=self.progcfg,root=self.basedir["source"],debug=False,
            init_=build_cfg['init'],static_=build_cfg['static'],config_=build_cfg['config'],
            compile_=build_cfg['compile'],requires_comp_success=build_cfg['requires_comp_success'])
        self.test=testing.Testing(cfg=self.progcfg,root=self.basedir["source"],debug=False)
        
    
    def getProgramCfg(self):
        return self.progcfg

    def generate_pos_test_cmd(self,exe,pid,dbi:bool=False):
        pos_cmd=self.program.test_info['test_script']['POS'] if not dbi else \
            self.program.test_info['test_script']['POS_DBI']
        pos_test=self.program.test_info['positive_tests'][pid]['POS_TEST']
        base_cmd=re.sub("<POS_TEST>",pos_test," ".join(pos_cmd))
        exe_cmd=re.sub("<BIN>",exe,base_cmd)
        return exe_cmd

    def generate_neg_test_cmd(self,exe,nid,dbi:bool=False):
        neg_cmd=self.program.test_info['test_script']['NEG'] if not dbi else \
            self.program.test_info['test_script']['NEG_DBI']
        neg_test=self.program.test_info['negative_tests'][nid]['NEG_TEST']
        base_cmd=re.sub("<NEG_TEST>",neg_test," ".join(neg_cmd))
        exe_cmd=re.sub("<BIN>",exe,base_cmd)
        return exe_cmd


    def getTimeoutDefaults(self,ttype:str=None):
        x=self.program.test_info["timeouts"]
        if ttype and x.get(ttype,None):
            x=x.get(ttype);
        return x
        
    def buildType(self):
        return self.program.build_type;
    
    def getExePath(self):
        exe=self.getExe()
        if exe and self.eval_root:
            return f"{self.eval_root}/{exe}"
        return exe
        
    def getProgram(self):
        return self.progcfg['program_info']['program']

    def getExe(self):
        exep = self.progcfg["program_info"]["exe"]
        p=self.progcfg["build_info"].get("exe_out_dir",None) # this ends with '/'
        if p:
            if p[-1]!='/':
                p+='/'
            exep=f"{p}{exep}"
        return exep 

    def getRefPath(self):
        exe=self.getRef()
        if exe and self.eval_root:
            return f"{self.eval_root}/{exe}"
        return exe
        
    def getRef(self):
        refp = self.progcfg["program_info"].get("exe_ref",None)
        if refp:
            p=self.progcfg["build_info"].get("exe_ref_out_dir",None) # this ends with '/'
            if p:
                if p[-1]!='/':
                    p+='/'
                refp=f"{p}{refp}"
        return refp 

    def initialize_dir(self,destdir,build_id):
        self.eval_root=destdir 
        ret=self.program.build(build_root_dir=destdir,build_id=build_id)
        return ret

    def setupEvaluation(self,destdir,build_id):
        res1=self.initialize_dir(destdir,build_id)
        res2=self.test.setup(destdir,self.program.build_dest_dir)
        return res1,res2

    def getTestLog(self):
        if self.test_log is None:
            self.test_log=f"{self.destDir()}/test_results.log"
        return self.test_log

    def getCompileLog(self):
        return self.program.compile_log

    def getSrcDir(self):
        return self.program.build_src_dir

    def getBuildDir(self):
        return self.program.build_dest_dir

    def buildTestScript(self,bash_script,destdir,sanity_check:bool=False):
        exe_=os.path.realpath(os.path.join(destdir,self.getExe()))
        ref_=self.getRef()
        if ref_:
            ref_=os.path.realpath(os.path.realpath(os.path.join(destdir,ref_)))
        #print(f"[buildTestScript] [DESTDIR => {destdir}] EXE => {exe_}")
        scrpt,dbi_scrpt=self.test.generate_bash(bash_script=bash_script,
            dest_dir=destdir,exe=exe_,ref=ref_,sanitychk=sanity_check)
        self.configure_test_info(scrpt,dbi_scrpt)
        return scrpt[0],dbi_scrpt[0]
    
    def configure_test_info(self,scrpt,dbi_scrpt):
        self.tests={
            "all":scrpt[0],"independent_negs":scrpt[1:],
            "all_dbi":dbi_scrpt[0],"independent_negs_dbi":dbi_scrpt[1:]
            } if len(scrpt)>1 else {
            "all":scrpt[0],"independent_negs":None,
            "all_dbi":dbi_scrpt[0],"independent_negs_dbi":None
            } 
    
    def check_build(self,build_id:str):
        ret=0
        destdir=self.destDir()
        if self.eval_root == None:
            ret=self.initialize_dir(destdir,build_id)
            if ret != 0:
                print(f"[ERROR] Build failed for {build_id} @ {destdir}")
            else:
                print(f"[SUCCESS] Build succeeded for {build_id} @ {destdir}")
        else:
            built_exe=self.getExePath()
            if not os.path.exists(built_exe):
                print(f"[ERROR] Previous build failed to generate binary [expected: '{built_exe}']")
                ret = -1
        return ret


    def check_test_setup(self,bash_script:str="test.sh"):
        script,dbi_script=self.test.setup_with_reuse(bash_script,self.eval_root,self.program.build_dest_dir)
        self.configure_test_info(script,dbi_script)
        
    
    def pos_testcmd(self,exe,pid,dbi:bool=False):
        pcmd=self.generate_pos_test_cmd(exe,pid,dbi)
        timeout=self.getPosTestTimeout(pid,dbi)
        testinfo=self.getPosTestInfo(pid)
        return pcmd,timeout,testinfo

    def run_pos_test(self,exe,pid,dbi:bool=False):
        # we're using the genprog-style test.sh to evaluate:
        # the command should be "test.sh <binary> <test_id>"
        pcmd,timeout,tinfo=self.pos_testcmd(exe,pid,dbi)
        lenv=None
        if tinfo.get("ENV",None) is not None and tinfo["ENV"] is not None:
            lenv=os.environ
            lenv.update(tinfo["ENV"]);
        p=subprocess.Popen(shlex.split(pcmd),env=lenv);
        pret=p.wait(timeout=timeout)
        
        return p.returncode,p,tinfo

    def neg_testcmd(self,exe,nid,dbi:bool=False):
        ncmd=self.generate_neg_test_cmd(exe,nid,dbi)
        timeout=self.getNegTestTimeout(nid,dbi)
        testinfo=self.getNegTestInfo(nid)
        return ncmd,timeout,testinfo

    def run_neg_test(self,exe,nid,dbi:bool=False):
        # we're using the genprog-style test.sh to evaluate:
        # the command should be "test.sh <binary> <test_id>"
        
        ncmd,timeout,tinfo=self.neg_testcmd(exe,nid,dbi)
        lenv=None
        if tinfo.get("ENV",None) is not None and tinfo["ENV"] is not None:
            lenv=os.environ
            lenv.update(tinfo["ENV"]);
        n=subprocess.Popen(shlex.split(ncmd),env=lenv);
        nret=n.wait(timeout=timeout)
        
        return n.returncode,n,tinfo
    
    def run_tests(self,exe:str=None,dbi:bool=False,expect_neg_to_fail:bool=True,fail_fast:bool=True):
        numpos=self.numPosTests()
        numneg=self.numNegTests()
        if exe is None:
            exe=self.getExePath()
        expected_behavior=True
        failing_ret=-1
        passing_ret=0

        results=list()
        for ni in range(0,numneg):
            nret,n,ninfo = self.run_neg_test(exe,ni,dbi)
            if nret is None:
                nret=n.wait()
            pass_value=None if ninfo.get('PASS',None) is None else int(ninfo['PASS']) 
            fail_value=None if ninfo.get('FAIL',None) is None else int(ninfo['FAIL']) 
            not_expected=((pass_value is not None) and nret == pass_value) or ((fail_value is not None) and nret != fail_value)
            if not_expected and expect_neg_to_fail:
                expected_behavior=False
                            #0  1    2     3         4          5
            results.append(("n",ni+1,nret,pass_value,fail_value,not not_expected))
            if (not expected_behavior) and fail_fast:
                print(f"Unexpected failure with negative test n{ni+1}")
                return self.write_test_results(expected_behavior,results)
        for pi in range(0,numpos):
            pret,p,pinfo = self.run_pos_test(exe,pi,dbi)
            pass_value=None if pinfo.get('PASS',None) is None else int(pinfo['PASS']) 
            fail_value=None if pinfo.get('FAIL',None) is None else int(pinfo['FAIL']) 
            if pret is None:
                pret=p.wait()
            not_expected=((pass_value is not None) and pret != pass_value) or ((fail_value is not None) and nret == fail_value)
            if not_expected:
                expected_behavior=False
            results.append(("p",pi+1,pret,pass_value,fail_value,not not_expected))
            if (not expected_behavior) and fail_fast:
                print(f"Unexpected failure with positive test p{pi+1}")
                return self.write_test_results(expected_behavior,results)
                
        #print(f"EXPECTED BEHAVIOR : {expected_behavior} ")
        return self.write_test_results(expected_behavior,results)
        
        
    def write_test_results(self,expected_behavior,results):
        fh=open(self.test_log,"w")
        tres="\n".join([f"{x[0]}{x[1]} : {x[2]} {'EXPECTED BEHAVIOR (PASS)' if x[5]  else 'UNEXPECTED BEHAVIOR (FAIL)'}" for x in results])
        fh.write(tres)
        fh.write(f"\nTests behaved {'as expected' if expected_behavior else 'unexpectedly'}")
        fh.close()
        return expected_behavior,results
        
    def create_seed_file(self,seed:int=0):
        seedfile=os.path.join(self.getBuildDir(),"rseed")
        with open(seedfile,"w") as f:
            f.write(str(seed)); f.close() 

    def init(self,seed:int=0,bash_script:str="test.sh",rid:str=None):
        if not rid:
            rid=self.getProgram()
        res1,res2=self.setupEvaluation(self.destDir(),rid);
        x= self.buildTestScript(bash_script,self.destDir(),self.sanity_check);
        self.create_seed_file(seed)
        #print(f"{destdir} => {self.getBuildDir()}")
        return x
    
        
            
        



    

