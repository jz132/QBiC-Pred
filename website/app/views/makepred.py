import os
import sys
sys.path.insert(0, '..')

from flask import request,render_template,make_response,jsonify,url_for,send_from_directory,Response
from werkzeug.utils import secure_filename
import ast
import json

from celery import Celery,chain
from app import app,db

import app.controller.celerytask as celerytask
import app.controller.utils as utils

ALLOWED_EXTENSIONS = set(['csv','tsv','vcf','txt'])
#app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# view specific utils
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
# ==========================

def is_valid_cols(filepath):
    file_extension = os.path.splitext(filepath)[1]
    if file_extension == ".tsv" or file_extension == ".csv":
        required = ['chromosome','chromosome_start','mutation_type','mutated_from_allele','mutated_to_allele']
        with open(filepath) as f:
            file_extension = os.path.splitext(filepath)[1]
            if file_extension == ".tsv":
                incols = f.readline().strip().split("\t")
            else: # must be csv since we checked it
                incols = f.readline().strip().split(",")
        if not all(elem in incols for elem in required):
            os.remove(filepath)
            return False
        else:
            return True
    elif file_extension == ".vcf":
        with open(filepath) as f:
            if len(f.readline().strip().split("\t")) == 5:
                return True
            else:
                os.remove(filepath)
                return False
    elif file_extension == ".txt":
        with open(filepath) as f:
            for line in f:
                line = line.strip()
                if "\t" in line:
                    line = line.split("\t")
                else:
                    line = line.split()
                valid = len(line) >= 2 and utils.is_dna(line[0],length=17) and utils.is_dna(line[1],length=1)
                if not valid:
                #    os.remove(filepath) # TODO: move this somewhere else
                    return False
        return True
    return False


'''
return empty string if there is no file, filename if there is file and it has been handled
by the function
return: status, msg
msg = filename if success
'''
def prepare_request(request):
    nonspecbind_thres =  float(request.form.get("nonspecific-binding-thres"))
    if nonspecbind_thres < 0.2 or nonspecbind_thres > 0.4:
        return {"status":'error',"message":'nonspecific binding threshold should be between 0.2 and 0.4'}
    specbind_thres =  float(request.form.get("specific-binding-thres"))
    if specbind_thres < 0.3 or specbind_thres > 0.5:
        return {"status":'error',"message":'specific binding threshold should be between 0.3 and 0.5'}
    if nonspecbind_thres >= specbind_thres:
        return {"status":'error',"message":'nonspecific binding threshold should be less than specific binding threshold'}
    # First, check if the input file is valid, this depends on the input-mode
    if request.form.get('input-mode') == "1": # not example
        if 'input-file' not in request.files:
            return {"status":'error',"message":'no input file part'}
        file = request.files['input-file']
        # Check file size
        file.seek(0, os.SEEK_END)
        file_length = file.tell()
        if file_length > app.config['MAX_FILE_LENGTH']:
            maxsize = app.config['MAX_FILE_LENGTH'] / (1024*1024)
            return {"status":'error',"message":'uploaded file is larger than the allowed maximum size of %dMB' % maxsize}
        file.seek(0) # seek back
        # Can only accept tsv or csv or vcf
        if not allowed_file(file.filename):
            return {"status":'error',"message":'please upload only tsv/csv, vcf, or txt (with sequences) file'}
        # No file selected:
        if file.filename == '':
            return {"status":'error',"message":'no selected file'}
        # Check if we have all the columns we need
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        if not is_valid_cols(filepath):
            utils.delete_file(filepath)
            return {"status":'error',"message":'some required fields are missing from the input file or some values are incorrect'}
        returnstatus = "success"
    else: #input-mode==2
        if not request.form.get('examplelist'):
            return  {"status":'error',"message":'no input file part'}
        returnstatus = "example"
        egkey = request.form.get('examplelist')
        filename = app.config['INPUT_EXAMPLE_DICT'][egkey]['inputfile']
    # No TFs selected
    if not request.form.getlist('pred-select'):
        return {"status":'error',"message":'please select transcription factors'}
    # Check if p-value is in the valid range
    filteropt = int(request.form.get('optradio'))
    if filteropt == 2:
        pval = float(request.form.get('output-selection-opt'))
        if pval > 1 or pval < 0:
            return {"status":'error',"message":'p-value should be between 0 and 1'}
    # Finally, everything is okay
    retdict = {"status":returnstatus,"filename":filename}
    if request.form.get('input-mode') == "1":
        retdict["linecount"] = utils.line_count(filepath)
    else: # if it is an example, just set linecount to 0 since we know it will be safe
        retdict["linecount"] = 0
    return retdict

