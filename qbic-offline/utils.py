import gzip
import os
import subprocess

def get_chrom(cfile):
    with gzip.open(cfile,'rb') as f:
        next(f)
        chrom = f.read().decode('utf-8').replace('\n','')
    return chrom.upper()

def itoseq(seqint,kmer):
    nucleotides = {0:'A',1:'C',2:'G',3:'T'}
    seq = ""
    while(seqint > 0):
        seq = nucleotides[seqint & 3] + seq
        seqint >>= 2
    while len(seq) < kmer:
        seq = 'A' + seq
    return seq

'''
does not append 1, used for integer indexing
'''
def seqtoi(seq):
    nucleotides = {'A':0,'C':1,'G':2,'T':3}
    binrep = 0
    for i in range(0,len(seq)):
        binrep <<= 2
        binrep |= nucleotides[seq[i]]
    return binrep

def is_dna(sequence,length=0):
    valid_dna = 'ACGT'
    check = all(i in valid_dna for i in sequence.upper())
    if check and length > 0:
        check = (len(sequence) == length)
    return check

def isbound_escore(seq,etable,kmer=8,bsite_cutoff=0.4,nbsite_cutoff=0.35):
    nucleotides = {'A':0,'C':1,'G':2,'T':3}
    grapper = (2<<(8*2-1))-1
    binrep = seqtoi(seq[0:kmer])
    elist = [etable[binrep]]
    for i in range(kmer,len(seq)):
        binrep = ((binrep << 2) | seqtoi(seq[i])) & grapper
        elist.append(etable[binrep])
    if max(elist) < nbsite_cutoff:
        return "unbound"
    else:
        isbound = False
        for i in range(0,len(elist)):
            if elist[i] > bsite_cutoff:
                if isbound:
                    return "bound"
                else:
                    isbound = True
            else:
                isbound = False
        return "ambiguous"

"""
return: "is bound wild > is bound mut"
"""
def isbound_escore_18mer(seq18mer,pbm_name,escore_dir,spec_ecutoff=0.35,nonspec_ecutoff=0.4):
    eshort_path = "%s/%s_escore.txt" % (escore_dir,pbm_name)
    # TODO: avoid IO, maybe using global var?
    short2long_map = "%s/index_short_to_long.csv" % (escore_dir)

    #  -- this definitely needs to go to a database
    with open(eshort_path) as f:
        eshort = [float(line) for line in f]
    with open(short2long_map) as f:
        next(f)
        emap = [int(line.split(",")[1])-1 for line in f]

    elong = [eshort[idx] for idx in emap]

    wild = seq18mer[:-1]
    mut = seq18mer[:8] + seq18mer[-1] + seq18mer[9:-1]

    return "%s>%s" % (isbound_escore(wild,elong,bsite_cutoff=spec_ecutoff,nbsite_cutoff=nonspec_ecutoff),
                      isbound_escore(mut,elong,bsite_cutoff=spec_ecutoff,nbsite_cutoff=nonspec_ecutoff))

def delete_file(filename):
    '''
    this simple function is used to delete user file after USER_DATA_EXPIRY
    seconds
    '''
    if os.path.exists(filename):
        os.remove(filename)
        print("Deleted: %s"%filename)
    else:
        print("%s doesn't exist for deletion"%filename)

def line_count(file_path):
    num = subprocess.check_output(['wc', '-l', file_path])
    num = num.split()
    return int(num[0])

# https://stackoverflow.com/questions/2130016/splitting-a-list-into-n-parts-of-approximately-equal-length
def chunkify(lst,n):
    return [lst[i::n] for i in range(n)]
