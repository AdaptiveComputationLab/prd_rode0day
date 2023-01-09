#!/usr/bin/env python3

import yaml, os, copy, shlex, re
import subprocess as sub


import protos


class rode0day_info:
    bugs=None
    def __init__(self,infile:str=None):
        assert infile;
        self.srcfile=infile;
        # we're making some assumptions about the rode0day directory structure 
        self.download_dir=os.path.dirname(os.path.realpath(self.srcfile))
        self.base_dir=os.path.dirname(self.download_dir)
        
        with open(infile,'r') as f:
            data=yaml.load(f)
            f.close()
        self.rode0day_id=data["rode0day_id"]
        self.negtest_dir=os.path.join(self.base_dir,"solutions")
        self.annotated_src_dir=os.path.join(self.base_dir,"source")
        chals=data["challenges"].keys()
        self.id_to_prog = dict((str(data["challenges"][x]["challenge_id"]),x) for x in chals)
        bugs_file=os.path.join(self.base_dir,"bugs.csv")
        bugs=self.getBugs(bugs_file,self.id_to_prog,data['challenges'])

        self.programs=dict()
        for id_,prgname in self.id_to_prog.items():
            self.programs[prgname]=copy.deepcopy(data['challenges'].get(prgname,None))
            self.programs[prgname].update({
                'name':prgname,
                'bugs':copy.deepcopy(bugs[str(id_)]),
                'src_base_dir':os.path.join(self.download_dir,prgname)
                }
            )


        

    def getDirInfo(self):
        return {
            "download": self.download_dir,
            "base": self.base_dir,
            "source":self.annotated_src_dir,
            "negtest": self.negtest_dir,
            "yamlfile": self.srcfile
        }

    def getProgram(self,_id:int=None):
        prog_name = self.id_to_prog.get(_id,None)
        return self.getProgram(prog_name)

    def getProgram(self,prog_name:str=None):
        assert prog_name
        challenge = self.programs.get(prog_name,None)
        return challenge
    
    def listAllPrograms(self):
        prog=list()
        for pname in list(self.getBinaryChallengeNames()):
            prog.append(self.getProgram(pname))
        return prog

    def getAllPrograms(self):
        return self.programs

    def getFaultyFnsFromBug(self,bugid,program,src_path):
        source_path=os.path.join(self.annotated_src_dir,program)
        tmpdir=f"/tmp/protos/{program}"
        if src_path:
            source_path=f"{source_path}/{src_path}"
        updated_src=protos.makeAllPretty(source_path,tmpdir=tmpdir)
        filesrch_cmd=f"egrep -rwn {bugid} {updated_src}"

        p=sub.Popen(shlex.split(filesrch_cmd),stdout=sub.PIPE,
            stderr=sub.STDOUT)
        output=p.stdout.readlines();
        fns=list()
        files=list()
        for x in output:
            o=x.decode('utf-8')
            m=re.match(r"([^:]+):(\d+):(.*)$",o)
            assert m;
            file=m.group(1);line_num=m.group(2);line=m.group(3)
            ret,prt=protos.getPrototypes(file=file)
            fn,lineinfo,fnc=protos.getFunctionFromLine(
                infile=file,
                line_num=int(line_num),
                protos=prt,
                tmpdir=tmpdir
                )
            # let's get the relative path
            if file.startswith(f"{updated_src}/"):
                l=len(f"{updated_src}/")
                file=file[l:]
            fns.append(fn)
            files.append(file)

        return {'files':list(set(files)),'funcs':list(set(fns))}

    def getBugs(self,bugs_file,id_to_prog:dict,chals:dict):
        bugs=dict()
        reader=None
        with open(bugs_file, newline='') as csvfile:
            import csv
            reader = csv.DictReader(csvfile)
            for r in reader:
                bin_,bug_=(str(r['binary_id']),str(r['bug_id']))
                pname=id_to_prog.get(bin_)
                if not bugs.get(bin_,None):
                    bugs[bin_]=list()
                src_path=chals[pname].get('source_path','src')
                buggy_src=self.getFaultyFnsFromBug(bugid=bug_, program=pname, src_path=src_path)
                bugs[bin_].append((bug_,buggy_src))
                #print(f"{r['binary_id']} => {r['bug_id']}" )
            csvfile.close()
        #print(bugs['58'])
        return copy.deepcopy(bugs)
        #with open(bugs_file, 'r') as fp:
        #    line=fp.readline() # bug_id,binary_id
        #    line=fp.readline()
        #    while line:
        #        bug_id,binary_id=line.split(',',1)
        #        print(f"{bug_id} => {binary_id}")
        #        if not bugs.get(binary_id,None):
        #            bugs[binary_id]=list()
        #        bugs[binary_id].append(bug_id)
        #    fp.close()
        


    def getID(self):
        return self.rode0day_id

    def getChallenges(self):
        return self.programs

    def getBinaryChallenge(self,chalName):
        x= self.programs.get(chalName,None)
        assert x
        return x
    
    def getBinaryChallengeNames(self):
        return list(self.getChallenges().keys())

    def getBinaryChallengeID(self,chalName:str):
        return self.getBinaryChallenge(chalName)["challenge_id"]
    
    def getBinaryChallengeARCH(self,chalName:str):
        return self.getBinaryChallenge(chalName)["architecture"]
        
    def getBinaryChallengeINSTALLDIR(self,chalName:str):
        return self.getBinaryChallenge(chalName)["install_dir"]

    def getBinaryChallengeBINPATH(self,chalName:str):
        return self.getBinaryChallenge(chalName)["binary_path"]
    
    def getBinaryChallengeBINARGS(self,chalName:str):
        return self.getBinaryChallenge(chalName)["binary_arguments"]

    def getBinaryChallengeINPUTS(self,chalName:str):
        return self.getBinaryChallenge(chalName)["SAMPLE_INPUTS"]

    def getBinaryChallengeHASSOURCE(self,chalName:str):
        return self.getBinaryChallenge(chalName)["source_provided"]

    def getBinaryChallengeNEGTESTS(self,chalName:str):
        return self.getBinaryChallenge(chalName)["bugs"]
