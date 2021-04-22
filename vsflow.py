import argparse
import csv
import math
import multiprocessing as mp
import os
import time
from subprocess import run, PIPE, Popen
from itertools import groupby
import pickle
import random
import copy

import pandas as pd
import requests
import xlsxwriter
#from bs4 import BeautifulSoup
from fpdf import FPDF, set_global
#from pdfrw import PdfReader
#from pdfrw import PdfWriter
from pymol import cmd
from rdkit import Chem
from rdkit import DataStructs
from rdkit import RDLogger
from rdkit.Chem import AllChem as Chem
from rdkit.Chem import Descriptors
from rdkit.Chem import Draw, MACCSkeys
from rdkit.Chem.AtomPairs import Pairs, Torsions
from rdkit.Chem.Draw import SimilarityMaps
from molvs.tautomer import TautomerCanonicalizer, TautomerEnumerator
from molvs.standardize import Standardizer
import matplotlib as mpl
from rdkit.Chem import rdMolAlign
from rdkit.Chem.Pharm2D import Gobbi_Pharm2D, Generate
from xlrd import open_workbook
mpl.rc('figure', max_open_warning=0)
RDLogger.logger().setLevel(RDLogger.CRITICAL)
import visualize
import sss
import read
import write_output
import fpsearch
import  shapesearch
import prepare
from rdkit.Chem.Draw import rdMolDraw2D


# set path and global variables
script_path = os.path.dirname(os.path.abspath(__file__))
home = os.path.expanduser("~")
#database_path = f"{home}/.vsflow/DATABASES.csv"
#database_global = f"{script_path}/DATABASES.csv"
ttf_path = f"{script_path}/resources/DejaVuSansMono.ttf"
set_global("FPDF_CACHE_MODE", 2)
set_global("FPDF_CACHE_DIR", script_path)

## Read path of integrated databases or generate generate/update config files
if os.path.exists(f"{home}/.vsflow"):
    config = pickle.load(open(f"{home}/.vsflow/.config", "rb"))
    db_config = pickle.load(open(f"{home}/.vsflow/.db_config", "rb"))
    db_default = pickle.load(open(f"{home}/.vsflow/.db_default", "rb"))
else:
    os.mkdir(f"{home}/.vsflow")
    config = {"global_db": f"{script_path}/DATABASES", "local_db": f"{home}/VSFlow_Databases"}
    db_config = {}
    db_default = ""
print(db_config)
for key in config:
    try:
        for file in os.listdir(config[key]):
            if file.endswith(".vsdb"):
                if file.rsplit(".vsdb", maxsplit=1)[0] in db_config:
                    if db_config[file.rsplit(".vsdb", maxsplit=1)[0]][0] == time.ctime(os.path.getmtime(f"{config[key]}/{file}")):
                        continue
                print("Updating databases")
                db = pickle.load(open(f"{config[key]}/{file}", "rb"))
                db_info = db["config"]
                n_mols = db_info[2]
                standardized = db_info[0]
                n_confs = db_info[1]
                num_seed = db_info[3]
                db_config[file.rsplit(".vsdb", maxsplit=1)[0]] = [time.ctime(os.path.getmtime(f"{config[key]}/{file}")),
                                                                  standardized,
                                                                  n_confs,
                                                                  n_mols,
                                                                  num_seed]
                del db
    except FileNotFoundError:
        continue
to_remove = []
for db_info in db_config:
    try:
        if f"{db_info}.vsdb" not in os.listdir(config["global_db"]):
            if f"{db_info}.vsdb" not in os.listdir(config["local_db"]):
                #db_config.pop(db_info)
                to_remove.append(db_info)
    except FileNotFoundError:
        try:
            if f"{db_info}.vsdb" not in os.listdir(config["global_db"]):
                #db_config.pop(db_info)
                to_remove.append(db_info)
        except FileNotFoundError:
            try:
                if f"{db_info}.vsdb" not in os.listdir(config["local_db"]):
                    #db_config.pop(db_info)
                    to_remove.append(db_info)
            except FileNotFoundError:
                pass
for entry in to_remove:
    db_config.pop(entry)
    if entry == db_default:
        db_default = ""
pickle.dump(config, open(f"{home}/.vsflow/.config", "wb"))
pickle.dump(db_config, open(f"{home}/.vsflow/.db_config", "wb"))
pickle.dump(db_default, open(f"{home}/.vsflow/.db_default", "wb"))
print(config)
print(db_config)
print(db_default)
parser = argparse.ArgumentParser(description="Virtual Screening Workflow")
print('''\
**************************

 VV        VV  SSSSSSS             VSFlow   
  VV      VV  SSS    SS       Virtual Screening
   VV    VV    SSSS               Workflow
    VV  VV       SSSS         
     VVVV     SS    SSS       
      VV       SSSSSSS           

**************************
''')
subparsers = parser.add_subparsers(title="mode", help="specify mode of vsflow")

# substructure search

substructure = subparsers.add_parser("substructure", description="perform a substructure search")
group = substructure.add_mutually_exclusive_group(required=True)
group.add_argument("-i", "--input", help="specify path of input file [sdf, csv, xlsx]", metavar="")
group.add_argument("-smi", "--smiles", help="specify SMILES string on command line in double quotes",
                   action="append", metavar="")
group.add_argument("-sma", "--smarts", help="specify SMARTS string on command line in double quotes",
                   action="append", metavar="")
substructure.add_argument("-d", "--database", help="specify path of the database file [sdf or vsdb] or specify the "
                                                   "shortcut for an integrated database", default=db_default,
                          metavar="")
substructure.add_argument("-o", "--output", help="specify name of output file [default: substructure.sdf]",
                          default="substructure.sdf", metavar="")
substructure.add_argument("-m", "--mode", help="choose a mode for substructure search [std, all_tauts, can_taut, "
                                               "no_std]", choices=["std", "all_tauts", "can_taut", "no_std"],
                          default="std", metavar="")
substructure.add_argument("-np", "--nproc", type=int, help="Specify the number of processors used when the application "
                                                           "is run in multiprocessing mode.", metavar="")
substructure.add_argument("-fm", "--fullmatch", help="when specified, only full matches are returned",
                          action="store_true")
substructure.add_argument("-p", "--properties",
                          help="if specified, calculated molecular properties are written to the output files",
                          action="store_true")
substructure.add_argument("-nt", "--ntauts",
                          help="maximum number of query tautomers to be enumerated in mode all_tauts [default: 100]",
                          type=int, default=100, metavar="")
substructure.add_argument("-mf", "--multfile", help="generate separate output files for every query molecule",
                          action="store_true")
