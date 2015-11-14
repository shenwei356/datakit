#!/usr/bin/env python
# -*- coding: utf-8 -*-
# https://github.com/shenwei356/datakit
# Author     : Wei Shen
# Contact    : shenwei356@gmail.com
# LastUpdate : 2015-08-24

from __future__ import print_function

import argparse
import csv
import logging
import re
import sys

# ===================================[ args ]=================================


def parse_args():
    parser = argparse.ArgumentParser(
        description="Grep CSV file. Multiple keys supported.",
        epilog="https://github.com/shenwei356/datakit")

    parser.add_argument('csvfile',
                        nargs='*',
                        type=argparse.FileType('r'),
                        default=sys.stdin,
                        help='Input file(s)')
    parser.add_argument("-v",
                        "--verbose",
                        help='Verbosely print information',
                        action="count",
                        default=0)

    parser.add_argument('-o',
                        '--outfile',
                        type=argparse.FileType('w'),
                        default=sys.stdout,
                        help='Output file [STDOUT]')
    parser.add_argument(
        "-k",
        '--key',
        type=str,
        default='1',
        help=
        'Column number of key in csvfile. Multiple values shoud be separated by comma [1]')
    parser.add_argument("-H",
                        "--ignoretitle",
                        help="Ignore title",
                        action="store_true")
    parser.add_argument("-F",
                        '--fs',
                        type=str,
                        default=",",
                        help='Field separator [,]')
    parser.add_argument("-Fo",
                        '--fs-out',
                        type=str,
                        help='Field separator of ouput [same as --fs]')
    parser.add_argument("-Q",
                        '--qc',
                        type=str,
                        default='"',
                        help='Quote char["]')
    parser.add_argument("-t",
                        action='store_true',
                        help='Field separator is "\\t". Quote char is "\\t"')

    parser.add_argument('-p',
                        '--pattern',
                        nargs='?',
                        type=str,
                        help='Query pattern')
    parser.add_argument('-pf',
                        '--patternfile',
                        nargs='?',
                        type=str,
                        help='Pattern file')
    parser.add_argument(
        "-pk",
        type=str,
        default='1',
        nargs='?',
        help=
        'Column number of key in pattern file. Multiple values shoud be separated by comma [1]')

    parser.add_argument("-r",
                        "--regexp",
                        help='Pattern is regular expression',
                        action="store_true")
    parser.add_argument("-d",
                        "--speedup",
                        help='Delete matched pattern when matching one record',
                        action="store_true")
    parser.add_argument("-i",
                        "--invert",
                        help="Invert match (do not match)",
                        action="store_true")
    # parser.add_argument("-b", "--bloomfilter", help="Use bloom filter instead of dict",
    #                     action="store_true")

    args = parser.parse_args()

    # logging level
    if args.verbose >= 2:
        level = logging.DEBUG
    elif args.verbose == 1:
        level = logging.INFO
    else:
        level = logging.WARN
    logging.basicConfig(level=level, format="[%(levelname)s] %(message)s")

    # check args
    if not args.pattern and not args.patternfile:
        logging.error("one or both of option -p and -pf needed")
        sys.exit(1)

    if args.t:
        args.fs, args.qc = '\t', '\t'

    if not args.fs_out:
        args.fs_out = args.fs

    return args


def parse_key_index(key):
    if ',' in key:
        return [int(i) for i in key.split(',')]
    else:
        return [int(key)]


def read_patterns(args):
    patterns = dict()

    # pattern from command line
    if args.pattern:
        patterns[args.pattern] = 1

    # pattern from pattern file
    if args.patternfile:
        with open(args.patternfile) as patternfile:
            reader = csv.reader(patternfile,
                                delimiter=args.fs,
                                quotechar=args.qc)
            for row in reader:
                ncolumn = len(row)
                if ncolumn == 0:
                    continue

                # get key
                key = list()
                for k in parse_key_index(args.pk):
                    if ncolumn < k:
                        logging.error(
                            "key ({}) is beyond number of column ({})".format(
                                k, ncolumn))
                        sys.exit(1)
                    key.append(row[k - 1].strip())
                key = '_'.join(key)

                patterns[key] = 1

    if len(patterns) == 0:
        logging.error('no pattern given. Please check pattern file: {}'.format(
            args.patternfile))
        sys.exit(1)

    # pre compile the pattern
    if args.regexp:
        for p in patterns:
            patterns[p] = re.compile(p)

    return patterns


def csv_reader(fh, delimiter, quotechar, ignoretitle=False):
    reader = csv.reader(fh, delimiter=delimiter, quotechar=quotechar)
    once = True
    for row in reader:
        if ignoretitle and once:  # Ignore title
            once = False
            continue
        yield row
    return


def check_row(row, args, patterns):
    ncolumn = len(row)
    if ncolumn == 0:
        return False

    # get key
    key = list()
    for k in parse_key_index(args.key):
        if ncolumn < k:
            logging.error(
                "key ({}) is beyond number of column ({})".format(k, ncolumn))
            sys.exit(1)
        key.append(row[k - 1].strip())
    key = '_'.join(key)

    logging.debug("line: {}; key: {}; row: {}".format(sum, key, row))

    hit = False
    if args.regexp:  # use regular expression
        for k, p in patterns.items():
            if p.search(key):
                hit = True
                if args.speedup:
                    del patterns[k]
                break
    else:
        if key in patterns:  # full match
            hit = True
            if args.speedup:
                del patterns[key]

    if args.invert:
        if hit:
            return False
    else:
        if not hit:
            return False

    return True


if __name__ == '__main__':
    args = parse_args()

    patterns = read_patterns(args)

    logging.info("load {} patterns".format(len(patterns)))
    logging.info("column number of key in pattern: {}".format(args.pk))
    logging.info("Column number of key in csvfile: {}".format(args.key))
    logging.info("Field separator: ({})".format(args.fs))
    logging.info("Quote char: ({})".format(args.qc))

    cnt, sum = 0, 0
    writer = csv.writer(args.outfile,
                        delimiter=args.fs_out,
                        quotechar=args.qc,
                        quoting=csv.QUOTE_MINIMAL)

    stdinflag = False

    # If "iter(sys.stdin.readline, '')" in the flowing for-loop, first line
    # of stdin will be missing
    if args.csvfile is sys.stdin:
        logging.info("read data from STDIN")
        stdinflag = True
        args.csvfile = [iter(sys.stdin.readline, '')]

    for f in args.csvfile:
        if not stdinflag:
            logging.info("read data from file")
            f = iter(f.readline, '')

        next_row = csv_reader(f,
                              args.fs,
                              args.qc,
                              ignoretitle=args.ignoretitle)
        for row in next_row:
            sum += 1
            if args.speedup and len(patterns) == 0:
                break

            if not check_row(row, args, patterns):
                continue

            cnt += 1
            writer.writerow(row)

    proportion = cnt / sum if not sum == 0 else 0
    logging.info("hit proportion: {:.2%} ( {} / {} )".format(proportion, cnt,
                                                             sum))
