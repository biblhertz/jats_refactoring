# jats_refactoring
Scripts used to refactor JATS xml file generated with Sciflow, especially with the references.
The script are intended to 

#### _refactor.xslt_
- add label to all references
- reorder references according to labels
- correct wrong "article-title" attributions
- add missing "webpage" if origin is "@misc"

##### _add_all.py_ 
- include editors combining JATS with the original BibTeX files
- include pages
- include url when DOI is missing

The scripts were created with the support of ChatGPT.
## Prerequisites
- JATS file and BIB file where references id are identical, except for a . in the BIB (i.e. BIB=author.2024 , JATS=author2024)
- 