substructure.add_argument("--filter", help="specify property to filter screening results", action="append", metavar="")
substructure.add_argument("--mol_column",
                          help="Specify name (or position) of mol column [SMILES/InChI] in csv/xlsx file if not "
                               "automatically recognized", metavar="")
substructure.add_argument("--delimiter", help="Specify delimiter of csv file if not automatically recognized",
                          metavar="")
substructure.add_argument("--header", help="Specify number of row in csv/xlsx file to be used as column names "
                                           "[default: 1, e.g. first row]", type=int, default=1, metavar="")
substructure.add_argument("--pdf", help="generate a pdf file for all results", action="store_true")
substructure.add_argument("--combine", action="store_true")


def check_filter(filter_list):
    choices = ["mw", "logp",
               "hdon",
               "hacc", "rotb",
               "narom", "nhet",
               "tpsa"]
    filter_dict = {}
    for prop in choices:
        for entry in filter_list:
            if prop in entry:
                if entry.startswith(prop):
                    try:
                        x = float(entry.split(prop)[1])
                        filter_dict[prop] = x
                    except ValueError:
                        parser.error(message=f"Filter {entry} not supported")
    return filter_dict


def calc_props(mol, props):
    props["MW (g/mol)"] = str(round(Descriptors.MolWt(mol), 2))
    props["cLogP"] = str(round(Descriptors.MolLogP(mol), 2))
    props["TPSA (A\u00b2)"] = str(round(Descriptors.TPSA(mol), 2))
    props["HDon"] = str(Descriptors.NumHDonors(mol))
    props["HAcc"] = str(Descriptors.NumHAcceptors(mol))
    props["RotBonds"] = str(Descriptors.NumRotatableBonds(mol))
    props["AromRings"] = str(Descriptors.NumAromaticRings(mol))
    props["HetAromRings"] = str(Descriptors.NumAromaticHeterocycles(mol))


def read_database(args):
    mols = {}
    if args.database in db_config:
        try:
            mols = pickle.load(open(f"{config['local_db']}/{args.database}.vsdb", "rb"))
        except FileNotFoundError:
            try:
                mols = pickle.load(open(f"{config['global_db']}/{args.database}.vsdb", "rb"))
            except FileNotFoundError:
                parser.error(
                    message=f"{args.database} not found. Please make sure you specified the correct shortcut")
    else:
        if os.path.exists(args.database):
            if args.database.endswith(".vsdb"):
                try:
                    mols = pickle.load(open(args.database, "rb"))
                except:
                    parser.error(message=f"{args.output} could not be opened. Please make sure the file has the correct "
                                               f"format")

            else:
                if args.nproc:
                    print("here")
                    pool = mp.Pool(processes=args.nproc)
                    mols, failed = read.read_sd_mp(args.database, pool)
                    pool.close()

                else:
                    mols, failed = read.read_db_from_sd(args.database)
                if failed:
                    print(f"{len(failed)} of {len(mols) + len(failed)} molecules in {args.database} could not be processed")
                if not mols:
                    parser.error(message="No molecules could be read from SD file. Please make sure it has the right "
                                               "format")
        else:
            parser.error(message=f"File {args.database} not found. Please make sure you specified the correct path")
    return mols


def read_input(args):
    if args.smarts:
        query = read.read_smarts(args.smarts)
        if not query:
            parser.error(message="No valid molecule(s) could be generated from the provided SMARTS.")
    elif args.smiles:
        query = read.read_smiles(args.smiles, args.mode, args.ntauts)
        if not query:
            parser.error(message="No valid molecule(s) could be generated from the provided SMILES.")
    else:
        if os.path.exists(args.input):
            query = read.read_file(args.input, args.mol_column, args.delimiter, args.mode, args.ntauts)
            if not query:
                if args.input.endswith(".sdf"):# or args.input_format == "sdf":
                    parser.error(message="No valid molecules could be read from SD file.")
                elif args.input.endswith(".csv"):# or args.input_format == "csv":
                    parser.error(message="No valid molecules could be read from input file. Please check/specify "
                                               "name of SMILES/InChI containing column (--mol_column) or check/specify the"
                                               "separator (--delimiter)")
                elif args.input.endswith(".xlsx"):# or args.input_format == "xlsx":
                    parser.error(message="No valid molecules could be read from input file. Please check/specify "
                                               "name of SMILES/InChI containing column (--mol_column))")
                else:
                    parser.error(message="File format not recognized. Please specify the file format (--file_format)")
        else:
            query = {}
            parser.error(message=f"File {args.input} not found. Please make sure you specified the correct path")
    return query


