#!/usr/bin/env python3

import subprocess as sub
import shlex, re, os

def makeAllPretty(srcdir,tmpdir,ext=[".c",".cc",".cpp",".h",".hh"]):
    for x in os.listdir(srcdir):
        if any([x.endswith(i) for i in ext]):
            makePretty(f"{srcdir}/{x}",tmpdir)
    return tmpdir

def makePretty(infile,tmpdir):
    outfile=os.path.join(tmpdir,os.path.basename(infile))
    if os.path.exists(outfile):
        return True,outfile
    elif not os.path.exists(tmpdir):
        try:
            os.makedirs(tmpdir)
        except Exception as e:
            import sys;
            print(f"[protos] Failed to create directory structure '{tmpdir}'",file=sys.stderr)
            raise(e)
        
    # the purpose of this function is to generate consistent source files
    ident_cmd = "indent -kr -bap -nce " + \
                " -i8 -ts8 -sob -l80 " + \
                "-ss -bs -npsl -bl -bli0 " + \
                f"-o {outfile} {infile}"
    ret = None
    try:
        ret = sub.check_call(shlex.split(ident_cmd),stderr=sub.DEVNULL)
    except Exception as e:
        raise(e)
    #print(f"{ident_cmd} : {'SUCCESS' if not ret else 'FAIL'}")
    return ret,outfile

def getPrototypes(file):
    cproto_cmd = f"cproto -s -i -q -E 0 {file}"
    ret,p = (None,None)
    xout,xerr=(None,None)
    try:
        p = sub.Popen(shlex.split(cproto_cmd),stdout=sub.PIPE,stderr=sub.PIPE)
        xout,xerr=p.communicate(timeout=10)
    except Exception as e:
        print(xerr.read().decode('utf-8'))
        raise(e)
    protos = [ x for x in xout.decode('utf-8').split('\n') ]
    invalid_ = re.compile(r"^(/\*.*\*/|(\w+/)+\w+\.c:\d+: cannot read file ).*")
    valid_protos = []
    for p in protos:
        if invalid_.match(p):
            continue
        else:
            valid_protos.append(p)
    #print(f"{cproto_cmd} : {'SUCCESS' if not ret else 'FAIL'}")
    return ret,valid_protos

def cleanup_func(infunc):
    f=infunc
    f=f.rsplit('(',1)[0].rsplit(' ',1)[-1]
    try:
        while(f[0] in ['*',' ']):
            f=f[1:]
        while (f[-1] in ['(',' ']):
            f=f[0:-1]
    except Exception as e:
        print(f"Input: {infunc} => {f}")
        raise(e)
    return f

def getFunctionFromLine(infile:str,line_num:int,protos:list,tmpdir:str="/tmp/protos",debug:bool=False):
    ret,file=makePretty(infile,tmpdir)
    protos=[x for x in protos if x!="" and ('void (*' not in x)] # get rid of function pointers
    protos_ = [x.rsplit("(")[0].rsplit(' ')[-1]+"(" for x in protos]

    fls = None
    with open(file,"r") as infh:
        fls = infh.readlines()
        infh.close()
    
    indx = line_num+1
    check_next = False
    func = None
    start_line_num = None
    end_line_num = None
    count=0
        
    while (indx > -1): 
        if check_next:
            protchk = [(x in fls[indx]) for x in protos_]
            if any(protchk):
                pindx=protchk.index(True)
                func = protos[pindx]
                start_line_num = indx
                break
        if fls[indx].startswith("{"):
            check_next = True
        indx -= 1
    indx = line_num+1
    while (indx < len(fls)):
        if fls[indx].startswith("}"):
            end_line_num = indx
        indx+=1

    f=cleanup_func(func)

    return f,(start_line_num+1,end_line_num+1),fls[start_line_num:end_line_num+1]
    
    if start_line_num:    
        return func,(start_line_num+1,end_line_num+1),fls[start_line_num:end_line_num+1]                    
    else:
        return None,(None,None),None
