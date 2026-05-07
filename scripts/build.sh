#!/usr/bin/env bash

set -o xtrace

PDFDIR=~/personal/src/ons-website/static/archive
OUTPUTDIR=~/personal/src/esnible.github.io/jons/

for file in ${PDFDIR}/*; do 
    if [ -f "$file" ]; then 
        base_name=$(basename ${file})
        extension="${base_name##*.}"
        namepart="${base_name%.*}"
        # echo ${namepart} -- "$file" 
        outputfile=${OUTPUTDIR}/${namepart}.md
        if [ ! -f ${outputfile} ]; then
            # Make sure pdfmd is installed from https://github.com/M1ck4/pdfmd
            # not pypi!
            pdfmd --ocr auto --lang eng+ara --page-breaks --output ${outputfile}
        fi
    fi 
done