def substruct(args):
    start_time = time.time()
    print(f"Start: {time.strftime('%m/%d/%Y, %H:%M:%S', time.localtime())}")
    # check args.nproc
    if args.nproc:
        if 1 < args.nproc < mp.cpu_count():
            print(f"Running in parallel mode on {args.nproc} threads")
            pass
        elif args.nproc <= 1:
            print("Running in single core mode")
            args.nproc = None
        else:
            args.nproc = mp.cpu_count()
            print(f"Running in parallel mode on {args.nproc} threads")
    else:
        print("Running in single core mode")
    # check if filter is set correct
    if args.filter:
        filter_dict = check_filter(args.filter)
    else:
        filter_dict = {}
    # check if output path is valid
    if "/" in args.output:
        out_path = args.output.rsplit("/", maxsplit=1)[0]
        if not os.path.exists(out_path):
            parser.error(message=f"{args.output} is no valid path. Please check if you specified the correct path")
    print(f"Loading database {args.database} ...")
    sub_time = time.time()
    # load database if database path is valid
    mols = read_database(args)
    try:
        db_desc = mols.pop("config")
    except KeyError:
        db_desc = None
    sub_time_2 = time.time()
    sub_dur = sub_time_2 - sub_time
    print(sub_dur)
    print("Reading query input ...")
    # load input if paths are correct
    query = read_input(args)
    # set mol used based on selected mode and database
    if db_desc:
        if db_desc[0] == "yes":
            if args.mode == "std":
                key = "mol_sta"
            elif args.mode == "can_taut":
                key = "mol_can"
            elif args.mode == "all_tauts":
                key = "mol_sta"
            else:
                key = "mol"
        else:
            key = "mol"
    else:
        key = "mol"
    results = {}
    # perform substructure search based on selected parameters
    if args.fullmatch:
        if args.nproc:
            pool = mp.Pool(processes=args.nproc)
            if args.mode == "std" or args.mode == "mol_can":
                sss.sss_fm_mp(query, mols, key, filter_dict, results, pool)
            elif args.mode == "no_std":
                sss.sss_fm_nost_mp(query, mols, key, filter_dict, results, pool)
            else:
                sss.sss_fm_taut_mp(query, mols, key, filter_dict, results, pool)
            pool.close()
        else:
            if args.mode == "std" or args.mode == "mol_can":
                sss.sss_fm(query, mols, key, filter_dict, results)
            elif args.mode == "no_std":
                sss.sss_fm_nost(query, mols, key, filter_dict, results)
            else:
                sss.sss_fm_taut(query, mols, key, filter_dict, results)
    else:
        if args.nproc:
            pool = mp.Pool(processes=args.nproc)
            if args.mode == "std" or args.mode == "can_taut" or args.mode == "no_std":
                sss.sss_mp(query, mols, key, filter_dict, results, pool)
            else:
                sss.sss_mp_taut(query, mols, key, filter_dict, results, pool)
            pool.close()
        else:
            if args.mode == "std" or args.mode == "can_taut" or args.mode == "no_std":
                sss.sss(query, mols, key, filter_dict, results)
            else:
                sss.sss_taut(query, mols, key, filter_dict, results)
    sub_time_2 = time.time()
    sub_dur = sub_time_2 - sub_time
    print(sub_dur)
    print("Finished substructure search")
    del mols
    # calculate properties if desired
    if args.properties:
        for i in results:
            calc_props(results[i]["mol"], results[i]["props"])
    # write results to output file(s)
    print(f"{len(results)} matches found")
    print("Generating output file(s) ...")
    if args.combine:
        if args.smiles or args.smarts:
            if args.smiles:
                npatts = len(args.smiles)
            else:
                npatts = len(args.smarts)
            if npatts > 1:
                print("and")
                gr_res = [list(group) for k, group in groupby(sorted(results.values(), key=lambda entry: entry["num"]),
                                                              key=lambda entry: entry["num"])]
                counter = 0
                results = {}
                for entry in gr_res:
                    if len(entry) == npatts:
                        for i in range(1, len(entry)):
                            for match in entry[i]["match"]:
                                entry[0]["match"].append(match)
                            entry[0]['props']['QuerySmiles'] = f"{entry[0]['props']['QuerySmiles']} and {entry[i]['props']['QuerySmiles']}"
                        results[counter] = entry[0]
                        counter += 1
    if args.multfile:
        if results:
            if args.output.endswith(".csv"):
                write_output.gen_csv_xls_mult(query, results, args.output)
            elif args.output.endswith(".xlsx") or args.output.endswith(".xls"):
                write_output.gen_csv_xls_mult(query, results, args.output)
            else:
                write_output.gen_sdf_mult(query, results, args.output)
            if args.pdf:
                print("Generating PDF file(s) ...")
                if args.output.endswith(".sdf") or args.output.endswith(".csv") or args.output.endswith(".xlsx") or args.output.endswith(".xls"):
                    out_file = args.output.rsplit(".", maxsplit=1)[0]
                else:
                    out_file = args.output
                visualize.gen_pdf_mf(query, results, out_file, ttf_path)
    else:
        if results:
            if args.output.endswith(".csv") or args.output.endswith(".xlsx") or args.output.endswith(".xls"):
                write_output.gen_csv_xls(results, args.output)
            else:
                write_output.gen_sdf(results, args.output)
            if args.pdf:
                print("Generating PDF file(s) ...")
                if args.output.endswith(".sdf") or args.output.endswith(".csv") or args.output.endswith(
                        ".xlsx") or args.output.endswith(".xls"):
                    out_file = f"{args.output.rsplit('.', maxsplit=1)[0]}.pdf"
                else:
                    out_file = f"{args.output}.pdf"
                visualize.gen_pdf(query, results, out_file, ttf_path)
    end_time = time.time()
    print(f"Finished: {time.strftime('%m/%d/%Y, %H:%M:%S', time.localtime())}")
    duration = round(end_time - start_time, 5)
    print(f"Finished in {duration} seconds")


substructure.set_defaults(func=substruct)


## Fingerprint similarity search

fp_sim = subparsers.add_parser("fpsim", description="molecular similarity search using fingerprints")
group_fp = fp_sim.add_mutually_exclusive_group(required=True)
group_fp.add_argument("-i", "--input", help="specify path of input file [sdf, csv, xlsx]", metavar="")
group_fp.add_argument("-smi", "--smiles", help="specify SMILES string on command line in double quotes",
                      action="append", metavar="")
group_fp.add_argument("-sma", "--smarts", help="specify SMARTS string on command line in double quotes",
                      action="append", metavar="")
fp_sim.add_argument("-d", "--database", help="specify path of the database file [sdf or vsdb] or specify the shortcut "
                                             "for an integrated database", default=db_default, metavar="")
fp_sim.add_argument("-o", "--output", help="specify name of output file [default: fingerprint.sdf]",
                    default="fingerprint.sdf", metavar="")
fp_sim.add_argument("-m", "--mode", help="choose a mode for similarity search [std, all_tauts, can_taut, no_std]",
                    choices=["std", "all_tauts", "can_taut", "no_std"], default="std", metavar="")
fp_sim.add_argument("-np", "--nproc", type=int, help="Specify the number of processors used when the application is "
                                                      "run in multiprocessing mode.", metavar="")
fp_sim.add_argument("-f", "--fingerprint", help="specify fingerprint to be used [rdkit, ecfp, fcfp, ap, tt, maccs], [default: fcfp]",
                    choices=["rdkit", "ecfp", "fcfp", "ap", "tt", "maccs"], default="fcfp", metavar="")
fp_sim.add_argument("-r", "--radius", help="specify radius of circular fingerprints ecfp and fcfp [default: 3]",
                    type=int, default=3, metavar="")
fp_sim.add_argument("-nb", "--nbits", help="specify bit size of fingerprints [default: 4096]", type=int,
                    default=4096, metavar="")
fp_sim.add_argument("-s", "--similarity", help="specify fingerprint similarity metric to be used [tan, dice, cos, sok, "
                                               "russ, kulc, mcco, tver], [default: tan]",
                    choices=["tan", "dice", "cos", "sok", "russ", "kulc", "mcco", "tver"], default="tan", metavar="")
fp_sim.add_argument("-t", "--top_hits", type=int, default=10,
                    help="Maximum number of molecules with highest similarity to keep [default: 10]", metavar="")
fp_sim.add_argument("-c", "--cutoff", help="specify cutoff value for similarity coefficient", type=float, metavar="")
fp_sim.add_argument("-nt", "--ntauts", help="maximum number of query tautomers to be enumerated in mode all_tauts "
                                     "[default: 100]", type=int, default=100, metavar="")
fp_sim.add_argument("-mf", "--multfile", help="generate separate output files for every query molecule",
                    action="store_true")
fp_sim.add_argument("-p", "--properties",
                    help="if specified, calculated molecular properties are written to the output files",
                    action="store_true")