@app.route('/upload', methods=['POST'])
def handle_upload():
    MAX_LINES = 50000
    tfpref = "prediction6mer." # for rapid, need to be empty for now
    tfext = ".txt"
    if request.method == 'POST':
        req = prepare_request(request)
        if req["status"] == 'error':
            return jsonify({'Message':req["message"]}), 500
        else:
            if req["status"] == "example":
                filepath = app.config['STATIC_EXAMPLE_DIR'] + req["filename"]
            else:
                filepath = app.config['UPLOAD_FOLDER'] +req["filename"]
            # request.form.getlist('pred-select'):['Arid3a:Arid3a_3875.1_v1_deBruijn', 'Bhlhb2:Bhlhb2_4971.1_v1_deBruijn']
            genes_selected = [elm.split(":")[0] for elm in request.form.getlist('pred-select')]

            select_list = [elm.split(":")[1] for elm in request.form.getlist('pred-select')]
            unique_pbms = list({tfpref+x+tfext for pbm in select_list for x in pbm.split(',')})

            print(unique_pbms, genes_selected)
            chrver = request.form.get('genome-select')

            filteropt = int(request.form.get('optradio'))
            if filteropt == 1:
                filterval = int(request.form.get('output-selection-opt'))
            else:
                filterval = float(request.form.get('output-selection-opt'))

            if req["linecount"] > MAX_LINES or request.form.get("escore-toggle") == "off":
                spec_escore_thres = -1
                nonspec_escore_thres = -1
            else:
                spec_escore_thres = float(request.form.get('specific-binding-thres'))
                nonspec_escore_thres = float(request.form.get('nonspecific-binding-thres'))

            task = chain(celerytask.inittbl.s(filepath,
                        app.config['CHRDIR'] +"/"+chrver),
                        celerytask.do_prediction.s(unique_pbms,genes_selected,filteropt,filterval,spec_escore_thres,nonspec_escore_thres)).apply_async() # put genes_selected here

            # ==== STORING IN REDIS PART ====
            # it is important to store these in redis so information can be
            # passed to different browsers/machines.
            session_info = {"parent_id":task.parent.id,
                            "task_id":task.id,
                            "filename":req["filename"],
                            "genes_selected":genes_selected,
                            "filteropt":filteropt,
                            "filterval":filterval,
                            "chrver":request.form.get('genome-select'),
                            "spec_escore_thres":spec_escore_thres,
                            "nonspec_escore_thres":nonspec_escore_thres
                            }
            if db.exists(task.id):
                db.delete(task.id)
            db.hmset(task.id,session_info)
            db.expire(task.id, app.config['USER_DATA_EXPIRY'])
            # ================================
            task.forget() # not sure if needed???

            warning = ""
            if req["linecount"] > MAX_LINES:
                warning = "Notice: We turned off PBM E-score binding prediction since the number of lines is larger than %d. Please contact qbic-pred@duke.edu if you really need the E-score binding prediction." % MAX_LINES
            resp = make_response(jsonify({"warning":warning}), 202, {'Location': url_for('process_request',job_id=task.id)})

            job_name = request.form.get("job-name") if request.form.get("job-name") else task.id
            # we can put this in cookie to let browser save the recent jobs
            resp.set_cookie("qbic_recents:%s"%task.id, job_name, max_age=app.config['USER_DATA_EXPIRY'])
            return resp # {'Location': url_for('task_status',task_id=task.id)

#========Filling dropdown==========

@app.route('/checktfnames', methods=['GET','POST'])
def check_tfnames():
    tflist = request.get_json()['tfs']
    found = []
    notfound = []
    for tf in tflist:
        if tf in app.config['HGNC_GENE_NAMES']:
            found.append(tf)
        else:
            notfound.append(tf)
    return make_response(jsonify({}), 202, {'found':json.dumps(found),'notfound':json.dumps(notfound)})

@app.route('/predlist', methods=['GET'])
def get_predlist():
    with open(app.config['HUGO_PBM_MAPPING'],'r') as f:
        family_map = {}
        for line in f:
            key,val = line.strip().split("->")
            valmap = {z[0]:z[1] for z in (y.split(":") for y in (x for x in val.split(";")))} # generator
            family_map[key] = valmap
    return jsonify(family_map)

@app.route('/tfsdownload/<strlist>', methods=['GET'])
def make_tflist(strlist):
    tflist = ast.literal_eval(strlist)

    ''' return the csv file without having to save it '''
    return Response(
        "\n".join(tflist),
        mimetype="text/csv",
        headers={"Content-disposition":
                 "attachment; filename=tfs-selected.txt"})

@app.route('/examplelist', methods=['GET'])
def get_examplelist():
    return jsonify(app.config['INPUT_EXAMPLE_DICT'])

#==================

@app.route('/makeprediction', methods=['GET', 'POST'])
def makepred():
    return render_template("makepred.html")