fp_sim.add_argument("--filter", help="specify property to filter screening results", action="append", metavar="")
fp_sim.add_argument("--mol_column", help="Specify name (or position) of mol column [SMILES/InChI] in csv/xlsx file if "
                                         "not automatically recognized", metavar="")
fp_sim.add_argument("--delimiter", help="Specify delimiter of csv file if not automatically recognized", metavar="")
fp_sim.add_argument("--header", help="Specify number of row in csv/xlsx file to be used as column names "
                                     "[default: 1, e.g. first row]", type=int, default=1, metavar="")
fp_sim.add_argument("--pdf", help="generate a pdf file for all results", action="store_true")
fp_sim.add_argument("--simmap", help="generates similarity maps for supported fingerprints in pdf file",
                    action="store_true")
fp_sim.add_argument("--no_chiral", help="specify if chirality should not be considered", action="store_false")
fp_sim.add_argument("--tver_alpha", help="specify alpha parameter (weighs database molecule) for Tversky similarity "
                                         "[default: 0.5]", default=0.5, type=float, metavar="")
fp_sim.add_argument("--tver_beta", help="specify beta parameter (weighs query molecule) for Tversky similarity "
                                        "[default: 0.5]", default=0.5, type=float, metavar="")


def fingerprint(args):
    start_time = time.time()
    print(f"Start: {time.strftime('%m/%d/%Y, %H:%M:%S', time.localtime())}")
    # check args.nproc
    if args.nproc:
        if 1 < args.nproc < mp.cpu_count():
            print(f"Running in parallel mode on {args.nproc} threads")
            pass
        elif args.nproc <= 1:
            print("Running in single core mode")
            args.nproc = None
        else:
            args.nproc = mp.cpu_count()
            print(f"Running in parallel mode on {args.nproc} threads")
    else:
        print("Running in single core mode")
    # check if filter is set correct
    if args.filter:
        filter_dict = check_filter(args.filter)
    else:
        filter_dict = {}
    # check if output path is valid
    if "/" in args.output:
        out_path = args.output.rsplit("/", maxsplit=1)[0]
        if not os.path.exists(out_path):
            parser.error(message=f"{args.output} is no valid path. Please check if you specified the correct path")
    print(f"Loading database {args.database} ...")
    sub_time = time.time()
    # load database if database path is valid
    mols = read_database(args)
    try:
        db_desc = mols.pop("config")
    except KeyError:
        db_desc = None
    sub_time_2 = time.time()
    sub_dur = sub_time_2 - sub_time
    print(sub_dur)
    print("Reading query input ...")
    # load input if paths are correct
    query = read_input(args)
    # set mol used based on selected parameters and database
    if db_desc:
        if db_desc[0] == "yes":
            if args.mode == "std":
                key = "mol_sta"
            elif args.mode == "can_taut":
                key = "mol_can"
            elif args.mode == "all_tauts":
                key = "mol_sta"
            else:
                key = "mol"
        else:
            key = "mol"
    else:
        key = "mol"
    # Calculate fingerprints
    print("Calculating fingerprints ...")
    sub_time = time.time()
    features = False
    if args.fingerprint == "fcfp" or args.fingerprint == "ecfp":
        if args.fingerprint == "fcfp":
            name = f"FCFP{args.radius * 2}-like Morgan {args.nbits} bits"
            features = True
        else:
            name = f"ECFP{args.radius * 2}-like Morgan {args.nbits} bits"
        if args.nproc:
            pool = mp.Pool(processes=args.nproc)
            argslist = [(mols[i][key], i, args.radius, features, args.no_chiral, args.nbits) for i in mols]
            fps = pool.starmap(fpsearch.fp_morgan_mp, argslist)
            fpsearch.set_fp_mp(fps, mols)
            argslist = [(query[j]["mol"], j, args.radius, features, args.no_chiral, args.nbits) for j in query]
            fps = pool.starmap(fpsearch.fp_morgan_mp, argslist)
            fpsearch.set_fp_mp(fps, query)
            del argslist
            del fps
            pool.close()
        else:
            fpsearch.fp_morgan(mols, key, args.radius, args.nbits, features, args.no_chiral)
            fpsearch.fp_morgan(query, "mol", args.radius, args.nbits, features, args.no_chiral)
    elif args.fingerprint == "rdkit":
        name = f"RDKit {args.nbits} bits"
        if args.nproc:
            pool = mp.Pool(processes=args.nproc)
            argslist = [(mols[i][key], i, args.nbits) for i in mols]
            fps = pool.starmap(fpsearch.fp_rdkit_mp, argslist)
            fpsearch.set_fp_mp(fps, mols)
            argslist = [(query[j]["mol"], j, args.nbits) for j in query]
            fps = pool.starmap(fpsearch.fp_rdkit_mp, argslist)
            fpsearch.set_fp_mp(fps, query)
            del argslist
            del fps
            pool.close()
        else:
            fpsearch.fp_rdkit(mols, key, args.nbits)
            fpsearch.fp_rdkit(query, "mol", args.nbits)
    elif args.fingerprint == "ap":
        name = f"AtomPairs {args.nbits} bits"
        if args.nproc:
            pool = mp.Pool(processes=args.nproc)
            argslist = [(mols[i][key], i, args.nbits, args.no_chiral) for i in mols]
            fps = pool.starmap(fpsearch.fp_atompairs_mp, argslist)
            fpsearch.set_fp_mp(fps, mols)
            argslist = [(query[j]["mol"], j, args.nbits, args.no_chiral) for j in query]
            fps = pool.starmap(fpsearch.fp_atompairs_mp, argslist)
            fpsearch.set_fp_mp(fps, query)
            del argslist
            del fps
            pool.close()
        else:
            fpsearch.fp_atompairs(mols, key, args.nbits, args.no_chiral)
            fpsearch.fp_atompairs(query, "mol", args.nbits, args.no_chiral)
    elif args.fingerprint == "tt":
        name = f"TopologicalTorsion {args.nbits} bits"
        if args.nproc:
            pool = mp.Pool(processes=args.nproc)
            argslist = [(mols[i][key], i, args.nbits, args.no_chiral) for i in mols]
            fps = pool.starmap(fpsearch.fp_torsion_mp, argslist)
            fpsearch.set_fp_mp(fps, mols)
            argslist = [(query[j]["mol"], j, args.nbits, args.no_chiral) for j in query]
            fps = pool.starmap(fpsearch.fp_torsion_mp, argslist)
            fpsearch.set_fp_mp(fps, query)
            del argslist
            del fps
            pool.close()
        else:
            fpsearch.fp_torsion(mols, key, args.nbits, args.no_chiral)
            fpsearch.fp_torsion(query, "mol", args.nbits, args.no_chiral)
    else:
        name = "MACCS"
        if args.nproc:
            pool = mp.Pool(processes=args.nproc)
            argslist = [(mols[i][key], i) for i in mols]
            fps = pool.starmap(fpsearch.fp_maccs_mp, argslist)
            fpsearch.set_fp_mp(fps, mols)
            argslist = [(query[j]["mol"], j) for j in query]
            fps = pool.starmap(fpsearch.fp_maccs_mp, argslist)
            fpsearch.set_fp_mp(fps, query)
            del argslist
            del fps
            pool.close()
        else:
            fpsearch.fp_maccs(mols, key)
            fpsearch.fp_maccs(query, "mol")
    # Calculate similarities
    print("Calculating similarities ...")
    if args.cutoff:
        if args.similarity == "tver":
            results = fpsearch.sim_tver(mols, query, key, args.cutoff, args.similarity, filter_dict, name,
                                        args.tver_alpha, args.tver_beta)
        else:
            results = fpsearch.sim(mols, query, key, args.cutoff, args.similarity, filter_dict, name)
    else:
        if args.similarity == "tver":
            results = fpsearch.sim_top_tver(mols, query, key, args.top_hits, args.similarity, filter_dict, name,
                                            args.tver_alpha, args.tver_beta)
            print(len(results))
        else:
            results = fpsearch.sim_top(mols, query, key, args.top_hits, args.similarity, filter_dict, name)
    sub_time_2 = time.time()
    sub_dur = sub_time_2 - sub_time
    print(sub_dur)
    del mols
    print(f"{len(results)} matches found")
    # calculate molecular properties
    if args.properties:
        for i in results:
            calc_props(results[i]["mol"], results[i]["props"])
    # write output files
    print("Generating output file(s) ...")
    if args.multfile:
        if results:
            if args.output.endswith(".csv"):
                write_output.gen_csv_xls_mult(query, results, args.output)
            elif args.output.endswith(".xlsx") or args.output.endswith(".xls"):
                write_output.gen_csv_xls_mult(query, results, args.output)
            else:
                write_output.gen_sdf_mult(query, results, args.output)
            if args.pdf:
                print("Generating PDF file ...")
                if args.output.endswith(".sdf") or args.output.endswith(".csv") or args.output.endswith(".xlsx") or \
                   args.output.endswith(".xls"):
                    out_file = args.output.rsplit(".", maxsplit=1)[0]
                else:
                    out_file = args.output
                if args.simmap:
                    print(f"Calculating similarity maps for {len(results)} matches ...")
                    visualize.fp_maps(results, query, args.fingerprint, args.radius, args.nbits, features,
                                      args.similarity, out_file, ttf_path, args.multfile)
                else:
                    visualize.gen_pdf_mf(query, results, out_file, ttf_path)
    else:
        if results:
            if args.output.endswith(".csv") or args.output.endswith(".xlsx") or args.output.endswith(".xls"):
                write_output.gen_csv_xls(results, args.output)
            else:
                write_output.gen_sdf(results, args.output)
            if args.pdf:
                print("Generating PDF file(s) ...")
                if args.output.endswith(".sdf") or args.output.endswith(".csv") or args.output.endswith(
                        ".xlsx") or args.output.endswith(".xls"):
                    out_file = f"{args.output.rsplit('.', maxsplit=1)[0]}.pdf"
                else:
                    out_file = f"{args.output}.pdf"
                if args.simmap:
                    if args.fingerprint == "MACCS":
                        print("For MACCS keys no similarity map can be computed")
                        visualize.gen_pdf(query, results, out_file, ttf_path)
                    elif args.similarity == "tver":
                        print("For Tversky Similarity no similarity map can be computed")
                        visualize.gen_pdf(query, results, out_file, ttf_path)
                    else:
                        print(f"Calculating similarity maps for {len(results)} matches ...")
                        visualize.fp_maps(results, query, args.fingerprint, args.radius, args.nbits, features,
                                          args.similarity, out_file, ttf_path, args.multfile)
                else:
                    visualize.gen_pdf(query, results, out_file, ttf_path)
    end_time = time.time()
    print(f"Finished: {time.strftime('%m/%d/%Y, %H:%M:%S', time.localtime())}")
    duration = round(end_time - start_time, 5)
    print(f"Finished in {duration} seconds")


fp_sim.set_defaults(func=fingerprint)


## shape similarity search

shape_sim = subparsers.add_parser("shape")
shape_group = shape_sim.add_mutually_exclusive_group(required=True)
shape_group.add_argument("-i", "--input", help="specify path of input file [sdf, csv, xlsx]", metavar="")
shape_group.add_argument("-smi", "--smiles", action="append",
                         help="specify SMILES string on command line in double quotes", metavar="")
shape_sim.add_argument("-o", "--output", help="specify name of output file [default: shape.sdf]", default="shape.sdf",
                       metavar="")
shape_sim.add_argument("-d", "--database", help="specify path of the database file [sdf or vsdb] or specify the "
                                                "shortcut for an integrated database", default=db_default, metavar="")
shape_sim.add_argument("-np", "--nproc", help="Specify the number of processors to run the application in "
                                              "multiprocessing mode", type=int, metavar="")
shape_sim.add_argument("-t", "--top_hits", default=10, type=int, help="Maximum number of molecules with highest "
                                                                      "score to keep [default: 10]", metavar="")
shape_sim.add_argument("-a", "--align_method", choices=["mmff", "crippen"], default="mmff",
                       help="select method for molecular alignment [mmff, crippen], [default: mmff]", metavar="")
shape_sim.add_argument("-s", "--score", choices=["combo", "shapeonly"], default="combo",
                       help="select score to be used to rank the results", metavar="")
shape_sim.add_argument("-c", "--cutoff", type=float,
                       help="if specified, all molecules with score above cutoff are kept", metavar="")
shape_sim.add_argument("--seed", type=int,
                       help="specify seed for random number generator, for reproducibility", metavar="")
shape_sim.add_argument("--keep_confs", default=1, type=int,
                       help="number of query conformations to keep after energy minimization [default: 1]", metavar="")
shape_sim.add_argument("--nconfs", default=100, type=int,
                       help="maximum number of query conformations to be enumerated [default: 100]", metavar="")
shape_sim.add_argument("--boost", action="store_true",
                       help="distributes query conformer generation and 3D alignment on all available threads of "
                            "your cpu")
shape_sim.add_argument("--pharm_feats", choices=["gobbi", "base", "minimal"], default="gobbi",
                       help="select pharmacophore feature definitions to be used for calculation of 3D fps. "
                            "[default: 'gobbi']", metavar="")
shape_sim.add_argument("--shape_simi", choices=["tan", "protr", "tver"], default="tan",
                       help="specify measure to be used to compare shape similarity [tan, protr, tver], "
                            "[default: tver]", metavar="")
shape_sim.add_argument("--fp_simi", choices=["tan", "dice", "cos", "sok", "russ", "kulc", "mcco", "tver"],
                       default="tan",
                       help="specify measure to be used to for pharmacophore similarity "
                            "[tan, dice, cos, sok, russ, kulc, mcco, tver]", metavar="")
shape_sim.add_argument("--tver_alpha", help="specify alpha parameter (weighs database molecule) for Tversky similarity "
                                            "[default: 0.5]", default=0.5, type=float, metavar="")
shape_sim.add_argument("--tver_beta", help="specify beta parameter (weighs query molecule) for Tversky similarity "
                                           "[default: 0.5]", default=0.5, type=float, metavar="")
shape_sim.add_argument("--pdf", action="store_true", help="generate a pdf file for all results")
shape_sim.add_argument("--pymol", action="store_true", help="generate PyMOL file with 3D conformations for results")


def shape(args):
    start_time = time.time()
    print(f"Start: {time.strftime('%m/%d/%Y, %H:%M:%S', time.localtime())}")
    # check args.nproc
    if args.nproc:
        if 1 < args.nproc < mp.cpu_count():
            print(f"Running in parallel mode on {args.nproc} threads")
            pass
        elif args.nproc <= 1:
            print("Running in single core mode")
            args.nproc = None
        else:
            args.nproc = mp.cpu_count()
            print(f"Running in parallel mode on {args.nproc} threads")
    else:
        print("Running in single core mode")
    if args.boost:
        nthreads = 0
    else:
        nthreads = 1
    mols = {}
    if args.database in db_config:
        try:
            mols = pickle.load(open(f"{config['local_db']}/{args.database}.vsdb", "rb"))
        except FileNotFoundError:
            try:
                mols = pickle.load(open(f"{config['global_db']}/{args.database}.vsdb", "rb"))
            except FileNotFoundError:
                parser.error(
                    message=f"{args.database} not found. Please make sure you specified the correct shortcut")
    else:
        if os.path.exists(args.database):
            if args.database.endswith(".vsdb"):
                try:
                    mols = pickle.load(open(args.database, "rb"))
                except:
                    parser.error(message=f"{args.database} could not be opened. Please make sure the file has the correct "
                                               f"format")
            elif args.database.endswith(".sdf"):
                mols, _ = read.read_db_from_sd_3d(args.database)
                if not mols:
                    parser.exit(status=2, message="No molecules with 3D coordinates could be read from SD file !")
            else:
                parser.error(message="Database must have format .vsdb or .sdf. Use mode preparedb to prepare a database for"
                                     " shape similarity screening.")
        else:
            parser.error(message=f"{args.database} could not be opened. "
                                 f"Please make sure you specified the correct path")
    try:
        db_desc = mols.pop("config")
        # if db_desc[1] == 0:
        #     parser.error(message=f"Database {args.database} does not contain conformers. Use mode preparedb to generate "
        #                          f"conformers and prepare a database for shape similarity screening")

        seed = db_desc[3]
        if seed is None:
            if args.seed:
                seed = args.seed
            else:
                seed = random.randint(1, 10000)
        # num_confs = db_desc[1]
    except KeyError:
        if args.seed:
            seed = args.seed
        else:
            seed = random.randint(1, 10000)
        # num_confs = 100
    # read query
    if args.smiles:
        query = read.read_smiles_std(args.smiles)
    else:
        query = read.read_sd_3d(args.input)
        print(query)
    # perform shape screening with specified parameters
    if args.nproc:
        pool_shape = mp.Pool(processes=args.nproc)
        if args.smiles:
            mol2d_list = [(query[i]["mol"], i, args.nconfs, seed, args.keep_confs, nthreads, args.pharm_feats) for i in query]
            mol3d_list = []
        else:
            mol3d_list = [(query[i]["mol"], i, args.pharm_feats) for i in query if query[i]["mol"].GetConformer().Is3D()]
            mol2d_list = [(query[i]["mol"], i, args.nconfs, seed, args.keep_confs, nthreads, args.pharm_feats) for i in query if
                          query[i]["mol"].GetConformer().Is3D() is False]
        if mol2d_list:
            print(f"Generating 3D conformer(s) for {len(mol2d_list)} query molecule(s)")
            query_confs = pool_shape.starmap(shapesearch.gen_query_conf_pfp_mp, mol2d_list)
            for entry in query_confs:
                query[entry[0]]["confs"] = entry[1]
                query[entry[0]]["fp_shape"] = entry[2]
            del query_confs
            print(query)
        if mol3d_list:
            query_confs = pool_shape.starmap(shapesearch.gen_query_pfp_mp, mol3d_list)
            print(query_confs)
            for entry in query_confs:
                query[entry[0]]["confs"] = entry[1]
                query[entry[0]]["fp_shape"] = entry[2]
            del query_confs
            print(query)
        algs = pool_shape.starmap(shapesearch.shape_mp, [(mols[i]["confs"], i, mols[i]["pattern"], query[j]["confs"], j,
                                                               query[j]["fp_shape"], k, nthreads, args.shape_simi, args.fp_simi, args.tver_alpha, args.tver_beta, args.align_method, args.pharm_feats) for i in mols for j
                                                              in query for k in
                                                              range(query[j]["confs"].GetNumConformers()) if "confs" in mols[i]])
        pool_shape.close()
    else:
        shapesearch.gen_query_conf_pfp(query, args.nconfs, seed, args.keep_confs, nthreads, args.align_method, args.pharm_feats)
        algs = shapesearch.shape_search(mols, query, nthreads, args.align_method, args.shape_simi, args.fp_simi, args.pharm_feats, args.tver_alpha, args.tver_beta)
    # sort results
    grouped_algs = [res for res in (list(group) for k, group in groupby(sorted(algs, key=lambda entry: entry[3]), lambda x: x[3]))]
    grouped = []
    if args.score == "combo":
        sort_score = 0
    else:
        sort_score = 1
    if args.cutoff:
        for res in grouped_algs:
            gr = sorted([max(conf, key=lambda entry: entry[sort_score]) for conf in (list(group) for k, group in groupby(res, lambda x: x[8]))], reverse=True)
            print(gr)
            gr_res = [entry for entry in gr if entry[sort_score] >= args.cutoff]
            del gr
            print(gr_res)
            print(len(gr_res))
            grouped.append(gr_res)
    else:
        for res in grouped_algs:
            gr_res = sorted([max(conf, key=lambda entry: entry[sort_score]) for conf in (list(group) for k, group in groupby(res, lambda x: x[8]))],
                        reverse=True)[:args.top_hits]
            print(gr_res)
            print(len(gr_res))
            grouped.append(gr_res)
    results = {}
    counter = 0
    for entry in grouped:
        for feat in entry:
            props = copy.deepcopy(mols[feat[4]]["props"])
            props["Combo_Score"] = feat[0]
            props["Shape_Similarity"] = feat[1]
            props["3D_FP_Similarity"] = feat[2]
            props["QuerySmiles"] = query[feat[3]]["pattern"]
            results[counter] = {"mol": feat[6], "props": props, "top_conf": feat[5],
                                "q_num": feat[3]}
            counter += 1
    print(results)
    # write results to output files
    print(len(results))
    out_file = args.output.rsplit(".sdf", maxsplit=1)[0]
    for j in query:
        with open(f"{out_file}_{j + 1}.sdf", "w") as out:
            for i in results:
                if results[i]["q_num"] == j:
                    write_output.write_sdf_conformer(results[i]["mol"], results[i]["props"], results[i]["top_conf"], out)
        with open(f"{out_file}_{j + 1}_query.sdf", "w") as out_q:
            for confid in range(query[j]["confs"].GetNumConformers()):
                write_output.write_sdf_conformer(query[j]["confs"], {"Smiles": query[j]["pattern"]}, confid, out_q)
    if args.pymol:
        for j in query:
            visualize.export_pymol(f"{out_file}_{j + 1}_query.sdf", f"{out_file}_{j + 1}.sdf")
    if args.pdf:
        visualize.gen_pdf_shape(query, results, out_file, ttf_path)


shape_sim.set_defaults(func=shape)


## prepare databases for screening

canon = subparsers.add_parser("preparedb")
canon.add_argument("-i", "--input", help="specify path of input file [sdf, csv, xlsx] (required)", required=True, metavar="infile")
canon.add_argument("-o", "--output", default="prep_database.vsdb", help="specify name of output file [default: prep_database.vsdb]",
                   metavar="")
canon.add_argument("-int", "--integrate", help="specify shortcut for database; saves database to $HOME/VSFlow_Databases", metavar="")
canon.add_argument("-intg", "--int_global", help="stores database in {path_to_script}/Databases instead of $HOME/VSFlow_Databases, "
                                                 "can only be specified together with --integrate flag",
                   action="store_true")
canon.add_argument("-s", "--standardize", help="standardizes molecules, removes salts and associated charges",
                   action="store_true")
canon.add_argument("-c", "--conformers", help="generates multiple 3D conformers, required for mode shape",
                   action="store_true")
canon.add_argument("-np", "--nproc", type=int, help="specify number of processors to run application in multiprocessing mode", metavar="")
canon.add_argument("--max_tauts", help="maximum number of tautomers to be enumerated during standardization process",
                   type=int, default=100, metavar="")
canon.add_argument("--nconfs", help="maximal number of conformers generated", type=int, default=20, metavar="")
canon.add_argument("--rms_thresh", help="if specified, only those conformations out of nconfs that are at least "
                                        "this different are retained (RMSD calculated on heavy atoms)", type=float,
                   metavar="")
canon.add_argument("--seed", type=int, help="specify seed for random number generator, for reproducibility", metavar="")
canon.add_argument("--boost", help="distributes conformer generation on all available threads of your cpu",
                   action="store_true")


def canon_mol(args):
    start_time = time.time()
    print(f"Start: {time.strftime('%m/%d/%Y, %H:%M:%S', time.localtime())}")
    if args.boost:
        nthreads = 0
    else:
        nthreads = 1
    if args.integrate:
        db_name = args.integrate
        if args.int_global:
            db_path = config["global_db"]
            try:
                if os.path.exists(db_path):
                    with open(f"{db_path}/.test", "w") as test_file:
                        test_file.write("")
                else:
                    os.mkdir(db_path)
            except PermissionError:
                canon.error(message="You do not have the permission to integrate a database globally. Please contact "
                                    "your system administrator or re-run with sudo permissions !")
        else:
            db_path = config["local_db"]
            try:
                if os.path.exists(db_path):
                    pass
                else:
                    os.mkdir(db_path)
            except FileNotFoundError:
                canon.error(message="Path not valid. Please make sure you specified a correct path !")
            except PermissionError:
                canon.error(message="Permission denied")
            except OSError:
                canon.error(message="Permission denied")
        if args.integrate in db_config:
            choice = input(
                f"A database with name {db_name} is already integrated in VSFlow. Press 'o' to override the database, "
                f"press 'n' to choose a new name for the database or press 'c' to cancel and exit.")
            while choice != "o" and choice != "n" and choice != "c":
                choice = input("Press 'o' to override the database, press 'n' to choose a new name for the "
                                "database or press 'c' to cancel and exit.")
            if choice == "o":
                try:
                    test_load = pickle.load(open(f"{config['global_db']}/{args.integrate}", "rb"))
                    del test_load
                    with open(f"{config['global_db']}/.test", "w") as test_file:
                        test_file.write("")
                except FileNotFoundError:
                    pass
                except PermissionError:
                    sec_choice = input(f"You do not have the permission to change the database {args.integrate}. Please contact "
                          f"your system administrator or run again with sudo. Press 'c' to cancel or press 'n' to "
                          f"enter a different name")
                    while sec_choice != "n" and sec_choice != "c":
                        sec_choice = input(f"Press 'c' to cancel or press 'n' to enter a different name")
                    if sec_choice == "n":
                        db_name = input("Please enter different name:")
                        while db_name == args.integrate:
                            db_name = input("Please enter different name:")
                    else:
                        exit()
            elif choice == "n":
                db_name = input("Please enter different name:")
                while db_name == args.integrate:
                    db_name = input("Please enter different name:")
            else:
                exit()
        out_path = f"{db_path}/{db_name}.vsdb"
    else:
        if args.output.endswith(".vsdb"):
            out_path = args.output
        else:
            out_path = f"{args.output}.vsdb"
    standardized = "no"
    conformers = "no"
    seed = None
    if args.standardize:
        standardized = "yes"
        if args.nproc:
            can_pool = mp.Pool(processes=args.nproc)
            data, failed = read.read_sd_mp(args.input, can_pool)
            print(f"Finished reading sdf file: {time.strftime('%m/%d/%Y, %H:%M:%S', time.localtime())}")
            if failed:
                print(f"{len(failed)} molecules out of {len(data)} could not be processed")
            data_can = can_pool.starmap(prepare.do_standard, [(data[n]["mol"], data[n]["props"], args.ntauts) for n in data])
            mols = {}
            for i in range(len(data_can)):
                mols[i] = data_can[i]
            can_pool.close()
        else:
            data, failed = read.read_db_from_sd(args.input)
            print(f"Finished reading sdf file: {time.strftime('%m/%d/%Y, %H:%M:%S', time.localtime())}")
            if failed:
                print(f"{len(failed)} molecules out of {len(data)} could not be processed")

            mols = {}
            for n in data:
                std = prepare.do_standard(data[n]["mol"], data[n]["props"], args.ntauts)
                mols[n] = std
        print(f"Finished standardizing molecules: {time.strftime('%m/%d/%Y, %H:%M:%S', time.localtime())}")
    else:
        if args.nproc:
            can_pool = mp.Pool(processes=args.nproc)
            mols, failed = read.read_sd_mp(args.input, can_pool, mode="prepare")
            can_pool.close()
        else:
            mols, failed = read.read_prepare_db_from_sd(args.input)
        if failed:
            print(f"{len(failed)} molecules out of {len(mols) + len(failed)} could not be processed")
    if args.conformers:
        conformers = "yes"
        for i in mols:
            try:
                mol = mols[i]["mol_sta"]
                key = "mol_sta"
            except KeyError:
                key = "mol"
            break
        # if args.threshold:
        #     threshold = args.threshold
        # else:
        #     threshold = -1.0
        print(key)
        if args.seed:
            seed = args.seed
        else:
            seed = random.randint(0, 10000)
        if args.nproc:
            can_pool = mp.Pool(processes=args.nproc)
            confs = can_pool.starmap(prepare.gen_confs_mp, [(mols[i][key], i, args.nconfs, seed, nthreads) for i in mols])
            for entry in confs:
                mols[entry[1]]["confs"] = entry[0]
                mols[entry[1]]["pattern"] = entry[2]
            can_pool.close()
        else:
            prepare.gen_confs(mols, args.nconfs, seed, key, nthreads)
    for i in mols:
        if "confs" in mols[i]:
            conformers = "yes"
        break
    mols["config"] = [standardized, conformers, len(mols), seed]
    pickle.dump(mols, open(out_path, "wb"))
    if args.integrate:
        db_config[db_name] = [time.ctime(os.path.getmtime(out_path)),
                              standardized,
                              conformers,
                              len(mols),
                              seed]
        pickle.dump(db_config, open(f"{home}/.vsflow/.db_config", "wb"))
        print(f"{args.input} was integrated as database {db_name} in VSFlow. You can now search the database calling -db "
              f"{db_name}.")

    end_time = time.time()
    duration = round(end_time - start_time)
    print(f"Finished in {duration} seconds")


canon.set_defaults(func=canon_mol)


## show integrated databases

show_db = subparsers.add_parser("managedb")
show_db.add_argument("-d", "--default", help="specify name of database to be set as default")
show_db.add_argument("-s", "--show", help="Show currently integrated databases in VSFlow", action="store_true")
show_db.add_argument("-rm", "--remove", help="specify name of database to be removed")


def get_db(args):
    db_shortcut = ["shortcut"]
    db_create = ["created"]
    db_standard = ["standardized"]
    db_conformers = ["conformers"]
    db_length = ["number of cpds"]
    for db in db_config:
        db_shortcut.append(db)
        db_create.append(db_config[db][0])
        db_standard.append(db_config[db][1])
        db_conformers.append(str(db_config[db][2]))
        db_length.append(db_config[db][3])
    default_db = pickle.load(open(f"{home}/.vsflow/.db_default", "rb"))
    if args.default:
        if args.default in db_shortcut:
            pickle.dump(args.default, open(f"{home}/.vsflow/.db_default", "wb"))
            print(f"'{args.default}' has been set as default database. This database is now used if the -db flag is not"
                  f" specified.")
        else:
            print(f"Database '{args.default}' is not integrated in VSFlow. Use preparedb -h to see how a database can "
                  f"be integrated.")
    if args.show:
        for i in range(len(db_shortcut)):
            if i == 0:
                print('\033[1m')
                print("DATABASES\n")
                print(f"{db_shortcut[i]}" + " "*(max([len(string) for string in db_shortcut]) + 5 - len(db_shortcut[i])) +
                      f"{db_create[i]}" + " "*(max([len(string) for string in db_create]) + 5 - len(db_create[i])) +
                      #f"{db_source[i]}" + " " * (max([len(string) for string in db_source]) + 5 - len(db_source[i])) +
                      f"{db_standard[i]}" + " " * (max([len(string) for string in db_standard]) + 5 - len(db_standard[i])) +
                      f"{db_conformers[i]}" + " " * (max([len(string) for string in db_conformers]) + 5 - len(db_conformers[i])) +
                      #f"{db_all_tauts[i]}" + " " * (max([len(string) for string in db_all_tauts]) + 5 - len(db_all_tauts[i])) +
                      f"{db_length[i]}")
                print('\033[0m')
            else:
                print(f"{db_shortcut[i]}" + " "*(max([len(string) for string in db_shortcut]) + 5 - len(db_shortcut[i])) +
                      f"{db_create[i]}" + " "*(max([len(string) for string in db_create]) + 5 - len(db_create[i])) +
                      #f"{db_source[i]}" + " " * (max([len(string) for string in db_source]) + 5 - len(db_source[i])) +
                      f"{db_standard[i]}" + " " * (max([len(string) for string in db_standard]) + 5 - len(db_standard[i])) +
                      f"{db_conformers[i]}" + " " * (max([len(string) for string in db_conformers]) + 5 - len(db_conformers[i])) +
                      #f"{db_all_tauts[i]}" + " " * (max([len(string) for string in db_all_tauts]) + 5 - len(db_all_tauts[i])) +
                      f"{db_length[i]}")

        print("\n")
        print('\033[1m')
        print(f"Default database: {default_db}")
        print('\033[0m')
        print("You can set (or change) a default database by calling managedb --default {shortcut}")
    if args.remove:
        if args.remove in db_config:
            choice = input(f"Are you sure you want to remove {args.remove} ? [y/n]")
            while choice != "y" and choice != "n":
                choice = input(f"Are you sure you want to remove {args.remove} ? [y/n]")
            if choice == "n":
                pass
            else:
                try:
                    os.remove(f"{db_config['local_db']}/{args.remove}")
                    db_config.pop(args.remove)
                    pickle.dump(db_config, open(f"{home}/.vsflow/.db_config", "wb"))
                except FileNotFoundError:
                    try:
                        os.remove(f"{db_config['global_db']}/{args.remove}")
                        db_config.pop(args.remove)
                        pickle.dump(db_config, open(f"{home}/.vsflow/.db_config", "wb"))
                        print(f"{args.remove} was successfully removed !")
                    except PermissionError:
                        print(f"You do not have the permission to remove {args.remove}. Please contact your system"
                              f"administrator!")
        else:
            print(f"No database with name {args.remove} integrated in VSFlow !")



show_db.set_defaults(func=get_db)


def main():
    args = parser.parse_args()
    if "func" in args:
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

